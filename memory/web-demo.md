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

## 2026-07-11 - Runnable workspace and Compose skeleton

### Completed

- Added minimal Next.js and Express workspaces with root and health smoke tests.
- Added separate frontend, API, and core Dockerfiles plus PostgreSQL and Chroma
  services, health checks, and named state volumes in one Compose stack.
- Added Node and container build output to the existing local-runtime ignores.

### Decisions

- Kept the initial UI and API deliberately minimal; later tasks own the
  Narrative Canvas and downstream health aggregation.
- Used TypeScript checks as the API build and a static Next.js root route as
  the frontend baseline.

### Problems and fixes

- Supertest could not bind a temporary port inside the restricted sandbox
  (`listen EPERM`). The identical API test passed outside that restriction.

### Remaining

- The core container command targets `core_service.app`, which Task 3 creates.
- Full `docker compose up --build` verification follows once Tasks 2 and 3 add
  portable storage and the core HTTP service.

## 2026-07-11 - Chroma health-check review fix

- Reproduced the original Chroma probe failure in the pinned upstream image:
  `python` is absent and exits 127.
- Added a minimal child image that installs `curl`; Compose now checks Chroma's
  `/api/v2/heartbeat` endpoint with that executable.
- Verified `docker compose build chroma`, live startup through healthy state,
  direct curl heartbeat output, Compose config, and clean diff checks.

## 2026-07-11 - Portable Python storage

- Added PostgreSQL selection behind `DATABASE_URL` without changing the public
  `get_pg_connection()` contract; a small DB-API adapter translates SQLite `?`
  placeholders and preserves name/index row access used by existing modules.
- Added idempotent PostgreSQL schema bootstrap and `git_poll_state` to both SQL
  dialects for the upcoming persisted poller.
- Added remote Chroma selection through `CHROMA_HOST`/`CHROMA_PORT`, retaining
  embedded Chroma when the host is absent and keeping the collection API intact.
- Added `psycopg[binary]` as the only new runtime dependency; no ORM or domain
  signature changes were introduced.
- Focused tests pass 5/5 and the offline suite passes 39 tests with 1 live test
  deselected. The sandboxed run could not create Chroma's home cache; rerunning
  with access to the existing model cache passed.

## 2026-07-11 - Thin Python core API

- Added FastAPI endpoints for health, recommendation, asset evidence,
  explanation, prompt adoption, internal capture processing, and lifecycle SSE.
- Kept recommendation, onboarding, capture, and storage contracts unchanged;
  the HTTP layer only validates, delegates, and translates results.
- `memory_ready` is emitted only for capture results that confirm both an asset
  id and `embedded=true`; the in-memory backlog is capped at 100 for the
  single-core hackathon runtime.
- Strict TDD evidence: initial collection failed with missing FastAPI and
  `core_service`; focused tests then passed 7/7 and the offline suite passed
  46 tests with 1 live test deselected.
- Remaining: Task 4 owns Git polling, bounded retries, persisted SHA position,
  and richer capture lifecycle orchestration.

## 2026-07-11 - Core API review fixes

- Corrected internal capture orchestration to call `capture_commit(commit_sha)`
  before `process_raw_event(raw_event_id)` and proved exact argument flow.
- Lifecycle order is now `capture_started` before Git work, followed by
  `memory_ready` with asset/title/source/version only after embedded success,
  or `capture_retrying` for incomplete results and safe exceptions.
- Event publishing is async and loop-local; blocking domain calls use FastAPI's
  threadpool. Added a concurrent endpoint-to-SSE subscriber regression test.
- Replaced deprecated TestClient tests with HTTPX ASGI transport and bounded,
  trimmed optional explanation questions.
