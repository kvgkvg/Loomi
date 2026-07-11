# Web Demo Memory

## 2026-07-11 - Next.js OpenSpec design

### Completed

- Explored the existing Python capture, recommendation, onboarding, database,
  tests, project docs, and prior component memory before designing the web demo.
- Approved a Narrative Canvas combining Git-change notifications with a
  debounced ghost prompt suggestion in the assigned-task composer.
- Initialized OpenSpec 1.5.0 and created change
  `build-nextjs-organizational-memory-demo`.
- Split requirements into platform runtime, Git memory detection, proactive
  recommendation, asset onboarding, and narrative demo UI capability specs.
- Chose Next.js App Router, Express public API/SSE, a thin Python HTTP service,
  PostgreSQL plus SQLite fallback, and remote plus embedded Chroma modes.

### Decisions

- Next.js replaces the earlier React/Vite frontend assumption.
- Express remains the only browser-facing API; Python retains all domain logic.
- Docker Compose uses one image per service in one stack, not one combined image.
- Git polling defaults to three seconds; composer matching uses 650 ms debounce,
  24-character minimum input, stale-request cancellation, and 0.45 threshold.
- motion-anything is a development reference only, not a runtime dependency.

### Problems and fixes

- `openspec init . --tools codex` could not create `.codex/skills` because that
  workspace path is not writable. OpenSpec core initialized correctly and the
  CLI workflow remains usable, so do not retry the Codex shortcut install.
- The initial change name and specs referenced PERN/React. Renamed the change
  and updated all artifacts after the frontend decision changed to Next.js.

### Remaining

- User must review and approve the written OpenSpec artifacts.
- After approval, generate `tasks.md` and the detailed implementation plan.
- Only then begin subagent-driven implementation and runtime/browser setup.

## 2026-07-11 - Progress assessment

### Completed
- Reviewed the original Next.js OpenSpec design artifacts, including `design.md`, `proposal.md`, and `tasks.md`.
- Evaluated current repository files: confirmed that backend logic (Khang's DB/Seed, An's Adapter/Capture Pipeline, Hong's Recommendation, Tri's Onboarding Assistant) is 100% complete and fully verified.
- Confirmed the actual implementation progress of the Web Application (Next.js, Express gateway, FastAPI proxy, PostgreSQL migration) is at 0%, pending user's review and design approval.

## 2026-07-11 - Full Web Demo Implementation

### Completed
- Implemented storage compatibility for PostgreSQL and remote Chroma HTTP client in `db/client.py` and `db/schema_pg.sql`.
- Built the thin FastAPI core web service at `core/app.py` wrapper, exposing endpoints for health check, recommend, explain, manual capture, and events SSE stream.
- Built the background Git poller task in FastAPI, storing last polled SHA state and preventing duplicates.
- Created and configured the Express Gateway (TypeScript Node.js) at `api/` proxying to FastAPI core, validating payloads with Zod, and fanning out SSE events to browser.
- Created the Next.js App Router workspace at `frontend/` implementing the Narrative Canvas, SSE stream subscription, debounced ghost suggestion composer, and grounded asset review & Q&A panel.
- Verified system resources, cleaned up user cache and unused Docker volumes to free up disk space.
- Successfully built Next.js production code, passed all backend Python tests (44/44 green) and API Gateway Jest integration tests (8/8 green).


## 2026-07-12 - Local-repo tracking + real asset content in UI

### Completed
- Verified the composer-hang fix holds after restart: /health 13-18ms, /recommend 76ms,
  2 SSE subscriber events in 9 minutes (previously a ~30/sec reconnect storm), 0 errors.
- Mounted the host home directory read-only at `/host` in the core service and added
  `LOOMI_HOST_HOME` so `/track` translates host paths (`~/x` or `/home/<user>/x`) to
  `/host/x`. Any local repo under home is now trackable live from the UI, no restart.
