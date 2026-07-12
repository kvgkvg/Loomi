from __future__ import annotations

import json
import uuid

import pytest

from db.client import get_pg_connection
from capture_pipeline.process import process_raw_event
import capture_pipeline.process as process_module


RATIONALE = {
    "problem": "Reduce misroutes",
    "failed_attempts": ["Keyword-only routing"],
    "constraints": ["Return one queue"],
    "confidence": "auto",
}


class FakeCollection:
    """Stand-in for the Chroma collection. Embeddings are Chroma-managed now,
    so upsert takes documents (no explicit embeddings)."""

    def __init__(self):
        self.records = {}

    def upsert(self, *, ids, documents, metadatas):
        for index, item_id in enumerate(ids):
            self.records[item_id] = {
                "document": documents[index],
                "metadata": metadatas[index],
            }

    def get(self, *, ids):
        return {"ids": [item_id for item_id in ids if item_id in self.records]}


@pytest.fixture
def fake_services(monkeypatch):
    collection = FakeCollection()
    monkeypatch.setattr(process_module, "extract_rationale", lambda content, signal: RATIONALE.copy())
    monkeypatch.setattr(process_module, "get_vector_collection", lambda: collection)
    return collection


def _insert_event(*, paths=None, title="add support prompt", content="Route tickets"):
    event_id = str(uuid.uuid4())
    signal = json.dumps(
        {
            "repository_root": "/tmp/example-repo",
            "commit_sha": uuid.uuid4().hex,
            "paths": paths or ["prompts/support.md"],
            "diff": "+ Route tickets",
        }
    )
    conn = get_pg_connection()
    conn.execute(
        """
        INSERT INTO raw_events (id, source_tool, title, content, raw_signal, processed)
        VALUES (?, 'git', ?, ?, ?, 0)
        """,
        (event_id, title, content, signal),
    )
    conn.commit()
    conn.close()
    return event_id


def test_process_creates_pending_review_with_draft_embedding(isolated_runtime, fake_services):
    raw_event = _insert_event()

    result = process_raw_event(raw_event)

    assert result["rationale"] == RATIONALE
    assert result["embedded"] is False
    assert result["draft_embedded"] is True
    assert result["review_status"] == "pending"
    assert len(result["statement_ids"]) == 3
    collection = fake_services
    record = collection.records[result["asset_id"]]
    assert record["document"] == "Route tickets\n\nProblem: Reduce misroutes"
    assert record["metadata"] == {
        "asset_id": result["asset_id"],
        "version_id": result["version_id"],
        "source_tool": "git",
        "review_status": "pending",
    }
    conn = get_pg_connection()
    event = conn.execute(
        "SELECT processed, processed_asset_version_id FROM raw_events WHERE id = ?",
        (raw_event,),
    ).fetchone()
    assert event["processed"] == 0
    assert event["processed_asset_version_id"] == result["version_id"]
    assert conn.execute("SELECT count(*) FROM rationale").fetchone()[0] == 0
    assert conn.execute(
        "SELECT count(*) FROM rationale_statements WHERE review_status = 'pending'"
    ).fetchone()[0] == 3


def test_process_is_idempotent_while_review_pending(isolated_runtime, fake_services):
    raw_event = _insert_event()

    first = process_raw_event(raw_event)
    second = process_raw_event(raw_event)

    assert second == first
    conn = get_pg_connection()
    assert conn.execute("SELECT count(*) FROM asset_versions").fetchone()[0] == 1
    assert conn.execute("SELECT count(*) FROM rationale_statements").fetchone()[0] == 3


def test_later_commit_appends_version(isolated_runtime, fake_services):
    first_event = _insert_event(content="Route tickets v1")
    second_event = _insert_event(content="Route tickets v2")
    first = process_raw_event(first_event)

    second = process_raw_event(second_event)

    assert second["asset_id"] == first["asset_id"]
    conn = get_pg_connection()
    row = conn.execute(
        "SELECT version_number FROM asset_versions WHERE id = ?",
        (second["version_id"],),
    ).fetchone()
    assert row["version_number"] == 2


def test_llm_failure_keeps_event_retryable(isolated_runtime, monkeypatch):
    raw_event = _insert_event()
    monkeypatch.setattr(
        process_module,
        "extract_rationale",
        lambda content, signal: (_ for _ in ()).throw(RuntimeError("provider failed")),
    )

    result = process_raw_event(raw_event)

    assert result["embedded"] is False
    assert result["asset_id"] is None
    assert result["version_id"] is None
    assert "error" in result
    conn = get_pg_connection()
    assert conn.execute(
        "SELECT processed FROM raw_events WHERE id = ?", (raw_event,)
    ).fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM assets").fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM asset_versions").fetchone()[0] == 0


def test_missing_event_returns_retryable_error(isolated_runtime):
    result = process_raw_event("missing")

    assert result["embedded"] is False
    assert result["error"] == "Raw event not found"
