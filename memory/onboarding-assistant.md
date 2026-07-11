# Onboarding assistant memory

## 2026-07-11 - Design approved

- Scoped the task to `onboarding/assistant.py`; delivery UI is excluded.
- Selected Gemini Developer API free tier and `gemini-3.1-flash-lite` as the
  configurable default. Rejected Claude, Groq, and NVIDIA for this task.
- Chose stdlib HTTPS instead of adding an SDK, with `GEMINI_API_KEY` supplied
  only through the environment.
- Locked grounding: load asset versions and rationale through `db/client.py`,
  then filter model citations against the loaded version numbers and exact
  stored constraints.
- Chose safe error results with empty citations for invalid input, missing data,
  database errors, API errors, quota exhaustion, and malformed responses.
- No implementation exists yet. Next: user reviews the written spec, then write
  the implementation plan and execute it with strict TDD.
- Security note: an API credential was pasted into chat. It must be revoked and
  replaced; it was not copied into the repository or used.

## 2026-07-11 - Implementation and verification

- Added `onboarding/assistant.py` with lazy shared DB import, parameterized
  asset/version queries, Gemini Free Tier REST calls, response validation, and
  citation filtering.
- Added eight unittest cases covering the public contract, optional question,
  tuple/dict-compatible evidence boundary, missing asset, DB/API failures,
  malformed/empty model output, and the HTTP request body.
- Focused tests pass: `python -m unittest discover -s tests -p
  'test_onboarding_assistant.py' -v`.
- Live Gemini/database smoke test remains unavailable because `db/client.py`
  and seed data are not present in this checkout and no rotated API key was
  supplied. No secret was used.
