import os
os.environ["LOOMI_TESTING"] = "1"

import pytest
import subprocess
import asyncio
import json
from pathlib import Path
from unittest.mock import patch

from db.client import get_pg_connection, get_vector_collection
from core.app import poll_git_repo, event_broadcaster
import core.app as core_app_module
import capture_pipeline.process as process_module
import onboarding.assistant as assistant_module
import recommend.engine as recommend_module


class FakeCollection:
    def __init__(self):
        self.records = {}

    def upsert(self, *, ids, documents, metadatas):
        for index, item_id in enumerate(ids):
            self.records[item_id] = {
                "document": documents[index],
                "metadata": metadatas[index],
            }

    def count(self):
        return len(self.records)

    def query(self, *, query_texts, n_results):
        ids = list(self.records)[:n_results]
        return {"ids": [ids], "distances": [[0.1 for _ in ids]]}


@pytest.fixture(autouse=True)
def fake_vector_collection(monkeypatch):
    collection = FakeCollection()

    async def run_inline(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(core_app_module, "get_vector_collection", lambda: collection)
    monkeypatch.setattr(recommend_module, "get_vector_collection", lambda: collection)
    monkeypatch.setattr(core_app_module.anyio.to_thread, "run_sync", run_inline)
    monkeypatch.setitem(globals(), "get_vector_collection", lambda: collection)
    return collection

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
    data = core_app_module.health_check()
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

    data = asyncio.run(core_app_module.recommend_endpoint(
        core_app_module.RecommendRequest(task_description="find code", top_k=2)
    ))
    assert len(data) > 0
    assert data[0]["asset_id"] == "asset1"
    assert data[0]["title"] == "Title1"

def test_explain_endpoint(isolated_runtime):
    # Mock explain_asset from assistant_module
    with patch("core.app.explain_asset", return_value={"explanation": "This is mock explanation", "cited_versions": [1], "cited_constraints": []}):
        data = asyncio.run(core_app_module.explain_endpoint(
            core_app_module.ExplainRequest(asset_id="asset1", question="Why?")
        ))
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
    monkeypatch.setattr(
        process_module,
        "get_vector_collection",
        lambda: type("Collection", (), {"upsert": lambda self, **kwargs: None})(),
    )
    emitted_stages = []
    monkeypatch.setattr(
        core_app_module,
        "_emit_stage",
        lambda header, stage, status, log=None, result=None: emitted_stages.append((stage, status)),
    )
    monkeypatch.setattr(core_app_module.time, "sleep", lambda _: None)
    
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
    
    # 4. Call poll_git_repo again - it should detect and prepare the new commit,
    # but not broadcast memory_ready until human review finalizes it.
    events = poll_git_repo(temp_git_repo)
    assert len(events) == 0
    for stage in ("persist", "embed"):
        assert (stage, "running") in emitted_stages
        assert emitted_stages.index((stage, "running")) < emitted_stages.index((stage, "success"))
    assert (("finalize", "skipped")) in emitted_stages
    pending = conn.execute(
        """
        SELECT re.processed, count(rs.id) AS statement_count
        FROM raw_events re
        JOIN asset_versions av ON av.id = re.processed_asset_version_id
        JOIN rationale_statements rs ON rs.version_id = av.id
        WHERE re.title = ?
        GROUP BY re.processed
        """,
        ("second commit",),
    ).fetchone()
    assert pending["processed"] == 0
    assert pending["statement_count"] == 2
    
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
    data = asyncio.run(core_app_module.capture_endpoint(
        core_app_module.CaptureRequest(commit_sha=third_sha)
    ))
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


def test_pull_request_trigger_captures_head_commit(temp_git_repo, isolated_runtime, monkeypatch):
    monkeypatch.chdir(temp_git_repo)
    monkeypatch.setattr(core_app_module, "get_tracked_repo", lambda: temp_git_repo)
    monkeypatch.setattr(
        process_module,
        "extract_rationale",
        lambda content, signal: {
            "problem": "Review PR knowledge",
            "failed_attempts": [],
            "constraints": ["Wait for reviewer"],
            "confidence": "auto",
        },
    )
    monkeypatch.setattr(
        process_module,
        "get_vector_collection",
        lambda: type("Collection", (), {"upsert": lambda self, **kwargs: None})(),
    )

    prompt = temp_git_repo / "prompts" / "pr-trigger.md"
    prompt.write_text("PR-triggered prompt update", encoding="utf-8")
    _git(temp_git_repo, "add", ".")
    _git(temp_git_repo, "commit", "-m", "pr prompt update")
    head_sha = _git(temp_git_repo, "rev-parse", "HEAD")

    data = asyncio.run(core_app_module.pull_request_trigger_endpoint(
        core_app_module.PullRequestTriggerRequest(commit_sha=head_sha, action="opened")
    ))

    assert data["status"] == "triggered"
    assert data["commit_sha"] == head_sha
    assert data["review_status"] == "pending"
    conn = get_pg_connection()
    row = conn.execute(
        "SELECT processed, processed_asset_version_id FROM raw_events WHERE title = ?",
        ("pr prompt update",),
    ).fetchone()
    assert row["processed"] == 0
    assert row["processed_asset_version_id"] == data["version_id"]
    runs = asyncio.run(core_app_module.runs_endpoint())
    run = next(r for r in runs["runs"] if r["full_sha"] == head_sha)
    assert run["status"] == "running"
    assert run["stages"][-1]["key"] == "finalize"
    assert run["stages"][-1]["status"] == "skipped"


def test_adopt_endpoint(isolated_runtime):
    conn = get_pg_connection()
    conn.execute("INSERT INTO users (id, name, email) VALUES ('u1', 'An', 'an@example.com')")
    conn.execute("INSERT INTO assets (id, title, type, source_tool, owner_id) VALUES ('asset1', 'Title1', 'prompt', 'git', 'u1')")
    conn.commit()
    conn.close()

    data = asyncio.run(core_app_module.adopt_endpoint(
        core_app_module.AdoptRequest(asset_id="asset1", user_id="u1", task_description="Use this prompt")
    ))
    assert data["status"] == "success"
    assert data["usage_id"] is not None

    # Verify usage count updated
    conn = get_pg_connection()
    row = conn.execute("SELECT usage_count FROM assets WHERE id = 'asset1'").fetchone()
    assert row["usage_count"] == 1
    conn.close()

@pytest.mark.anyio
async def test_events_stream_connection(isolated_runtime):
    response = await core_app_module.events_endpoint()
    assert response.media_type == "text/event-stream"

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
