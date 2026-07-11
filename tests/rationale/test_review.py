import pytest

from adapters.chat_adapter import capture_chat_export
from capture_pipeline.chat_process import process_chat_event
from db.client import get_pg_connection
from rationale.review import ReviewError, ensure_reviewer, list_pending_statements, review_statement
import capture_pipeline.chat_process as chat_module
import rationale.review as review_module


class FakeCollection:
    def __init__(self): self.records = {}
    def upsert(self, *, ids, documents, metadatas): self.records[ids[0]] = {"document": documents[0], "metadata": metadatas[0]}


@pytest.fixture
def pending(isolated_runtime, monkeypatch):
    monkeypatch.setattr(chat_module, "extract_rationale_statements", lambda turns: [{
        "statement_type": "intent", "statement": "Return valid JSON", "original_statement": "Return valid JSON",
        "evidence_kind": "inferred", "confidence": 0.7, "source_turn_ids": [turns[0]["id"]],
        "source_version_ids": [], "source_commit_ids": [], "alternative_explanation": "Formatting preference", "review_status": "pending",
    }])
    event = capture_chat_export({"uuid": "r1", "chat_messages": [{"uuid": "m1", "sender": "human", "text": "JSON only"}]}, "claude")
    result = process_chat_event(event["raw_event_id"])
    conn = get_pg_connection()
    conn.execute("INSERT INTO users (id, name) VALUES ('reviewer', 'Reviewer')")
    conn.commit(); conn.close()
    return result


def test_approve_promotes_trusted_summary_and_vector(pending, monkeypatch):
    collection = FakeCollection()
    monkeypatch.setattr(review_module, "get_vector_collection", lambda: collection)

    result = review_statement(pending["statement_ids"][0], "approve", "reviewer")

    assert result["review_status"] == "approved"
    conn = get_pg_connection()
    assert conn.execute("SELECT confidence FROM rationale").fetchone()[0] == "user_provided"
    assert pending["asset_id"] in collection.records


def test_edit_preserves_original_and_reject_never_embeds(pending, monkeypatch):
    collection = FakeCollection()
    monkeypatch.setattr(review_module, "get_vector_collection", lambda: collection)

    edited = review_statement(pending["statement_ids"][0], "edit", "reviewer", edited_statement="Return strict JSON")

    assert edited["review_status"] == "edited"
    conn = get_pg_connection()
    row = conn.execute("SELECT statement, original_statement FROM rationale_statements").fetchone()
    assert tuple(row) == ("Return strict JSON", "Return valid JSON")


def test_reject_excludes_statement_from_vector(pending, monkeypatch):
    collection = FakeCollection()
    monkeypatch.setattr(review_module, "get_vector_collection", lambda: collection)

    result = review_statement(pending["statement_ids"][0], "reject", "reviewer", note="wrong")

    assert result["review_status"] == "rejected"
    assert collection.records == {}
    conn = get_pg_connection()
    assert conn.execute("SELECT count(*) FROM rationale").fetchone()[0] == 0


def test_invalid_transition_is_rejected(pending, monkeypatch):
    monkeypatch.setattr(review_module, "get_vector_collection", lambda: FakeCollection())
    review_statement(pending["statement_ids"][0], "approve", "reviewer")

    with pytest.raises(ReviewError):
        review_statement(pending["statement_ids"][0], "reject", "reviewer")


def test_pending_queue_contains_evidence_and_excludes_reviewed(pending, monkeypatch):
    monkeypatch.setattr(review_module, "get_vector_collection", lambda: FakeCollection())
    queue = list_pending_statements()
    assert queue[0]["statement"] == "Return valid JSON"
    assert queue[0]["source_turns"][0]["content"] == "JSON only"

    review_statement(pending["statement_ids"][0], "reject", "reviewer")
    assert list_pending_statements() == []


def test_ensure_reviewer_creates_idempotent_attribution_user(isolated_runtime):
    first = ensure_reviewer("Alice")
    second = ensure_reviewer(" Alice ")
    assert first == second
    conn = get_pg_connection()
    assert conn.execute("SELECT name FROM users WHERE id = ?", (first,)).fetchone()[0] == "Alice"


def test_ensure_reviewer_rejects_empty_name(isolated_runtime):
    with pytest.raises(ReviewError):
        ensure_reviewer("  ")
