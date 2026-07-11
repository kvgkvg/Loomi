from types import SimpleNamespace

import pytest

from capture_pipeline.llm import RationaleError, extract_rationale


class FakeOpenAI:
    def __init__(self, content=None, error=None):
        self.content = content
        self.error = error
        self.base_url = None
        self.api_key = None
        self.request = None

    def factory(self, *, base_url, api_key):
        self.base_url = base_url
        self.api_key = api_key
        return self

    @property
    def chat(self):
        return SimpleNamespace(
            completions=SimpleNamespace(create=self._create),
        )

    def _create(self, **request):
        self.request = request
        if self.error:
            raise self.error
        message = SimpleNamespace(content=self.content)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


VALID = (
    '{"problem":"Reduce misroutes","failed_attempts":[],"constraints":'
    '["JSON only"],"confidence":"auto"}'
)


def test_extract_rationale_uses_required_endpoint_and_model(monkeypatch):
    fake = FakeOpenAI(VALID)
    monkeypatch.setenv("FEATHERLESS_API_KEY", "test-key")

    result = extract_rationale("prompt", "diff", client_factory=fake.factory)

    assert fake.base_url == "https://api.featherless.ai/v1"
    assert fake.api_key == "test-key"
    assert fake.request["model"] == "zai-org/GLM-5.2"
    assert fake.request["temperature"] == 0.1
    assert result["problem"] == "Reduce misroutes"


def test_extract_rationale_accepts_one_json_fence(monkeypatch):
    fake = FakeOpenAI(f"```json\n{VALID}\n```")
    monkeypatch.setenv("FEATHERLESS_API_KEY", "test-key")

    result = extract_rationale("prompt", "diff", client_factory=fake.factory)

    assert result["constraints"] == ["JSON only"]


@pytest.mark.parametrize(
    "content",
    [
        "not json",
        '{"problem":3,"failed_attempts":[],"constraints":[],"confidence":"auto"}',
        '{"problem":"x","failed_attempts":[1],"constraints":[],"confidence":"auto"}',
        '{"problem":"x","failed_attempts":[],"constraints":[],"confidence":"guess"}',
    ],
)
def test_extract_rationale_rejects_invalid_payload(content, monkeypatch):
    monkeypatch.setenv("FEATHERLESS_API_KEY", "test-key")

    with pytest.raises(RationaleError):
        extract_rationale("prompt", "diff", client_factory=FakeOpenAI(content).factory)


def test_extract_rationale_sanitizes_sdk_error(monkeypatch):
    secret = "runtime-secret-value"
    monkeypatch.setenv("FEATHERLESS_API_KEY", secret)
    fake = FakeOpenAI(error=RuntimeError(f"request rejected for {secret}"))

    with pytest.raises(RationaleError) as caught:
        extract_rationale("prompt", "diff", client_factory=fake.factory)

    assert secret not in str(caught.value)


def test_extract_rationale_requires_api_key(monkeypatch):
    monkeypatch.delenv("FEATHERLESS_API_KEY", raising=False)

    with pytest.raises(RationaleError, match="FEATHERLESS_API_KEY is not set"):
        extract_rationale("prompt", "diff", client_factory=FakeOpenAI(VALID).factory)
