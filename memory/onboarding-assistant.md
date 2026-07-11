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
- At implementation time, live Gemini/database smoke test remained unavailable
  because `db/client.py` and seed data were not present and no rotated API key
  was supplied. No secret was used.

## 2026-07-11 - Gemini live smoke

- A rotated `GEMINI_API_KEY` became visible to the Codex process.
- The direct Gemini Free Tier request succeeded through `_call_gemini()` and
  returned valid JSON: `smoke test passed` with empty citation lists.
- The first sandbox request failed on DNS resolution; the retry with approved
  network escalation succeeded. End-to-end `explain_asset()` remains blocked
  only by the missing shared DB client and seed data.

## 2026-07-11 - Grounded seed-asset verification

- `db/client.py`, `db/schema.sql`, and `db/seed.py` are now present. Running the
  seed script populated SQLite relational rows but stopped while creating
  Chroma vectors because `chromadb` is not installed.
- Used the seeded asset `35e6eb7c-acfc-4bfd-a603-e4dd30328cbf` (Lead
  qualification agent for inbound sales) to run `explain_asset()` end to end.
- Evidence loaded: one asset version and its rationale. Gemini returned a
  grounded explanation citing version 1 and the exact stored constraints about
  valid JSON and not contacting leads directly.
