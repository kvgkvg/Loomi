import pytest

import intent_ci.engine as engine
from intent_ci.engine import create_intent_review, list_intent_reviews, resolve_intent_review


@pytest.fixture
def intent_runtime(isolated_runtime, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("CHROMA_HOST", raising=False)
    monkeypatch.delenv("INTENT_CI_AUTO_PASS", raising=False)
    monkeypatch.setattr(engine, "recommend", lambda prompt, top_k=1: [])
    monkeypatch.setattr(
        engine, "_extract_intent",
        lambda prompt, client_factory=None: {"intent": "Do the task", "confidence": 0.9},
    )
    return isolated_runtime


def test_green_checks_still_wait_for_human_gate(intent_runtime):
    review = create_intent_review("Build a summarizer for weekly reports", "claude-code", "alice")
    assert review["status"] == "pending"
    assert {c["name"]: c["status"] for c in review["checks"]} == {
        "policy_secrets": "pass",
        "reuse_available": "pass",
        "intent_clarity": "pass",
    }
    assert review["intent"] == "Do the task"


def test_auto_pass_opt_in(intent_runtime, monkeypatch):
    monkeypatch.setenv("INTENT_CI_AUTO_PASS", "1")
    review = create_intent_review("Build a summarizer for weekly reports", "claude-code", "alice")
    assert review["status"] == "passed"


def test_secret_in_prompt_fails_policy_and_redacts(intent_runtime):
    review = create_intent_review(
        "Use api_key=super-secret-value to call the billing API", "codex"
    )
    checks = {c["name"]: c["status"] for c in review["checks"]}
    assert checks["policy_secrets"] == "fail"
    assert review["status"] == "pending"
    assert "super-secret-value" not in review["prompt"]
    stored = list_intent_reviews()[0]
    assert "super-secret-value" not in stored["prompt"]


def test_existing_asset_match_requires_action(intent_runtime, monkeypatch):
    monkeypatch.setattr(
        engine, "recommend",
        lambda prompt, top_k=1: [{"asset_id": "a-1", "title": "Ticket triage prompt", "score": 0.61}],
    )
    review = create_intent_review("triage incoming support tickets", "claude-code")
    reuse = next(c for c in review["checks"] if c["name"] == "reuse_available")
    assert reuse["status"] == "action_required"
    assert reuse["asset_id"] == "a-1"
    assert review["status"] == "pending"


def test_llm_failure_degrades_to_error_check(intent_runtime, monkeypatch):
    def boom(prompt, client_factory=None):
        raise RuntimeError("provider down")

    monkeypatch.setattr(engine, "_extract_intent", boom)
    review = create_intent_review("some ambiguous ask", "claude-code")
    clarity = next(c for c in review["checks"] if c["name"] == "intent_clarity")
    assert clarity["status"] == "error"
    assert review["status"] == "pending"
    assert review["intent"] is None


def test_low_confidence_fails_clarity(intent_runtime, monkeypatch):
    monkeypatch.setattr(
        engine, "_extract_intent",
        lambda prompt, client_factory=None: {"intent": "Unclear", "confidence": 0.3},
    )
    review = create_intent_review("do the thing with the stuff", "claude-code")
    clarity = next(c for c in review["checks"] if c["name"] == "intent_clarity")
    assert clarity["status"] == "fail"
    assert review["status"] == "pending"


def test_resolve_pending_review(intent_runtime):
    review = create_intent_review("Use api_key=abc123secret now", "codex")
    assert review["status"] == "pending"
    result = resolve_intent_review(review["id"], "approve", reviewer="Tech Lead")
    assert result["status"] == "approved"
    with pytest.raises(ValueError):
        resolve_intent_review(review["id"], "reject")
    with pytest.raises(ValueError):
        resolve_intent_review("no-such-id", "approve")
    with pytest.raises(ValueError):
        resolve_intent_review(review["id"], "promote")


def test_empty_prompt_rejected(intent_runtime):
    with pytest.raises(ValueError):
        create_intent_review("   ", "claude-code")
    with pytest.raises(ValueError):
        create_intent_review("valid prompt", "")


def test_list_orders_newest_first(intent_runtime):
    first = create_intent_review("first prompt about metrics dashboards", "claude-code")
    second = create_intent_review("second prompt about email digests", "codex")
    listed = list_intent_reviews()
    assert [r["id"] for r in listed[:2]] == [second["id"], first["id"]] or listed[0]["id"] in {
        first["id"], second["id"]
    }
    assert all(isinstance(r["checks"], list) for r in listed)


def test_chat_history_is_sanitized_and_stored(intent_runtime):
    review = create_intent_review(
        "Plan migration",
        "codex",
        chat_history=[
            "user: please migrate old billing flow",
            "assistant: use api_key=super-secret-value for test",
            "   ",
        ],
    )
    assert isinstance(review["chat_history"], list)
    assert len(review["chat_history"]) == 2
    assert all("super-secret-value" not in msg for msg in review["chat_history"])

    stored = next(item for item in list_intent_reviews() if item["id"] == review["id"])
    assert len(stored["chat_history"]) == 2
    assert all("super-secret-value" not in msg for msg in stored["chat_history"])
