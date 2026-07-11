import json
import asyncio
import sqlite3
import threading

import httpx

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
    return connection


async def _request(method, path, **kwargs):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app_module.app), base_url="http://test"
    ) as client:
        return await client.request(method, path, **kwargs)


def test_health_and_recommend_delegate(monkeypatch):
    monkeypatch.setattr(app_module, "recommend", lambda task, top_k=5: [{"asset_id": "a1", "score": 0.9}])
    _client(monkeypatch)

    assert asyncio.run(_request("GET", "/health")).json() == {"status": "ok"}
    assert asyncio.run(_request("POST", "/recommend", json={"task_description": "qualify inbound leads", "top_k": 1})).json() == {
        "results": [{"asset_id": "a1", "score": 0.9}]
    }
    assert asyncio.run(_request("POST", "/recommend", json={"task_description": " "})).status_code == 422


def test_asset_detail_returns_grounded_evidence(monkeypatch):
    _client(monkeypatch)

    response = asyncio.run(_request("GET", "/assets/a1"))

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
    _client(monkeypatch)

    response = asyncio.run(_request("POST", "/assets/a1/explain", json={"question": "  Why?  "}))

    assert response.json()["explanation"] == "a1: Why?"
    assert asyncio.run(_request("POST", "/assets/a1/explain", json={"question": " "})).status_code == 422


def test_use_records_adoption(monkeypatch):
    connection = _client(monkeypatch)

    response = asyncio.run(_request(
        "POST", "/assets/a1/use",
        json={"user_id": "u1", "task_description": "qualify inbound leads"}
    ))

    assert response.status_code == 201
    assert response.json()["content"] == "Classify leads"
    assert connection.execute("SELECT COUNT(*) FROM asset_usage").fetchone()[0] == 1
    assert connection.execute("SELECT usage_count FROM assets WHERE id = 'a1'").fetchone()[0] == 3


def test_capture_routes_sha_to_raw_event_and_emits_grounded_lifecycle(monkeypatch):
    calls = []
    monkeypatch.setattr(
        app_module,
        "capture_commit",
        lambda sha: calls.append(("capture", sha)) or {
            "raw_event_id": "raw-1",
            "title": "Lead prompt",
            "source_tool": "git",
        },
    )
    monkeypatch.setattr(
        app_module,
        "process_raw_event",
        lambda raw_id: calls.append(("process", raw_id)) or {
            "embedded": True,
            "asset_id": "a1",
            "version_id": "v1",
        },
    )

    async def exercise():
        events.clear()
        stream = events.subscribe()
        started = asyncio.create_task(anext(stream))
        await asyncio.sleep(0)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_module.app), base_url="http://test"
        ) as client:
            response = await client.post("/internal/capture", json={"commit_sha": "abc"})
        assert response.status_code == 202
        assert await started == {"type": "capture_started", "commit_sha": "abc"}
        assert await anext(stream) == {
            "type": "memory_ready",
            "asset_id": "a1",
            "title": "Lead prompt",
            "source": "git",
            "version": "v1",
        }
        await stream.aclose()

    asyncio.run(exercise())
    assert calls == [("capture", "abc"), ("process", "raw-1")]


def test_capture_started_reaches_subscriber_before_git_work(monkeypatch):
    release_capture = threading.Event()

    def blocked_capture(sha):
        assert release_capture.wait(timeout=1)
        return {"raw_event_id": "raw-1", "title": "Lead prompt", "source_tool": "git"}

    monkeypatch.setattr(app_module, "capture_commit", blocked_capture)
    monkeypatch.setattr(
        app_module,
        "process_raw_event",
        lambda _: {"embedded": True, "asset_id": "a1", "version_id": "v1"},
    )

    async def exercise():
        events.clear()
        stream = events.subscribe()
        request = asyncio.create_task(_request("POST", "/internal/capture", json={"commit_sha": "abc"}))
        assert await asyncio.wait_for(anext(stream), timeout=1) == {
            "type": "capture_started",
            "commit_sha": "abc",
        }
        release_capture.set()
        assert (await request).status_code == 202
        await stream.aclose()

    asyncio.run(exercise())


def test_capture_failure_emits_retrying_without_ready(monkeypatch):
    monkeypatch.setattr(
        app_module,
        "capture_commit",
        lambda _: {"raw_event_id": "raw-1", "title": "Lead prompt", "source_tool": "git"},
    )
    monkeypatch.setattr(
        app_module,
        "process_raw_event",
        lambda _: {"embedded": False, "asset_id": "a1", "error": "vector failed"},
    )

    async def exercise():
        events.clear()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_module.app), base_url="http://test"
        ) as client:
            response = await client.post("/internal/capture", json={"commit_sha": "abc"})
        assert response.status_code == 202
        assert response.json()["error"] == "capture failed"
        stream = events.subscribe()
        assert await anext(stream) == {"type": "capture_started", "commit_sha": "abc"}
        assert await anext(stream) == {
            "type": "capture_retrying",
            "commit_sha": "abc",
            "error": "capture failed",
        }
        await stream.aclose()

    asyncio.run(exercise())


def test_capture_exception_is_safe_and_retryable(monkeypatch):
    def fail_capture(_):
        raise ValueError("bad sha at /srv/private?token=secret")

    monkeypatch.setattr(app_module, "capture_commit", fail_capture)

    async def exercise():
        events.clear()
        response = await _request("POST", "/internal/capture", json={"commit_sha": "abc"})
        assert response.status_code == 202
        assert response.json() == {"embedded": False, "error": "capture failed"}
        stream = events.subscribe()
        assert (await anext(stream))["type"] == "capture_started"
        assert await anext(stream) == {
            "type": "capture_retrying",
            "commit_sha": "abc",
            "error": "capture failed",
        }
        await stream.aclose()

    asyncio.run(exercise())


def test_process_exception_is_safe_and_retryable(monkeypatch):
    monkeypatch.setattr(
        app_module,
        "capture_commit",
        lambda _: {"raw_event_id": "raw-1", "title": "Lead prompt", "source_tool": "git"},
    )

    def fail_process(_):
        raise RuntimeError("postgresql://admin:secret@db/internal")

    monkeypatch.setattr(app_module, "process_raw_event", fail_process)

    async def exercise():
        events.clear()
        response = await _request("POST", "/internal/capture", json={"commit_sha": "abc"})
        assert response.status_code == 202
        assert response.json() == {"embedded": False, "error": "capture failed"}
        stream = events.subscribe()
        assert (await anext(stream))["type"] == "capture_started"
        assert await anext(stream) == {
            "type": "capture_retrying",
            "commit_sha": "abc",
            "error": "capture failed",
        }
        await stream.aclose()

    asyncio.run(exercise())


def test_sse_endpoint_receives_event_published_during_subscription(monkeypatch):
    async def exercise():
        events.clear()
        response = app_module.lifecycle_events(once=True)
        line = asyncio.create_task(anext(response.body_iterator))
        await asyncio.sleep(0)
        await events.publish({"type": "capture_started", "commit_sha": "abc"})
        assert await asyncio.wait_for(line, timeout=1) == (
            'data: {"type": "capture_started", "commit_sha": "abc"}\n\n'
        )

    asyncio.run(exercise())
