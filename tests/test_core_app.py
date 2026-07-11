import os
os.environ["LOOMI_TESTING"] = "1"

import pytest
import subprocess
import asyncio
import json
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient

from db.client import get_pg_connection, get_vector_collection
from core.app import app, poll_git_repo, event_broadcaster
import capture_pipeline.process as process_module
import onboarding.assistant as assistant_module

def _git(path, *args):
    return subprocess.run(
        ["git", *args], cwd=path, check=True, text=True, capture_output=True
    ).stdout.strip()

@pytest.fixture
def temp_git_repo(tmp_path):
    repository = tmp_path / "test-repo"
    repository.mkdir()
    _git(repository, "init")
    _git(repository, "config", "user.name", "An")
    _git(repository, "config", "user.email", "an@example.com")
    
    # Create a markdown knowledge file
    prompt = repository / "prompts" / "test-prompt.md"
    prompt.parent.mkdir(parents=True, exist_ok=True)
    prompt.write_text("Hello Loomi!", encoding="utf-8")
    _git(repository, "add", ".")
    _git(repository, "commit", "-m", "initial commit")
    return repository

def test_health_endpoint(isolated_runtime):
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["database"] == "ok"
        assert data["vector_store"] == "ok"

def test_recommend_endpoint(isolated_runtime):
    # Populate mock assets/vectors
    col = get_vector_collection()
    col.upsert(
        ids=["asset1"],
        documents=["Find all code blocks."],
        metadatas=[{"asset_id": "asset1", "version_id": "v1", "source_tool": "git"}]
    )
    
    conn = get_pg_connection()
    conn.execute("INSERT INTO raw_events (id, source_tool, title, content, processed) VALUES ('r1', 'git', 'Title1', 'Find all code blocks.', 1)")
    conn.execute("INSERT INTO users (id, name, email) VALUES ('u1', 'An', 'an@example.com')")
    conn.execute("INSERT INTO assets (id, title, type, source_tool, owner_id, current_version_id) VALUES ('asset1', 'Title1', 'prompt', 'git', 'u1', 'v1')")
    conn.execute("INSERT INTO asset_versions (id, asset_id, raw_event_id, version_number, content) VALUES ('v1', 'asset1', 'r1', 1, 'Find all code blocks.')")
    conn.execute("INSERT INTO rationale (id, version_id, problem, failed_attempts, constraints, confidence) VALUES ('rat1', 'v1', 'extract blocks', '[]', '[]', 'auto')")
    conn.commit()
    conn.close()

    with TestClient(app) as client:
        response = client.post("/recommend", json={"task_description": "find code", "top_k": 2})
        assert response.status_code == 200
        data = response.json()
        assert len(data) > 0
        assert data[0]["asset_id"] == "asset1"
        assert data[0]["title"] == "Title1"

def test_explain_endpoint(isolated_runtime):
    # Mock explain_asset from assistant_module
    with patch("core.app.explain_asset", return_value={"explanation": "This is mock explanation", "cited_versions": [1], "cited_constraints": []}):
        with TestClient(app) as client:
            response = client.post("/explain", json={"asset_id": "asset1", "question": "Why?"})
            assert response.status_code == 200
            data = response.json()
            assert data["explanation"] == "This is mock explanation"
            assert data["cited_versions"] == [1]

