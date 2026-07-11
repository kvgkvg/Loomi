from adapters.chat_adapter import capture_chat_export
from capture_pipeline.chat_process import process_chat_event
from db.client import get_pg_connection
from onboarding import assistant
from rationale.review import review_statement
from recommend import engine
import capture_pipeline.chat_process as chat_module
import rationale.review as review_module


class FakeCollection:
    def __init__(self): self.records = {}
    def upsert(self, *, ids, documents, metadatas): self.records[ids[0]] = {"document": documents[0], "metadata": metadatas[0]}
    def count(self): return len(self.records)
    def query(self, **kwargs):
        ids = list(self.records)
        return {"ids": [ids], "distances": [[0.1 for _ in ids]]}


def test_prompt_history_review_to_role_aware_reuse(isolated_runtime, monkeypatch):
    monkeypatch.setattr(chat_module, "extract_rationale_statements", lambda turns: [{
        "statement_type": "intent", "statement": "Prevent invalid JSON", "original_statement": "Prevent invalid JSON",
        "evidence_kind": "inferred", "confidence": 0.75, "source_turn_ids": [turns[-1]["id"]],
        "source_version_ids": [], "source_commit_ids": [], "alternative_explanation": "Style preference", "review_status": "pending",
    }])
    event = capture_chat_export({"uuid": "demo", "name": "JSON prompt", "chat_messages": [{"uuid": "m1", "sender": "human", "text": "Return JSON only"}]}, "claude")
    processed = process_chat_event(event["raw_event_id"])
    conn = get_pg_connection()
    conn.execute("INSERT INTO users (id, name) VALUES ('creator', 'Creator')")
    conn.commit(); conn.close()

    vectors = FakeCollection()
    monkeypatch.setattr(review_module, "get_vector_collection", lambda: vectors)
    reviewed = review_statement(processed["statement_ids"][0], "approve", "creator")
    assert reviewed["review_status"] == "approved"
    assert processed["asset_id"] in vectors.records

    monkeypatch.setattr(engine, "get_vector_collection", lambda: vectors)
    results = engine.recommend("avoid malformed structured output", role="Developer")
    assert results[0]["asset_id"] == processed["asset_id"]
    assert "role_reason" in results[0]

    monkeypatch.setattr(assistant, "_call_llm", lambda prompt: {"explanation": "Use JSON-only constraint", "cited_versions": [1], "cited_constraints": []})
    explanation = assistant.explain_asset(processed["asset_id"], role="Intern")
    assert explanation["role"] == "Intern"
    assert explanation["rationale_statements"][0]["review_status"] == "approved"


M1 = {"uuid": "m1", "sender": "human", "text": "Draft a formatter"}
M2 = {"uuid": "m2", "sender": "assistant", "text": "Here is a draft"}
M3 = {"uuid": "m3", "sender": "human", "text": "Return JSON only"}
M4 = {"uuid": "m4", "sender": "human", "text": "Also validate against the schema"}


def _reimport_event(*messages):
    payload = {"uuid": "conv-re", "name": "Reimport", "chat_messages": list(messages)}
    return capture_chat_export(payload, "claude")["raw_event_id"]


def _mock_statements(monkeypatch):
    monkeypatch.setattr(chat_module, "extract_rationale_statements", lambda turns, code_evidence=None: [{
        "statement_type": "intent", "statement": "Produce JSON", "original_statement": "Produce JSON",
        "evidence_kind": "observed", "confidence": 0.9, "source_turn_ids": [turns[-1]["id"]],
        "source_version_ids": [], "source_commit_ids": [], "alternative_explanation": None,
        "review_status": "pending",
    }])


