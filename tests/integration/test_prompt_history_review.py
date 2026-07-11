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
