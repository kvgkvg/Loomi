from adapters.chat_adapter import capture_chat_export
from capture_pipeline.chat_process import process_chat_event
from db.client import get_pg_connection
import capture_pipeline.chat_process as module


STATEMENTS = [{
    "statement_type": "intent",
    "statement": "Produce JSON",
    "original_statement": "Produce JSON",
    "evidence_kind": "observed",
    "confidence": 0.9,
    "source_turn_ids": [],
    "source_version_ids": [],
    "source_commit_ids": [],
    "alternative_explanation": None,
    "review_status": "pending",
}]


def _event():
    return capture_chat_export({
        "uuid": "conv-1",
        "name": "JSON formatter",
        "chat_messages": [
            {"uuid": "m1", "sender": "human", "text": "Draft formatter"},
            {"uuid": "m2", "sender": "assistant", "text": "Draft"},
            {"uuid": "m3", "sender": "human", "text": "Return JSON only"},
        ],
    }, "claude")["raw_event_id"]


def test_process_persists_pending_history_without_embedding(isolated_runtime, monkeypatch):
    event_id = _event()
    monkeypatch.setattr(module, "extract_rationale_statements", lambda turns, code_evidence=None: [dict(STATEMENTS[0], source_turn_ids=[turns[-1]["id"]])])
    monkeypatch.setattr(module, "get_vector_collection", lambda: (_ for _ in ()).throw(AssertionError("must not embed pending rationale")))

    result = process_chat_event(event_id)

    assert result["review_status"] == "pending"
    conn = get_pg_connection()
    assert conn.execute("SELECT count(*) FROM conversations").fetchone()[0] == 1
    assert conn.execute("SELECT count(*) FROM conversation_turns").fetchone()[0] == 3
    statement = conn.execute("SELECT review_status FROM rationale_statements").fetchone()
    assert statement["review_status"] == "pending"
    asset = conn.execute("SELECT source_tool FROM assets").fetchone()
    assert asset["source_tool"] == "claude"


def test_process_is_idempotent(isolated_runtime, monkeypatch):
    event_id = _event()
    monkeypatch.setattr(module, "extract_rationale_statements", lambda turns, code_evidence=None: [dict(STATEMENTS[0], source_turn_ids=[turns[-1]["id"]])])

    first = process_chat_event(event_id)
    second = process_chat_event(event_id)

    assert second == first
    conn = get_pg_connection()
    assert conn.execute("SELECT count(*) FROM asset_versions").fetchone()[0] == 1
    assert conn.execute("SELECT count(*) FROM rationale_statements").fetchone()[0] == 1


def test_llm_failure_keeps_event_retryable(isolated_runtime, monkeypatch):
    event_id = _event()
    monkeypatch.setattr(module, "extract_rationale_statements", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("provider")))

    result = process_chat_event(event_id)

    assert result["asset_id"] is None
    conn = get_pg_connection()
    assert conn.execute("SELECT processed FROM raw_events WHERE id = ?", (event_id,)).fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM conversations").fetchone()[0] == 0
