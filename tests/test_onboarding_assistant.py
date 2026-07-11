import json
import unittest
from unittest.mock import patch

from onboarding import assistant


class FakeCursor:
    def __init__(self, asset, versions):
        self.asset = asset
        self.versions = versions
        self.result = None

    def execute(self, query, params=()):
        if "FROM assets" in query:
            self.result = [self.asset] if self.asset is not None else []
        elif "FROM asset_versions" in query:
            self.result = self.versions
        else:
            raise AssertionError(f"unexpected query: {query}")

    def fetchone(self):
        return self.result[0] if self.result else None

    def fetchall(self):
        return self.result

    def close(self):
        pass


class FakeConnection:
    def __init__(self, asset, versions):
        self.cursor_obj = FakeCursor(asset, versions)

    def cursor(self):
        return self.cursor_obj

    def close(self):
        pass


def connection_for(asset=None, versions=()):
    return FakeConnection(asset, list(versions))


class OnboardingAssistantTests(unittest.TestCase):
    def test_valid_asset_returns_contract_and_filters_citations(self):
        asset = {"id": "a1", "title": "Lead agent", "type": "prompt"}
        versions = [
            {"version_number": 1, "content": "old", "diff_summary": "start", "problem": "slow", "constraints": ["JSON only"]},
            {"version_number": 2, "content": "new", "diff_summary": "fix", "problem": "fast", "constraints": ["JSON only", "no PII"]},
        ]
        model = {"explanation": "Grounded", "cited_versions": [2, 999], "cited_constraints": ["no PII", "invented"]}
        with patch.object(assistant, "get_pg_connection", return_value=connection_for(asset, versions)), patch.object(assistant, "_call_gemini", return_value=model):
            result = assistant.explain_asset("a1")
        self.assertEqual(result, {"explanation": "Grounded", "cited_versions": [2], "cited_constraints": ["no PII"]})

    def test_optional_question_is_passed_to_gemini_prompt(self):
        asset = {"id": "a1", "title": "Lead agent", "type": "prompt"}
        with patch.object(assistant, "get_pg_connection", return_value=connection_for(asset)), patch.object(assistant, "_call_gemini", return_value={"explanation": "ok", "cited_versions": [], "cited_constraints": []}) as call:
            assistant.explain_asset("a1", "Why JSON?")
        self.assertIn("Why JSON?", call.call_args.args[0])

    def test_invalid_input_and_dependency_errors_are_safe(self):
        self.assertEqual(assistant.explain_asset(""), {"explanation": "asset_id must be a non-empty string", "cited_versions": [], "cited_constraints": []})
        with patch.object(assistant, "get_pg_connection", side_effect=RuntimeError("db secret")):
            result = assistant.explain_asset("a1")
        self.assertEqual(result["cited_versions"], [])
        self.assertNotIn("db secret", result["explanation"])

    def test_missing_asset_returns_safe_result(self):
        with patch.object(assistant, "get_pg_connection", return_value=connection_for()):
            result = assistant.explain_asset("missing")
        self.assertEqual(result, {"explanation": "asset not found", "cited_versions": [], "cited_constraints": []})

    def test_gemini_failure_is_safe(self):
        asset = {"id": "a1", "title": "Lead agent", "type": "prompt"}
        with patch.object(assistant, "get_pg_connection", return_value=connection_for(asset)), patch.object(assistant, "_call_gemini", side_effect=RuntimeError("quota secret")):
            result = assistant.explain_asset("a1")
        self.assertEqual(result["cited_constraints"], [])
        self.assertNotIn("quota secret", result["explanation"])

    def test_empty_model_explanation_is_treated_as_failure(self):
        asset = {"id": "a1", "title": "Lead agent", "type": "prompt"}
        empty = {"explanation": "", "cited_versions": [], "cited_constraints": []}
        with patch.object(assistant, "get_pg_connection", return_value=connection_for(asset)), patch.object(assistant, "_call_gemini", return_value=empty):
            result = assistant.explain_asset("a1")
        self.assertEqual(result, {"explanation": "unable to generate explanation", "cited_versions": [], "cited_constraints": []})

    def test_gemini_boundary_posts_json_and_parses_response(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def read(self):
                return json.dumps({"candidates": [{"content": {"parts": [{"text": json.dumps({"explanation": "ok", "cited_versions": [], "cited_constraints": []})}]}}]}).encode()

        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key", "GEMINI_MODEL": "test-model"}), patch.object(assistant.urllib.request, "urlopen", return_value=FakeResponse()) as open_url:
            result = assistant._call_gemini("evidence prompt")
        request = open_url.call_args.args[0]
        self.assertIn("test-model", request.full_url)
        self.assertNotIn("test-key", json.loads(request.data.decode())["contents"][0]["parts"][0]["text"])
        self.assertEqual(result["explanation"], "ok")

    def test_malformed_gemini_response_is_safe_at_public_boundary(self):
        asset = {"id": "a1", "title": "Lead agent", "type": "prompt"}
        with patch.object(assistant, "get_pg_connection", return_value=connection_for(asset)), patch.object(assistant, "_call_gemini", side_effect=ValueError("provider payload")):
            result = assistant.explain_asset("a1")
        self.assertEqual(result, {"explanation": "unable to generate explanation", "cited_versions": [], "cited_constraints": []})


if __name__ == "__main__":
    unittest.main()
