import json
from types import SimpleNamespace

from role_lens.lens import clear_role_lens_cache, resolve_role_lens


class FakeOpenAI:
    def __init__(self, payload): self.payload = payload; self.calls = 0
    def factory(self, **kwargs): return self
    @property
    def chat(self): return SimpleNamespace(completions=SimpleNamespace(create=self.create))
    def create(self, **kwargs):
        self.calls += 1
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(self.payload)))])


def setup_function(): clear_role_lens_cache()


def test_presets_are_deterministic_without_api_key(monkeypatch):
    monkeypatch.delenv("FEATHERLESS_API_KEY", raising=False)
    intern = resolve_role_lens("Intern")
    manager = resolve_role_lens("Manager")
    assert intern["detail_level"] == "guided"
    assert manager["detail_level"] == "summary"


def test_custom_role_uses_validated_llm_and_cache(monkeypatch):
    monkeypatch.setenv("FEATHERLESS_API_KEY", "test")
    fake = FakeOpenAI({"role": "QA", "goals": ["risk"], "detail_level": "technical", "ranking_weights": {"role": 0.15}, "explanation_style": "evidence", "primary_actions": ["verify"]})
    first = resolve_role_lens("QA", client_factory=fake.factory)
    second = resolve_role_lens("qa", client_factory=fake.factory)
    assert first == second
    assert fake.calls == 1


def test_invalid_weight_falls_back_to_developer(monkeypatch):
    monkeypatch.setenv("FEATHERLESS_API_KEY", "test")
    fake = FakeOpenAI({"role": "QA", "goals": [], "detail_level": "x", "ranking_weights": {"role": 3}, "explanation_style": "x", "primary_actions": []})
    result = resolve_role_lens("QA", client_factory=fake.factory)
    assert result["role"] == "Developer"
    assert result["fallback"] is True
