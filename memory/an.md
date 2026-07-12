# Ấn — Adapter and Capture Pipeline Memory

## 2026-07-11

### Completed

- Implemented shared SQLite/Chroma clients and MVP schema.
- Implemented Git commit adapter with canonical event contract.
- Implemented Featherless rationale extraction using `zai-org/GLM-5.2` at `https://api.featherless.ai/v1`.
- Implemented transactional asset/version/rationale creation and Chroma upsert.
- Created isolated Conda environment definition `loomi-an`.
- Added unit, integration, retry, idempotency, versioning, and opt-in live API tests.
- Added operator and component documentation.

### Decisions

- Chose SQLite plus persistent Chroma for self-contained hackathon demo.
- Asset identity is repository root plus sorted captured path set; branch is excluded by MVP scope.
- Version and asset UUIDs are deterministic so retries do not duplicate vector records.
- Featherless credential is environment-only. Project contains placeholders, never real key.
- Embedding model is fixed to `sentence-transformers/all-MiniLM-L6-v2` across components.

### Problems and Fixes

- Base Conda environment had `chromadb-client`, which is HTTP-only and cannot create `PersistentClient`. Created dedicated `loomi-an` environment with full `chromadb` package.
- Initial `conda env create` with classic resolver spent several minutes on metadata. Used libmamba solver to create Python 3.11 environment, then installed manifest pip dependencies.
- Chroma cannot share SQLite transaction. Deterministic version IDs make vector retry an idempotent upsert.

### Remaining Integration

- Hồng's recommendation engine must reuse exact MiniLM embedding model.
- Team may swap SQLite implementation for PostgreSQL only inside `db/client.py`.
- Demo runner/poller can call `capture_commit()` then `process_raw_event()`; background automation is intentionally outside current scope.

## 2026-07-12

### Completed

- Implemented end-to-end intent review enrichment with optional `chat_history` payload from chat hooks (Codex + Claude Code) through API gateway to core service.
- Added runtime-safe DB migration in `intent_ci/engine.py` to create `intent_reviews.chat_history` on existing databases without breaking old deployments.
- Added SSE `intent_review_required` event from core whenever a prompt review is created, enabling immediate user-facing attention cue.
- Updated Next.js dashboard to flash newly arrived pending intent reviews and show compact chat history context before approve/reject.
- Added tests for chat history sanitization/persistence in `tests/intent_ci/test_engine.py` and gateway forwarding in `api/tests/gateway.test.ts`.

### Decisions

- Keep intent extraction focused on the submitted prompt while storing recent chat context for reviewer grounding.
- Store `chat_history` as JSON string in SQLite and JSONB in Postgres schema; normalize values in engine to a bounded safe list (20 items, 1000 chars each).
- Emit a dedicated SSE event for "review required" instead of overloading existing `intent_review` consumer logic.

### Problems and Fixes

- Existing databases do not auto-pick new columns from `CREATE TABLE IF NOT EXISTS`; fixed with runtime column-check + `ALTER TABLE` fallback.
- Frontend SSE resolve handler had stale state capture risk; fixed by functional state update when clearing flash marker.
- Local environment test run showed unrelated infra gaps (`jest` missing in API workspace and Chroma HTTP-only mode for some core tests). Verified changed intent engine suite independently.

### Remaining Integration

- Install API dev dependencies in `api/` (`npm install`) before running gateway Jest suite locally.
- For full core test pass, run in configured environment where Chroma persistent client mode is available.
- Optional: add hook contract docs listing supported history keys for each client payload shape.

## 2026-07-12 — recommend composer-change bug fix

### Problem
User reported: when composer content changes (new git commit) for an asset,
recommend() did not surface the workflow even when the new query text was
near-identical to the committed diff.

Root cause: capture_pipeline/process.py upserted Chroma vector with
`ids=[f"draft:{version_id}"]` and metadata `review_status="pending"`. Recommend
engine (`recommend/engine.py`) queries Chroma with `query_texts=[task]` then
joins hits on `assets.id IN (...)`. The id `draft:<uuid>` never matched any
`assets.id`, so `meta = {}`, every row was skipped, results = [].

### Fix
- capture_pipeline/process.py: upsert directly under `ids=[asset_id]` (with
  `version_id` and `review_status` in metadata). Removed the `draft:` prefix -
  matches the convention Hồng already documented in `memory/recommend-hong.md`
  ("vector id = asset_id") at integration time.
- Engine unchanged - now join works because id == asset_id.
- `tests/capture_pipeline/test_process.py::test_process_creates_pending_review_with_draft_embedding`
  updated lookup to `result["asset_id"]` (test still asserts the upsert shape).
- Trade-off: pending (un-reviewed) rationale is now visible in recommend().
  Acceptable for MVP/ponytail; review tab still gates `rationale` table write.

### Status
`pytest tests/capture_pipeline/test_process.py tests/recommend/ tests/test_scoring.py`
= 13/13 passed.

Next: re-run end-to-end smoke with the demo composer; same asset, two commits
should resolve to id=asset_id and recommmend should return consistent rows
across edits instead of empty.