def test_git_poller_and_capture_flow(temp_git_repo, isolated_runtime, monkeypatch):
    # Change working directory to temp git repo so capture_commit works
    monkeypatch.chdir(temp_git_repo)
    
    # Mock LLM calls inside capture_pipeline
    monkeypatch.setattr(
        process_module,
        "extract_rationale",
        lambda content, signal: {
            "problem": "Create mock logic",
            "failed_attempts": [],
            "constraints": ["Constraint 1"],
            "confidence": "auto",
        },
    )
    
    # 1. Get initial HEAD SHA
    head_sha = _git(temp_git_repo, "rev-parse", "HEAD")
    
    # 2. Test poller initialization
    # If git_poll_state is empty, calling poll_git_repo should insert the current HEAD SHA and return no new events
    events = poll_git_repo(temp_git_repo)
    assert len(events) == 0
    
    # Verify DB has last_polled_sha set to current head_sha
    conn = get_pg_connection()
    row = conn.execute("SELECT last_polled_sha FROM git_poll_state WHERE repo_path = ?", (str(temp_git_repo),)).fetchone()
    assert row is not None
    assert row["last_polled_sha"] == head_sha
    
    # 3. Create a new commit in the repository
    prompt2 = temp_git_repo / "prompts" / "test-prompt2.md"
    prompt2.write_text("Hello second prompt!", encoding="utf-8")
    _git(temp_git_repo, "add", ".")
    _git(temp_git_repo, "commit", "-m", "second commit")
    new_sha = _git(temp_git_repo, "rev-parse", "HEAD")
    
    # 4. Call poll_git_repo again - it should detect, capture and process the new commit
    events = poll_git_repo(temp_git_repo)
    assert len(events) == 1
    assert events[0]["title"] == "second commit"
    assert events[0]["problem"] == "Create mock logic"
    
    # Verify DB has last_polled_sha advanced to new_sha
    row = conn.execute("SELECT last_polled_sha FROM git_poll_state WHERE repo_path = ?", (str(temp_git_repo),)).fetchone()
    assert row["last_polled_sha"] == new_sha
    
    # 5. Call poll_git_repo again - it should NOT process duplicates (no new commits)
    events = poll_git_repo(temp_git_repo)
    assert len(events) == 0
    
    # 6. Test manual capture endpoint on a new commit
    prompt3 = temp_git_repo / "prompts" / "test-prompt3.md"
    prompt3.write_text("Hello third prompt!", encoding="utf-8")
    _git(temp_git_repo, "add", ".")
    _git(temp_git_repo, "commit", "-m", "third commit")
    third_sha = _git(temp_git_repo, "rev-parse", "HEAD")
    
    monkeypatch.setenv("LOOMI_REPO_PATH", str(temp_git_repo))
    with TestClient(app) as client:
        response = client.post("/capture", json={"commit_sha": third_sha})
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["raw_event_id"] is not None
        
        # 7. Check if poller skips it next time
        # Calling poll_git_repo should advance the last_polled_sha but return 0 new events because it is already captured
        events = poll_git_repo(temp_git_repo)
        assert len(events) == 0
        
        # Verify last_polled_sha is advanced to third_sha
        row = conn.execute("SELECT last_polled_sha FROM git_poll_state WHERE repo_path = ?", (str(temp_git_repo),)).fetchone()
        assert row["last_polled_sha"] == third_sha
    conn.close()

def test_adopt_endpoint(isolated_runtime):
    conn = get_pg_connection()
    conn.execute("INSERT INTO users (id, name, email) VALUES ('u1', 'An', 'an@example.com')")
    conn.execute("INSERT INTO assets (id, title, type, source_tool, owner_id) VALUES ('asset1', 'Title1', 'prompt', 'git', 'u1')")
    conn.commit()
    conn.close()

    with TestClient(app) as client:
        response = client.post(
            "/adopt",
            json={"asset_id": "asset1", "user_id": "u1", "task_description": "Use this prompt"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["usage_id"] is not None

        # Verify usage count updated
        conn = get_pg_connection()
        row = conn.execute("SELECT usage_count FROM assets WHERE id = 'asset1'").fetchone()
        assert row["usage_count"] == 1
        conn.close()

def test_events_stream_connection(isolated_runtime):
    with TestClient(app) as client:
        with client.stream("GET", "/events") as response:
            assert response.status_code == 200
            assert response.headers["content-type"] == "text/event-stream"
            iterator = response.iter_lines()
            conn_line = next(iterator)
            assert "connected" in conn_line

@pytest.mark.anyio
async def test_event_broadcaster():
    queue = event_broadcaster.subscribe()
    assert len(event_broadcaster.listeners) == 1
    
    await event_broadcaster.broadcast("test_event", {"some": "data"})
    event = await queue.get()
    assert event["event"] == "test_event"
    assert event["data"] == {"some": "data"}
    
    event_broadcaster.unsubscribe(queue)
    assert len(event_broadcaster.listeners) == 0
