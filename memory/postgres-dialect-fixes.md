# Postgres dialect fixes after app-demo merge (2026-07-12)

## Context
Merged `feature/app-demo` (docker web stack: Next.js + Express + FastAPI core + Postgres + Chroma) into `develop`. app-demo code was written/tested against **SQLite**; running the full docker stack uses **Postgres**, which exposed 3 dialect bugs. All found by end-to-end real-data testing (live Featherless, no mock).

## Bugs found & fixed
1. **`db/schema_pg.sql` missing 7 tables.** During merge, `db/schema.sql` (SQLite) got develop's prompt-history/rationale-review tables, but `schema_pg.sql` was NOT conflicted so it kept app-demo's older table set. Missing: `conversations, conversation_turns, turn_feedback, rationale_statements, rationale_statement_turns, rationale_statement_versions, rationale_statement_commits`. Symptom: `/explain` crashed `relation "rationale_statements" does not exist`. Fixed by porting all 7 to PG dialect (UUID / TIMESTAMPTZ).
   - **Rule: whenever `schema.sql` changes, mirror it in `schema_pg.sql`.** They drift silently — no test catches it unless you run on Postgres.

2. **`core/app.py is_commit_captured`: `raw_signal LIKE ?`.** `raw_signal` is TEXT in SQLite but **JSONB** in Postgres → `operator does not exist: jsonb ~~ unknown`. The git poller crashed every tick. Fixed with portable `CAST(raw_signal AS TEXT) LIKE ?` (works both engines).
   - **Rule: never `LIKE` a JSONB column. Cast to text, or use JSON operators.**

3. **`docker-compose.yml` core env passed `GEMINI_API_KEY`** but the pipeline uses `FEATHERLESS_API_KEY` (Featherless GLM-5.2). Capture/explain LLM silently failed. Swapped to `FEATHERLESS_API_KEY=${FEATHERLESS_API_KEY}`.

## Feature: git poller on ANY repo
`capture_commit(commit_sha)` originally resolved the repo from **cwd** (`git rev-parse --show-toplevel`), ignoring the poller's `LOOMI_REPO_PATH`. Added optional `repo_path` param (backward compatible — default None = cwd). `core/app.py` now has `resolve_repo_path()` (env `LOOMI_REPO_PATH` → git toplevel → repo parent) used by both the poller and `/capture`. To demo live capture on an external GitHub repo: clone it into a bind-mounted, gitignored path (`.demo-repos/target`), set `LOOMI_REPO_PATH=/app/.demo-repos/target`, recreate core. New commits → SSE `memory_ready` → frontend feed → discoverable via recommend.

Demo trick: to replay a repo's EXISTING commits as "new" without fabricating commits, `UPDATE git_poll_state SET last_polled_sha='<older_sha>'` — poller streams `older..HEAD` live. Already-captured commits are deduped silently (no SSE), so only genuinely new supported files broadcast.

## Verified end-to-end (docker stack, real data)
recommend (embedding), explain (live LLM, grounded + constraints), capture (commit→rationale→embed), api gateway proxy, Next.js UI, and the git-poller → SSE live feed on an external GitHub repo. Screenshots in scratchpad.
