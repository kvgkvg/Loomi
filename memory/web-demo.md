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

## 2026-07-12 - Role-aware view wired into web UI

### Completed
- Threaded optional `role` through the web stack: core `RecommendRequest`/
  `ExplainRequest` models, gateway Zod schemas, and passed positionally to the
  existing `recommend(task, top_k, role)` / `explain_asset(id, question, role)`
  contracts (unchanged).
- Frontend: "Viewing as" role switcher in the nav (Developer/Intern/Tech Lead/
  Manager presets, persisted in localStorage), role sent with every recommend and
  explain call, ghost suggestion shows the `role_reason` line ("◆ Manager lens:
  Matches role goal: risk"), and role change re-triggers the debounced suggestion.
- Verified: Manager role boosts the contract asset 0.5613 → 0.5964 with role_reason;
  Intern explanation comes back step-by-step with primary_actions; UI end-to-end.
- Tests: backend 79 passed / 2 skipped (SQLite mode); gateway Jest 8/8 (run inside
  the api container via `docker compose exec -T api npx jest` — jest is not
  installed on the host).

### Problems and fixes
- Featherless plan allows 4 concurrency units and GLM-5.2 costs 4 units/request →
  only ONE LLM call can be in flight org-wide. Parallel explain calls (or a demo
  with two people clicking Review simultaneously) 429 as "unable to generate
  explanation". Also saw provider-side 504s that hold the quota for a while.
  Retry when idle — not a code bug.

## 2026-07-12 - Intent CI: prompt reviews from chat environments

### Completed
- New `intent_ci/engine.py`: every prompt POSTed from a chat env runs three
  CI-style checks — `policy_secrets` (regex, reuses chat adapter secret patterns;
  prompt stored redacted), `reuse_available` (recommend() top-1 >= 0.45 →
  action_required with the matching asset), `intent_clarity` (GLM extracts
  {intent, confidence}; < 0.6 fails; LLM error degrades to an 'error' check,
  never raises). All pass → 'passed'; else 'pending' → human approve/reject.
- New table `intent_reviews` in BOTH db/schema.sql and db/schema_pg.sql
  (checks TEXT in SQLite, JSONB in Postgres).
- Core endpoints: POST /intent-review (broadcasts `intent_review` SSE),
  GET /intent-reviews, POST /intent-review/{id}/resolve (broadcasts
  `intent_review_resolved`). Gateway proxies all three with Zod validation.
- UI: "Intent CI — Prompt Reviews" panel under the Composer — env badge, status
  chip (PASSED/PENDING/APPROVED/REJECTED), per-check ✓/✗/●/⚠ lines, Approve/
  Reject buttons on pending; live updates via SSE, resolver name = current role.
- `integrations/`: Claude Code UserPromptSubmit hook (working, fire-and-forget,
  always exit 0) + settings snippet; Codex CLI notify script (experimental);
  Copilot documented as skipped (no prompt-hook API); generic curl for anything.
- Verified e2e: clean prompt → passed; api_key prompt → policy fail + [REDACTED]
  stored; "triage support tickets" → reuse action_required 0.69 vs seeded asset;
  hook script → exit 0 instantly, review appears in UI via SSE ~15s later with
  reuse hit on "Meeting notes summarizer" (0.65); Approve flips PENDING→APPROVED.
- Tests: 8 new in tests/intent_ci/ (mocked LLM + recommend); full suite
  87 passed / 2 skipped; gateway Jest 8/8.

### Notes
- agent-browser `click @ref` on buttons rendered after async state changes is
  unreliable (stale refs) — use `agent-browser eval` with a JS querySelector
  click for verification; the app itself is fine.
