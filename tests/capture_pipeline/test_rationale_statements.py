import json
from types import SimpleNamespace

import pytest

from capture_pipeline.rationale_statements import RationaleStatementsError, extract_rationale_statements


class FakeOpenAI:
    def __init__(self, content):
        self.content = content
        self.request = None

    def factory(self, **kwargs):
        return self

    @property
    def chat(self):
        return SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **request):
        self.request = request
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))])


def _payload(**overrides):
    statement = {
        "statement_type": "intent",
        "statement": "Return valid JSON",
        "evidence_kind": "observed",
        "confidence": 0.9,
        "source_turn_ids": ["t1"],
        "source_version_ids": [],
        "source_commit_ids": [],
        "alternative_explanation": None,
    }
    statement.update(overrides)
    return json.dumps({"statements": [statement]})


def test_extracts_observed_and_inferred_statements(monkeypatch):
    fake = FakeOpenAI(_payload())
    monkeypatch.setenv("FEATHERLESS_API_KEY", "test")

    result = extract_rationale_statements([{"id": "t1", "role": "user", "content": "JSON required"}], client_factory=fake.factory)

    assert result[0]["evidence_kind"] == "observed"
    assert result[0]["review_status"] == "pending"


def test_redacts_secret_before_llm(monkeypatch):
    fake = FakeOpenAI(_payload())
    monkeypatch.setenv("FEATHERLESS_API_KEY", "test")

    extract_rationale_statements([{"id": "t1", "role": "user", "content": "sk-secretvalue123456"}], client_factory=fake.factory)

    assert "sk-secretvalue" not in fake.request["messages"][-1]["content"]
    assert "[REDACTED]" in fake.request["messages"][-1]["content"]


@pytest.mark.parametrize(
    "payload",
    [
        _payload(evidence_kind="guess"),
        _payload(confidence=1.2),
        _payload(source_turn_ids=["missing"]),
        _payload(statement_type="unknown"),
    ],
)
def test_rejects_invalid_or_unresolvable_statements(payload, monkeypatch):
    monkeypatch.setenv("FEATHERLESS_API_KEY", "test")
    with pytest.raises(RationaleStatementsError):
        extract_rationale_statements([{"id": "t1", "role": "user", "content": "x"}], client_factory=FakeOpenAI(payload).factory)


def test_accepts_json_fence_and_inferred_alternative(monkeypatch):
    payload = _payload(evidence_kind="inferred", confidence=0.4, alternative_explanation="Could be formatting preference")
    monkeypatch.setenv("FEATHERLESS_API_KEY", "test")

    result = extract_rationale_statements([{"id": "t1", "role": "user", "content": "x"}], client_factory=FakeOpenAI(f"```json\n{payload}\n```").factory)

    assert result[0]["alternative_explanation"] == "Could be formatting preference"
