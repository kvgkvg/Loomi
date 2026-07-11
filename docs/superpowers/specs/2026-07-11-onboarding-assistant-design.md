# Spec: Grounded Onboarding Assistant

## Objective

Implement only the onboarding assistant assigned to Tri. Given an asset ID and
an optional question, it explains why the asset evolved as it did using stored
versions and rationale. The result must remain grounded in database evidence
and must not break the hackathon demo when the database or LLM is unavailable.

The delivery UI, recommend engine, capture pipeline, database implementation,
and production governance are outside this spec.

## Accepted Design Decisions

- Use the Gemini Developer API free tier, not Claude, Groq, or NVIDIA.
- Default to `gemini-3.1-flash-lite`, configurable with `GEMINI_MODEL` because
  free-model availability can change.
- Read relational data only through `db/client.py`.
- Call Gemini over HTTPS with Python's standard library; do not add an SDK.
- Never store an API key in source control. Read `GEMINI_API_KEY` at runtime.
- Do not provide a deterministic synthesized answer when Gemini fails; return a
  safe, explicit failure result with empty citations.

## Public Contract

```python
def explain_asset(asset_id: str, question: str = None) -> dict:
    """Return explanation, cited version numbers, and cited constraints."""
```

Every call returns exactly these keys:

```python
{
    "explanation": str,
    "cited_versions": list[int],
    "cited_constraints": list[str],
}
```

No caller-visible signature changes are allowed without team approval.

## Architecture and Data Flow

1. Validate that `asset_id` is a non-empty string and normalize an empty
   optional question to no question.
2. Obtain a DB-API connection from `db.client.get_pg_connection()`.
3. Load the asset, all `asset_versions`, and each version's `rationale`, ordered
   by `version_number`.
4. Serialize only the loaded evidence and optional question into the prompt.
5. Request JSON from the Gemini REST API.
6. Validate the response shape and types.
7. Remove every cited version not loaded from the database and every cited
   constraint not present in the stored rationale.
8. Return the public contract.

The assistant does not query Chroma because semantic retrieval belongs to the
recommend engine; onboarding starts from an already-selected `asset_id`.

## Grounding Rules

- The explanation may use only asset metadata, version content, diff summaries,
  rationale problems, failed attempts, and constraints loaded for the asset.
- When a question cannot be answered from that evidence, Gemini must say the
  stored evidence is insufficient.
- Version citations are integers matching stored `version_number` values.
- Constraint citations are exact stored constraint strings. Hallucinated or
  malformed citations are discarded after generation.
- Secrets and raw database credentials must never appear in prompts or logs.

## Error Handling

Invalid input, missing assets, DB errors, absent API keys, timeouts, HTTP errors,
quota errors, malformed Gemini responses, and invalid JSON must not escape from
`explain_asset()` as exceptions. They return an explanatory message with empty
`cited_versions` and `cited_constraints`. The message may identify the failure
category but must not expose credentials, response internals, or stored content.

The HTTP request has a finite timeout. One call is attempted; automatic retry is
excluded from the MVP because it consumes free quota and adds demo latency.

## Tech Stack

- Python 3.10+
- Team-provided DB-API connection through `db/client.py`
- Gemini Developer API free tier
- Python standard library: `json`, `os`, `urllib.request`, `urllib.error`
- `unittest` for isolated tests

## Commands

```bash
# Focused tests
python -m unittest discover -s tests -p 'test_onboarding_assistant.py' -v

# All repository tests
python -m unittest discover -s tests -v

# Syntax validation
python -m compileall onboarding tests
```

No build or lint command exists in the repository yet. Adding a formatter,
test framework, or dependency manager is outside this feature.

## Project Structure

```text
onboarding/
  __init__.py             # Package marker
  assistant.py            # Public function and minimal internal helpers
tests/
  test_onboarding_assistant.py
docs/superpowers/specs/
  2026-07-11-onboarding-assistant-design.md
memory/
  onboarding-assistant.md # Append-only session decisions and handoff
```

## Code Style

Use small typed helpers only where they isolate an external boundary. Keep the
public function unchanged and return plain built-in data structures.

```python
def explain_asset(asset_id: str, question: str = None) -> dict:
    if not isinstance(asset_id, str) or not asset_id.strip():
        return _empty_result("asset_id must be a non-empty string")
    # Load evidence, call Gemini, validate citations, return the contract.
```

Use snake_case, four-space indentation, explicit timeouts, and no module-level
network or database work.

## Testing Strategy

Implementation follows strict red-green-refactor. Each production behavior is
preceded by a focused test that is run and observed failing for the intended
reason. Tests use fake connection/cursor objects and an injected fake LLM call;
they do not require a live database, network, or API quota.

Required behavioral checks:

1. A valid asset returns the exact contract.
2. Versions are ordered and the optional question reaches the grounded prompt.
3. Unknown version and constraint citations are removed.
4. Empty and missing asset IDs return safe results.
5. DB and Gemini failures do not escape as exceptions.
6. The production data path imports the shared DB client.
7. A final opt-in smoke test may call Gemini using a rotated local key, but it
   must not be part of the default test suite.

## Boundaries

- Always: preserve the public contract, use `db/client.py`, validate inputs and
  model output, use finite network timeouts, run tests before completion, and
  keep secrets out of files and logs.
- Ask first: change the database schema, add dependencies, alter the function
  signature, add another provider, or change repository-wide tooling.
- Never: commit `.env` or API keys, connect to the database independently,
  fabricate citations, implement the UI, or add graph/RBAC infrastructure.

## Success Criteria

- `onboarding/assistant.py` exposes the specified function and exact output.
- It loads all version/rationale evidence through the shared DB client.
- It supports both general explanation and an optional grounded question.
- It uses a free Gemini model configured through environment variables.
- All returned citations are verified against loaded database evidence.
- Every declared failure mode returns safely without leaking sensitive data.
- Focused tests and the full local test suite pass.
- A live smoke test succeeds with a newly rotated Gemini key when the external
  DB client and seed data are available.

Repository-side completion and live integration completion must be reported
separately if the team-owned DB client or seed data is still absent.

## Open Questions

None. Integration will adapt SQL placeholder syntax to the actual DB-API client
once `db/client.py` exists, without changing the public contract.