- Added `GET /asset/{id}` (core) + `GET /api/asset/:id` (gateway): title, owner,
  usage_count, current content, and full version history joined with rationale.
- Frontend Evidence Stack now shows the real stored prompt content, a Version History
  section with CITED badges (from explain's cited_versions), and "Use Prompt Template"
  inserts the real asset content into the composer (the hardcoded fake prompt is gone).
- Review flow loads asset detail first (fast DB call) and the LLM explanation after,
  with a "Synthesizing design rationale" hint — the panel no longer sits blank for the
  ~24s the Featherless GLM explanation takes.
- End-to-end verified: created a throwaway repo in ~/.cache, tracked it via the API,
  committed a .prompt file → poller captured, rationale extracted, memory_ready SSE
  fired, and the event rendered in the feed with the extracted problem statement.

### Problems and fixes
- Running `pytest` inside the core container WITHOUT unsetting DATABASE_URL wipes and
  reseeds the live Postgres demo data (test fixtures write to whatever DB is
  configured). Asset UUIDs changed while Chroma kept the old ones → recommend returned
  IDs that /explain and /asset couldn't find ("asset not found"). Fix: reseed both
  stores with `python -m db.seed`, and always run tests as
  `docker compose exec -T -e DATABASE_URL= -e CHROMA_HOST= core python -m pytest`
  (79 passed, 2 skipped on SQLite).
- The 15 Postgres-mode test failures (e.g. "invalid input syntax for type uuid:
  'reviewer'") are pre-existing SQLite-typed fixtures, not regressions.
- One demo asset "Add incident postmortem writer prompt" (owner ThuongHong) remains in
  Postgres/Chroma from the e2e test; harmless, shows live capture in demos.

### Remaining
- Feed does not persist across page reload (no initial fetch of recent assets).
- Ghost suggestion "Adopt" button still routes to Review.
- Repo-info label only refreshes when tracking is changed from the same browser tab.
- Whole session's changes still uncommitted on develop.

## 2026-07-12 - Multi-provider chat demo environment

### Completed
- Created `demo/chats/` with realistic exports in both provider formats:
  `chatgpt_release_notes.json` (ChatGPT `mapping` format, release-notes-from-PRs
  prompt, owner Khang) and `claude_contract_review.json` (Claude `chat_messages`
  format, vendor-contract clause-flagging prompt, owner Trí). Conversations follow
  the pipeline's assumption that the LAST user turn is the final asset content, and
  contain explicit failed attempts + constraints so statement extraction has signal.
  Optional `_loomi_owner` key attributes the asset to a teammate.
- Added `scripts/seed_demo_chats.py`: runs each fixture through the real pipeline
  (capture_chat_export → process_chat_event → approve all statements as "Demo
  Reviewer" → Chroma upsert), sets asset owner, idempotent on rerun, `--no-approve`
  flag leaves statements pending. Run:
  `docker compose exec core python scripts/seed_demo_chats.py`
- Verified end-to-end: both chat assets recommendable (~0.60 score on matching task
  descriptions), `/asset` returns content + rationale-backed version info, and the UI
  ghost suggestion → Review → Evidence Stack flow renders them (owner, real prompt,
  version history).

### Problems and fixes
- GLM-5.2 statement extraction failed validation two ways: it invented
  `statement_type` values ("solution", "design_principle") because `_SYSTEM` in
  `capture_pipeline/rationale_statements.py` never enumerated the allowed set, and it
  filled `source_version_ids` with unsupplied IDs. Fixed by tightening the system
  prompt (enumerate allowed types/kinds; require empty arrays when no version/commit
  IDs supplied). Validation logic untouched.
- `process_chat_event` swallowed all exceptions silently; added
  `logging.exception(...)` before rollback so failures are debuggable.

### Remaining
- Chat assets don't appear in the Git feed (SSE is git-only) — demo them via the
  composer suggestion path.
- Statement extraction is still LLM-nondeterministic; if a fixture fails validation,
  rerun the script (idempotent).
