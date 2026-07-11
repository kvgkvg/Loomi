# Grounded Onboarding Assistant Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `explain_asset()` with Gemini Free Tier, database grounding, citation validation, and safe failure results.

**Architecture:** `onboarding/assistant.py` loads one asset and its ordered versions/rationale through the shared DB client, builds a bounded evidence prompt, calls Gemini's REST endpoint, then validates the JSON and citations. External boundaries are injectable in tests; the public function signature remains fixed.

**Tech Stack:** Python 3.10+, standard library `urllib`/`json`/`unittest`, team DB-API client, Gemini Developer API free tier.

## Global Constraints

- Use `GEMINI_API_KEY` and configurable `GEMINI_MODEL`; never commit secrets.
- Default model is `gemini-3.1-flash-lite`.
- Use only `db/client.py` for database access.
- Return exactly `explanation`, `cited_versions`, and `cited_constraints`.
- Never raise for invalid input, missing data, DB/API errors, quota errors, or malformed model output.
- Do not add an SDK, UI, retry loop, Chroma query, schema change, or deterministic synthesis fallback.
- Run each new test red before the implementation that makes it green.

---

### Task 1: Package and contract tests

**Files:**
- Create: `onboarding/__init__.py`
- Create: `tests/__init__.py`
- Test: `tests/test_onboarding_assistant.py`

**Interfaces:**
- Consumes: no production implementation; tests import `onboarding.assistant.explain_asset`.
- Produces: executable contract tests and patch points for a DB connection and Gemini request.

- [ ] **Step 1: Write the failing tests**

