# Running Loomi — Web Demo Stack

Everything runs in Docker Compose: five services, one command. This is the
path for demos and integration testing. (For the library-level Python/conda
workflow, see the [README](../README.md).)

## Architecture

```
frontend (Next.js :3000)
   → api (Express gateway :3001)
      → core (FastAPI :8002→8000)  ← git poller + SSE broadcaster
         → postgres (:5433→5432)   ← canonical store
         → chroma  (:8001→8000)    ← vector search (ONNX MiniLM embeddings)
```

## Prerequisites

- Docker + Docker Compose
- `.env` in the repo root:

```bash
cp .env.example .env
```

| Variable | Required | Purpose |
|---|---|---|
| `FEATHERLESS_API_KEY` | yes | Rationale extraction + onboarding explanations (GLM-5.2) |
| `LOOMI_HOST_REPO` | no | Host repo the git poller tracks at startup (defaults to this repo). Can be switched at runtime from the UI — see below. |

`LOOMI_DB_PATH` / `LOOMI_CHROMA_PATH` from `.env.example` only affect the
non-docker SQLite workflow; the compose stack uses Postgres + Chroma server.

## Start

```bash
docker compose up -d --build
```

First start downloads the ~167 MB ONNX embedding model into the `onnx_cache`
volume — the core service can take a minute before its healthcheck goes green.

- UI: <http://localhost:3000> — expect the green **System: HEALTHY** badge
- Gateway health: `curl http://localhost:3001/api/health`

## Seed demo data

```bash
# 6 git-style assets (prompts/workflows with rationale + vectors)
docker compose exec core python -m db.seed

# 2 chat-derived assets (real ChatGPT + Claude export fixtures pushed
# through the full chat pipeline, statements auto-approved)
docker compose exec core python scripts/seed_demo_chats.py
```

Both are idempotent — rerun any time the data gets messy. If the chat seeder
reports a validation failure (LLM output is nondeterministic), just rerun it.

## Demo walkthrough

**1. Live git capture.** In the UI's *Track* box paste a repo — either a git
URL (`https://github.com/owner/repo`, cloned inside the container) or any
local path under your home directory (`~/path/to/repo`; the host home is
mounted read-only at `/host` and paths auto-translate). Then commit a
knowledge file to that repo:

```bash
echo "You are a code reviewer..." > review.prompt
git add review.prompt && git commit -m "Add code review prompt"
```

Within ~3 s (poll interval) plus LLM time, a toast lands in the *Captured Git
Knowledge Feed* with the extracted problem statement. Only `.md .txt .prompt
.json .yaml .yml` files count — code-only commits are skipped by design.

**2. Proactive recommendation.** Type a task into the Composer (≥ 24 chars;
650 ms debounce). Try:

- `I need to triage incoming customer support tickets` → git-seeded asset
- `turn merged pull requests into customer release notes` → ChatGPT-derived asset
- `flag risky auto-renewal clauses in a vendor contract` → Claude-derived asset

**3. Evidence Stack.** Click *Review* on a suggestion: the stored prompt,
owner, and version history (CITED badges) appear instantly; the synthesized
design rationale + constraints follow after the LLM call (~20–30 s). Use the
*Ask* box for grounded follow-up questions.

**4. Adoption.** *Use Prompt Template* inserts the real stored prompt into
the Composer and increments the asset's `usage_count`.

## Tests

```bash
# Backend (79 tests). MUST blank DATABASE_URL/CHROMA_HOST — otherwise the
# fixtures write into the live Postgres/Chroma and wipe your demo data.
docker compose exec -T -e DATABASE_URL= -e CHROMA_HOST= core python -m pytest -q

# API gateway (Jest)
cd api && npm test
```

## Troubleshooting

| Symptom | Check |
|---|---|
| UI badge shows DEGRADED | `curl http://localhost:3001/api/health` — tells you which layer failed |
| Feed never shows commits | `docker logs loomi-core --tail 50` — poller and pipeline errors (tracebacks are logged) |
| Recommend returns assets that 404 on Review | Postgres and Chroma are out of sync — reseed both (commands above) |
| First request hangs tens of seconds | ONNX model cold download — wait for `loomi-core` healthcheck, it's cached in a volume afterwards |
| Demo data trashed after running tests | You ran pytest against live Postgres — reseed, and use the test command above |

Known limitations: chat-derived assets don't appear in the git feed (SSE is
git-only — demo them via the Composer); the feed resets on page reload.
