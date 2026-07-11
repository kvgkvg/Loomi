import json
import sqlite3

from fastapi.testclient import TestClient

import core_service.app as app_module
from core_service.events import events


def _connection():
    connection = sqlite3.connect(":memory:", check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        CREATE TABLE users (id TEXT PRIMARY KEY, name TEXT);
        CREATE TABLE assets (
            id TEXT PRIMARY KEY, type TEXT, title TEXT, source_tool TEXT,
            owner_id TEXT, current_version_id TEXT, usage_count INTEGER
        );
        CREATE TABLE asset_versions (
            id TEXT PRIMARY KEY, asset_id TEXT, version_number INTEGER,
            content TEXT, diff_summary TEXT
        );
        CREATE TABLE rationale (
            version_id TEXT, problem TEXT, failed_attempts TEXT,
            constraints TEXT, confidence TEXT
        );
        CREATE TABLE asset_usage (
            id TEXT PRIMARY KEY, asset_id TEXT, user_id TEXT,
            task_description TEXT
        );
        INSERT INTO users VALUES ('u1', 'An');
        INSERT INTO assets VALUES ('a1', 'prompt', 'Lead prompt', 'git', 'u1', 'v1', 2);
        INSERT INTO asset_versions VALUES ('v1', 'a1', 1, 'Classify leads', 'initial');
        INSERT INTO rationale VALUES ('v1', 'Qualify leads', '[]', '["valid JSON"]', 'auto');
        """
    )
    return connection


def _client(monkeypatch):
    connection = _connection()
    class Connection:
        def __getattr__(self, name):
            return getattr(connection, name)

        def close(self):
            pass

    monkeypatch.setattr(app_module, "get_pg_connection", Connection)
    return TestClient(app_module.app), connection


def test_health_and_recommend_delegate(monkeypatch):
    monkeypatch.setattr(app_module, "recommend", lambda task, top_k=5: [{"asset_id": "a1", "score": 0.9}])
    client, _ = _client(monkeypatch)

    assert client.get("/health").json() == {"status": "ok"}
    assert client.post("/recommend", json={"task_description": "qualify inbound leads", "top_k": 1}).json() == {
        "results": [{"asset_id": "a1", "score": 0.9}]
    }
    assert client.post("/recommend", json={"task_description": " "}).status_code == 422


def test_asset_detail_returns_grounded_evidence(monkeypatch):
    client, _ = _client(monkeypatch)

    response = client.get("/assets/a1")

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Lead prompt"
    assert body["owner_name"] == "An"
    assert body["versions"][0]["content"] == "Classify leads"
    assert body["versions"][0]["constraints"] == ["valid JSON"]


def test_explain_delegates(monkeypatch):
    monkeypatch.setattr(
        app_module,
        "explain_asset",
        lambda asset_id, question=None: {
            "explanation": f"{asset_id}: {question}",
            "cited_versions": [1],
            "cited_constraints": [],
        },
    )
    client, _ = _client(monkeypatch)

    response = client.post("/assets/a1/explain", json={"question": "Why?"})

    assert response.json()["explanation"] == "a1: Why?"


def test_use_records_adoption(monkeypatch):
    client, connection = _client(monkeypatch)

    response = client.post(
        "/assets/a1/use",
        json={"user_id": "u1", "task_description": "qualify inbound leads"},
    )

    assert response.status_code == 201
    assert response.json()["content"] == "Classify leads"
    assert connection.execute("SELECT COUNT(*) FROM asset_usage").fetchone()[0] == 1
    assert connection.execute("SELECT usage_count FROM assets WHERE id = 'a1'").fetchone()[0] == 3


def test_ready_event_is_published_only_after_successful_capture(monkeypatch):
    while events.pop() is not None:
        pass
    monkeypatch.setattr(app_module, "process_raw_event", lambda _: {"embedded": True, "asset_id": "a1"})
    client, _ = _client(monkeypatch)

    response = client.post("/internal/capture", json={"commit_sha": "abc"})

    assert response.status_code == 202
    assert events.pop() == {"type": "memory_ready", "asset_id": "a1"}

    monkeypatch.setattr(app_module, "process_raw_event", lambda _: {"embedded": False, "asset_id": "a2"})
    client.post("/internal/capture", json={"commit_sha": "def"})
    assert events.pop() is None


def test_internal_event_stream(monkeypatch):
    client, _ = _client(monkeypatch)
    while events.pop() is not None:
        pass
    events.publish({"type": "capture_retrying", "commit_sha": "abc"})

    with client.stream("GET", "/internal/events?once=true") as response:
        assert response.status_code == 200
        assert next(response.iter_lines()) == 'data: {"type": "capture_retrying", "commit_sha": "abc"}'