```python
import json
import unittest
from unittest.mock import patch

from onboarding import assistant


class FakeCursor:
    def __init__(self, rows):
        self.rows = iter(rows)
        self.last_query = ""

    def execute(self, query, params=()):
        self.last_query = query
        self.current = next(self.rows)

    def fetchone(self):
        return self.current[0] if self.current else None

    def fetchall(self):
        return self.current[1]

    def close(self):
        pass


class FakeConnection:
    def __init__(self, asset, versions):
        self.cursor_obj = FakeCursor([(asset, versions)])

    def cursor(self):
        return self.cursor_obj

    def close(self):
        pass


class OnboardingAssistantTests(unittest.TestCase):
    def test_valid_asset_returns_contract_and_filters_citations(self):
        asset = {"id": "a1", "title": "Lead agent", "type": "prompt"}
        versions = [
            {"version_number": 1, "content": "old", "diff_summary": "start", "problem": "slow", "constraints": ["JSON only"]},
            {"version_number": 2, "content": "new", "diff_summary": "fix", "problem": "fast", "constraints": ["JSON only", "no PII"]},
        ]
        model = {"explanation": "Grounded", "cited_versions": [2, 999], "cited_constraints": ["no PII", "invented"]}
        with patch.object(assistant, "get_pg_connection", return_value=FakeConnection(asset, versions)), patch.object(assistant, "_call_gemini", return_value=model):
            result = assistant.explain_asset("a1")
        self.assertEqual(result, {"explanation": "Grounded", "cited_versions": [2], "cited_constraints": ["no PII"]})

    def test_optional_question_is_passed_to_gemini_prompt(self):
        asset = {"id": "a1", "title": "Lead agent", "type": "prompt"}
        with patch.object(assistant, "get_pg_connection", return_value=FakeConnection(asset, [])), patch.object(assistant, "_call_gemini", return_value={"explanation": "ok", "cited_versions": [], "cited_constraints": []}) as call:
            assistant.explain_asset("a1", "Why JSON?")
        self.assertIn("Why JSON?", call.call_args.args[0])

    def test_invalid_input_and_dependency_errors_are_safe(self):
        self.assertEqual(assistant.explain_asset(""), {"explanation": "asset_id must be a non-empty string", "cited_versions": [], "cited_constraints": []})
        with patch.object(assistant, "get_pg_connection", side_effect=RuntimeError("db secret")):
            result = assistant.explain_asset("a1")
        self.assertEqual(result["cited_versions"], [])
        self.assertNotIn("db secret", result["explanation"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify the intended failure**

Run: `python -m unittest discover -s tests -p 'test_onboarding_assistant.py' -v`

Expected: FAIL because `onboarding.assistant` and `explain_asset` do not exist yet.

- [ ] **Step 3: Create package markers only**

Create empty `onboarding/__init__.py` and `tests/__init__.py`; do not implement production behavior yet.

- [ ] **Step 4: Run tests again**

Run: `python -m unittest discover -s tests -p 'test_onboarding_assistant.py' -v`

Expected: FAIL with the missing `onboarding.assistant` module/function, proving the tests are red for the feature.

---

### Task 2: Database evidence loading and safe contract

**Files:**
- Create: `onboarding/assistant.py`
- Modify: `tests/test_onboarding_assistant.py`

**Interfaces:**
- Consumes: `db.client.get_pg_connection()` when available, or the test-patched `get_pg_connection`.
- Produces: `explain_asset(asset_id, question=None)` and internal `_load_evidence()` returning asset/version evidence.

- [ ] **Step 1: Add the missing-asset and DB-safe tests**

Add tests asserting that a missing asset returns `asset not found` with empty citations and that a DB exception never escapes.

- [ ] **Step 2: Run focused tests and verify red**

Run: `python -m unittest tests.test_onboarding_assistant -v`

Expected: FAIL because the function is not implemented.

- [ ] **Step 3: Implement the minimal DB boundary**

Implement `get_pg_connection()` as a lazy import wrapper, `_empty_result(message)`, `_load_evidence(connection, asset_id)`, and `explain_asset()` input/DB handling. Use parameterized queries and close cursor/connection in `finally`. `_load_evidence()` must return `None` for a missing asset and versions ordered by `version_number`.

- [ ] **Step 4: Run tests and verify green**

Run: `python -m unittest tests.test_onboarding_assistant -v`

Expected: all current tests PASS except tests that intentionally patch the not-yet-written Gemini boundary; add no unrelated behavior.

---

### Task 3: Gemini REST call, JSON validation, and citation filtering

**Files:**
- Modify: `onboarding/assistant.py`
- Modify: `tests/test_onboarding_assistant.py`

**Interfaces:**
- Consumes: evidence from `_load_evidence()` and `GEMINI_API_KEY`/`GEMINI_MODEL`.
- Produces: `_call_gemini(prompt) -> dict` and validated public results.

- [ ] **Step 1: Add failing tests for prompt/API behavior**

Add tests for missing `GEMINI_API_KEY`, malformed Gemini JSON, HTTP/API failure, and citation filtering. Patch `urllib.request.urlopen` with a fake response; assert the request URL contains the configured model but never the API key in the prompt or logs.

- [ ] **Step 2: Run tests to verify red**

Run: `python -m unittest tests.test_onboarding_assistant -v`

Expected: FAIL because `_call_gemini` and response validation do not exist.

- [ ] **Step 3: Implement the smallest REST client**

Use `urllib.request.Request` with JSON body:

```python
{
    "contents": [{"parts": [{"text": prompt}]}],
    "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2},
}
```

POST to `https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}` with a finite timeout. Read `candidates[0].content.parts[0].text`, parse JSON, require string explanation plus list citations, then filter citations against loaded evidence. Convert every failure into `_empty_result()`.

- [ ] **Step 4: Run focused tests and verify green**

Run: `python -m unittest tests.test_onboarding_assistant -v`

Expected: all focused tests PASS with no network calls.

---

### Task 4: Full verification and handoff

**Files:**
- Verify: `onboarding/assistant.py`, `tests/test_onboarding_assistant.py`
- Append: `memory/onboarding-assistant.md`

- [ ] **Step 1: Run the focused suite**

Run: `python -m unittest discover -s tests -p 'test_onboarding_assistant.py' -v`

- [ ] **Step 2: Run the full suite and compile check**

Run: `python -m unittest discover -s tests -v` and `python -m compileall onboarding tests`

- [ ] **Step 3: Inspect for secrets and unrelated changes**

Run: `git diff --check`, `git status --short`, and search staged content for the pasted credential pattern and `.env` files.

- [ ] **Step 4: Append the memory handoff**

Record tests, implementation decisions, failures, and any unavailable live DB/Gemini verification without overwriting previous memory.

- [ ] **Step 5: Commit atomically**

```bash
git add onboarding tests memory/onboarding-assistant.md
git commit -m "feat: add grounded onboarding assistant"
```

- [ ] **Step 6: Push the feature branch**

```bash
git push -u origin feature/onboard-assistant
```

Report repository tests and live smoke-test status separately.
