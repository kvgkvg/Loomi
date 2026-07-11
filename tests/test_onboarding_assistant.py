import json
import unittest
from unittest.mock import patch

from onboarding import assistant


class FakeCursor:
    def __init__(self, asset, versions, statements=()):
        self.asset = asset
        self.versions = versions
        self.statements = list(statements)
        self.result = None
        self.queries = []

    def execute(self, query, params=()):
        self.queries.append(query)
        if "FROM assets" in query:
            self.result = [self.asset] if self.asset is not None else []
        elif "FROM rationale_statements" in query:
            self.result = self.statements
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
    def __init__(self, asset, versions, statements=()):
        self.cursor_obj = FakeCursor(asset, versions, statements)

    def cursor(self):
        return self.cursor_obj

    def close(self):
        pass


def connection_for(asset=None, versions=(), statements=()):
    return FakeConnection(asset, list(versions), statements)


class OnboardingAssistantTests(unittest.TestCase):
    def test_valid_asset_returns_contract_and_filters_citations(self):
        asset = {"id": "a1", "title": "Lead agent", "type": "prompt"}
        versions = [
            {"version_number": 1, "content": "old", "diff_summary": "start", "problem": "slow", "constraints": ["JSON only"]},
            {"version_number": 2, "content": "new", "diff_summary": "fix", "problem": "fast", "constraints": ["JSON only", "no PII"]},
        ]
        model = {"explanation": "Grounded", "cited_versions": [2, 999], "cited_constraints": ["no PII", "invented"]}
        with patch.object(assistant, "get_pg_connection", return_value=connection_for(asset, versions)), patch.object(assistant, "_call_llm", return_value=model):
            result = assistant.explain_asset("a1")
        self.assertEqual(result, {"explanation": "Grounded", "cited_versions": [2], "cited_constraints": ["no PII"]})

    def test_optional_question_is_passed_to_llm_prompt(self):
        asset = {"id": "a1", "title": "Lead agent", "type": "prompt"}
        with patch.object(assistant, "get_pg_connection", return_value=connection_for(asset)), patch.object(assistant, "_call_llm", return_value={"explanation": "ok", "cited_versions": [], "cited_constraints": []}) as call:
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

    def test_llm_failure_is_safe(self):
        asset = {"id": "a1", "title": "Lead agent", "type": "prompt"}
        with patch.object(assistant, "get_pg_connection", return_value=connection_for(asset)), patch.object(assistant, "_call_llm", side_effect=RuntimeError("quota secret")):
            result = assistant.explain_asset("a1")
        self.assertEqual(result["cited_constraints"], [])
        self.assertNotIn("quota secret", result["explanation"])

    def test_empty_model_explanation_is_treated_as_failure(self):
        asset = {"id": "a1", "title": "Lead agent", "type": "prompt"}
        empty = {"explanation": "", "cited_versions": [], "cited_constraints": []}
        with patch.object(assistant, "get_pg_connection", return_value=connection_for(asset)), patch.object(assistant, "_call_llm", return_value=empty):
            result = assistant.explain_asset("a1")
        self.assertEqual(result, {"explanation": "unable to generate explanation", "cited_versions": [], "cited_constraints": []})

    def test_llm_boundary_posts_prompt_and_parses_response(self):
        captured = {}

        class FakeCompletions:
            def create(self, *, model, temperature, messages):
                captured["model"] = model
                captured["messages"] = messages

                class Msg:
                    content = json.dumps(
                        {"explanation": "ok", "cited_versions": [], "cited_constraints": []}
                    )

                class Choice:
                    message = Msg()

                class Resp:
                    choices = [Choice()]

                return Resp()

        class FakeChat:
            completions = FakeCompletions()

        class FakeClient:
            def __init__(self, *, base_url, api_key):
                captured["base_url"] = base_url
                captured["api_key"] = api_key
                self.chat = FakeChat()

        with patch.dict(
            "os.environ", {"FEATHERLESS_API_KEY": "test-key", "FEATHERLESS_MODEL": "test-model"}
        ):
            result = assistant._call_llm("evidence prompt", client_factory=FakeClient)

        self.assertEqual(captured["base_url"], assistant.FEATHERLESS_BASE_URL)
        self.assertEqual(captured["model"], "test-model")
        self.assertIn("evidence prompt", captured["messages"][-1]["content"])
        self.assertEqual(result["explanation"], "ok")

    def test_malformed_llm_response_is_safe_at_public_boundary(self):
        asset = {"id": "a1", "title": "Lead agent", "type": "prompt"}
        with patch.object(assistant, "get_pg_connection", return_value=connection_for(asset)), patch.object(assistant, "_call_llm", side_effect=ValueError("provider payload")):
            result = assistant.explain_asset("a1")
        self.assertEqual(result, {"explanation": "unable to generate explanation", "cited_versions": [], "cited_constraints": []})

    def test_role_aware_explanation_loads_only_trusted_rationale(self):
        asset = {"id": "a1", "title": "Lead agent", "type": "prompt"}
        statements = [{"statement_type": "intent", "statement": "Reduce risk", "evidence_kind": "inferred", "confidence": 0.7, "review_status": "approved"}]
        connection = connection_for(asset, statements=statements)
        model = {"explanation": "Manager summary", "cited_versions": [], "cited_constraints": []}
        lens = {"role": "Manager", "detail_level": "summary", "explanation_style": "outcomes", "primary_actions": ["view owner"], "goals": [], "ranking_weights": {"role": 0.1}}
        with patch.object(assistant, "get_pg_connection", return_value=connection), patch.object(assistant, "resolve_role_lens", return_value=lens), patch.object(assistant, "_call_llm", return_value=model) as call:
            result = assistant.explain_asset("a1", role="Manager")

        self.assertEqual(result["role"], "Manager")
        self.assertEqual(result["primary_actions"], ["view owner"])
        self.assertEqual(result["rationale_statements"][0]["statement"], "Reduce risk")
        self.assertIn("Manager", call.call_args.args[0])
        statement_query = next(query for query in connection.cursor_obj.queries if "FROM rationale_statements" in query)
        self.assertIn("approved", statement_query)
        self.assertIn("edited", statement_query)


if __name__ == "__main__":
    unittest.main()