def test_reimport_identical_conversation_is_noop(isolated_runtime, monkeypatch):
    _mock_statements(monkeypatch)
    event_id = _reimport_event(M1, M2)
    first = process_chat_event(event_id)

    assert _reimport_event(M1, M2) == event_id
    conn = get_pg_connection()
    assert conn.execute("SELECT processed FROM raw_events WHERE id = ?", (event_id,)).fetchone()[0] == 1
    conn.close()

    assert process_chat_event(event_id) == first
    conn = get_pg_connection()
    assert conn.execute("SELECT count(*) FROM asset_versions").fetchone()[0] == 1
    assert conn.execute("SELECT count(*) FROM conversation_turns").fetchone()[0] == 2
    conn.close()


def test_reimport_with_new_turns_creates_version_2(isolated_runtime, monkeypatch):
    _mock_statements(monkeypatch)
    event_id = _reimport_event(M1, M2)
    first = process_chat_event(event_id)

    assert _reimport_event(M1, M2, M3) == event_id
    conn = get_pg_connection()
    assert conn.execute("SELECT processed FROM raw_events WHERE id = ?", (event_id,)).fetchone()[0] == 0
    conn.close()

    second = process_chat_event(event_id)
    assert second["error"] is None
    assert second["asset_id"] == first["asset_id"]
    assert second["version_id"] != first["version_id"]

    conn = get_pg_connection()
    v1 = conn.execute("SELECT version_number, content FROM asset_versions WHERE id = ?", (first["version_id"],)).fetchone()
    v2 = conn.execute("SELECT version_number, content FROM asset_versions WHERE id = ?", (second["version_id"],)).fetchone()
    assert (v1["version_number"], v1["content"]) == (1, "Draft a formatter")
    assert (v2["version_number"], v2["content"]) == (2, "Return JSON only")
    assert conn.execute("SELECT count(*) FROM conversation_turns").fetchone()[0] == 3
    assert conn.execute("SELECT count(*) FROM rationale_statements WHERE version_id = ?", (second["version_id"],)).fetchone()[0] == 1
    assert conn.execute("SELECT count(*) FROM rationale_statements WHERE version_id = ?", (first["version_id"],)).fetchone()[0] == 1
    assert conn.execute("SELECT current_version_id FROM assets WHERE id = ?", (first["asset_id"],)).fetchone()[0] == second["version_id"]
    conn.close()


def test_repeated_reimports_increment_version_numbers(isolated_runtime, monkeypatch):
    _mock_statements(monkeypatch)
    event_id = _reimport_event(M1, M2)
    process_chat_event(event_id)
    _reimport_event(M1, M2, M3)
    v2 = process_chat_event(event_id)
    _reimport_event(M1, M2, M3, M4)
    v3 = process_chat_event(event_id)

    assert v3["error"] is None
    conn = get_pg_connection()
    numbers = [row[0] for row in conn.execute("SELECT version_number FROM asset_versions ORDER BY version_number")]
    assert numbers == [1, 2, 3]
    latest = conn.execute("SELECT content FROM asset_versions WHERE id = ?", (v3["version_id"],)).fetchone()
    assert latest["content"] == "Also validate against the schema"
    conn.close()


def test_v2_llm_failure_rolls_back_and_stays_retryable(isolated_runtime, monkeypatch):
    _mock_statements(monkeypatch)
    event_id = _reimport_event(M1, M2)
    first = process_chat_event(event_id)

    _reimport_event(M1, M2, M3)
    monkeypatch.setattr(chat_module, "extract_rationale_statements",
                        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("provider down")))
    failed = process_chat_event(event_id)
    assert failed["asset_id"] is None

    conn = get_pg_connection()
    assert conn.execute("SELECT processed FROM raw_events WHERE id = ?", (event_id,)).fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM asset_versions").fetchone()[0] == 1
    assert conn.execute("SELECT count(*) FROM conversation_turns").fetchone()[0] == 2
    conn.close()

    _mock_statements(monkeypatch)
    retried = process_chat_event(event_id)
    assert retried["error"] is None
    assert retried["version_id"] != first["version_id"]
