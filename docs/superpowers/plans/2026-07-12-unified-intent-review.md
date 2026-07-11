# Unified Intent Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Analyze web, external-chat, and signed GitHub push events with bounded history; request human intent approval; flash unseen reviews; and retrieve semantically similar historical changes from a dedicated Chroma collection.

**Architecture:** Normalize every source into the existing Intent CI boundary, persist SQL first, then upsert redacted `prompt + intent` into a separate `intent_reviews` Chroma collection. Gateway verifies GitHub raw-body HMAC before forwarding accepted push data to core; core performs idempotent per-commit background analysis and emits existing SSE review events.

**Tech Stack:** Python 3.11, FastAPI, SQLite/PostgreSQL compatibility layer, Chroma 0.5.3, Featherless OpenAI-compatible API, Express/TypeScript/Zod, Next.js 16/React, GSAP, pytest, Jest/Supertest.

---

## File map

- Modify `db/schema.sql` and `db/schema_pg.sql`: matching intent-review columns and unique source identity.
- Modify `db/client.py`: named Chroma collection helper without changing asset collection behavior.
- Modify `intent_ci/engine.py`: history bounding/redaction, persistence, vector indexing, retry, similarity, status synchronization.
- Create `intent_ci/github.py`: pure GitHub push-to-canonical-event adapter.
- Modify `core/app.py`: expanded models/endpoints, async GitHub ingestion, SSE.
- Modify `api/src/index.ts`: expanded schemas, similar/retry proxies, raw-body GitHub HMAC endpoint.
- Modify `frontend/app/page.tsx` and `frontend/app/page.module.css`: web submission/history, unseen flash, similar changes.
- Modify `integrations/*` and `integrations/README.md`: history-aware hook payloads and GitHub setup.
- Modify/add tests under `tests/intent_ci`, `tests/test_core_app.py`, `api/tests`, and `frontend` as listed below.

### Task 1: Compatible relational schema

**Files:**
- Modify: `db/schema.sql:167`
- Modify: `db/schema_pg.sql:163`
- Test: `tests/db/test_client.py`
- Test: `tests/db/test_pg_compat.py`

- [ ] **Step 1: Write failing schema contract tests**

Add SQLite assertions for columns `messages`, `external_id`, `source_metadata`, `embedding_status`, and `embedding_error`, plus a duplicate non-null `(source_env, external_id)` rejection. Extend PostgreSQL schema-text/contract assertions with matching JSONB/TEXT columns.

```python
columns = {row["name"] for row in conn.execute("PRAGMA table_info(intent_reviews)")}
assert {"messages", "external_id", "source_metadata", "embedding_status", "embedding_error"} <= columns
with pytest.raises(sqlite3.IntegrityError):
    conn.execute("""INSERT INTO intent_reviews
        (id,prompt,source_env,external_id,checks,status)
        VALUES ('r2','p','github','repo:sha','[]','pending')""")
```

- [ ] **Step 2: Run tests and confirm failure**

Run: `pytest tests/db/test_client.py tests/db/test_pg_compat.py -q`
Expected: FAIL because columns/index do not exist.

- [ ] **Step 3: Add matching schemas**

SQLite columns use TEXT JSON; PostgreSQL uses JSONB. Add defaults and partial unique indexes:

```sql
messages TEXT NOT NULL DEFAULT '[]',
external_id TEXT,
source_metadata TEXT NOT NULL DEFAULT '{}',
embedding_status TEXT NOT NULL DEFAULT 'pending',
embedding_error TEXT
```

```sql
CREATE UNIQUE INDEX IF NOT EXISTS idx_intent_reviews_source_external
ON intent_reviews(source_env, external_id) WHERE external_id IS NOT NULL;
```

Use `JSONB NOT NULL DEFAULT '[]'::jsonb` / `'{}'::jsonb` in PostgreSQL.

- [ ] **Step 4: Run schema tests**

Run: `pytest tests/db/test_client.py tests/db/test_pg_compat.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add db/schema.sql db/schema_pg.sql tests/db/test_client.py tests/db/test_pg_compat.py
git commit -m "feat: extend intent review storage"
```

### Task 2: History-aware analysis and redaction

**Files:**
- Modify: `intent_ci/engine.py`
- Modify: `tests/intent_ci/test_engine.py`

- [ ] **Step 1: Write failing history tests**

Test newest-turn retention, role validation, secret redaction, and exact LLM messages. Patch client factory and assert prior context precedes current prompt.

```python
history = [
    {"role": "user", "content": "Earlier requirement"},
    {"role": "assistant", "content": "Earlier response"},
]
bounded = bound_messages(history, max_turns=1, max_chars=1000)
assert bounded == [history[-1]]
review = create_intent_review("Current request", "web", messages=history)
assert review["messages"] == history
```

- [ ] **Step 2: Run focused tests and confirm failure**

Run: `pytest tests/intent_ci/test_engine.py -q`
Expected: FAIL because history API does not exist.

- [ ] **Step 3: Implement minimal canonical history**

Add constants `INTENT_HISTORY_MAX_TURNS=12`, `INTENT_HISTORY_MAX_CHARS=12000`; implement `normalize_messages()` and `bound_messages()`. Extend `_extract_intent(prompt, messages=(), client_factory=None)` so Featherless receives system message, bounded redacted history, then current redacted user prompt. Extend `run_checks` and `create_intent_review` with keyword-only `messages`, `external_id`, and `metadata` while preserving old positional callers.

```python
def create_intent_review(prompt, source_env, user_name=None, *, messages=None,
                         external_id=None, metadata=None, client_factory=None): ...
```

Persist and return canonical redacted history/metadata. On duplicate source identity, return existing review.

- [ ] **Step 4: Run focused tests**

Run: `pytest tests/intent_ci/test_engine.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add intent_ci/engine.py tests/intent_ci/test_engine.py
git commit -m "feat: analyze intent with chat history"
```

### Task 3: Dedicated vectors, retry, and Similar Changes

**Files:**
- Modify: `db/client.py`
- Modify: `intent_ci/engine.py`
- Create: `tests/intent_ci/test_vectors.py`

- [ ] **Step 1: Write failing vector tests**

Use fake collection to assert collection name, document recipe, redaction, SQL embedding state, resolution metadata update, similarity join, and retry after failed upsert.

```python
review = create_intent_review("Build release notes", "web")
assert fake.upserts[0]["documents"] == ["Build release notes\nDo the task"]
hits = similar_intent_reviews(review["id"], limit=3)
assert hits[0]["review_id"] != review["id"]
assert 0 <= hits[0]["score"] <= 1
```

- [ ] **Step 2: Run test and confirm failure**

Run: `pytest tests/intent_ci/test_vectors.py -q`
Expected: FAIL because vector functions are absent.

- [ ] **Step 3: Implement named collection and indexing**

Add `get_vector_collection(name: str = "assets")` compatibility or a focused `get_intent_review_collection()` returning `intent_reviews` with cosine metadata. Implement `_index_review`, `retry_intent_review`, and `similar_intent_reviews`; exclude source review ID, clamp cosine, join relational fields, and set `embedding_status` to `ready` or `pending` with error. Extend resolution to update Chroma metadata best-effort without rolling back SQL judgment.

- [ ] **Step 4: Run vector and legacy DB/engine tests**

Run: `pytest tests/intent_ci/test_vectors.py tests/db/test_client.py tests/test_engine.py -q`
Expected: PASS; asset collection behavior unchanged.

- [ ] **Step 5: Commit**

```bash
git add db/client.py intent_ci/engine.py tests/intent_ci/test_vectors.py
git commit -m "feat: index and search intent reviews"
```

### Task 4: Pure GitHub push adapter

**Files:**
- Create: `intent_ci/github.py`
- Create: `tests/intent_ci/test_github.py`

- [ ] **Step 1: Write failing adapter tests**

Fixtures cover supported files, unsupported-only changes, bounded commit text, branch/repository/author metadata, earlier commits as history, and stable `external_id`.

```python
events = normalize_github_push(payload, delivery_id="delivery-1")
assert events[0]["source_env"] == "github"
assert events[0]["external_id"] == "owner/repo:" + payload["commits"][0]["id"]
assert events[1]["messages"][0]["content"].startswith("Earlier commit:")
```

- [ ] **Step 2: Run test and confirm failure**

Run: `pytest tests/intent_ci/test_github.py -q`
Expected: FAIL with missing module/function.

- [ ] **Step 3: Implement adapter**

Define supported extensions matching Git capture. Build one event per commit using repository full name, ref, author, commit message, distinct changed supported paths, and bounded payload-provided change summary. Cap commits, paths, and total characters; never fetch arbitrary repository contents.

- [ ] **Step 4: Run adapter tests**

Run: `pytest tests/intent_ci/test_github.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add intent_ci/github.py tests/intent_ci/test_github.py
git commit -m "feat: normalize github push intents"
```

### Task 5: Core API and asynchronous GitHub processing

**Files:**
- Modify: `core/app.py`
- Modify: `tests/test_core_app.py`

- [ ] **Step 1: Write failing core endpoint tests**

Test expanded request forwarding, retry, similar response, GitHub accepted response, one review per normalized commit, dedup return, and emitted `intent_review` events. Use mocked analyzer/vector boundaries.

```python
response = client.post("/github-push", json={"delivery_id": "d1", "payload": push})
assert response.status_code == 202
assert response.json()["accepted"] is True
```

- [ ] **Step 2: Run tests and confirm failure**

Run: `pytest tests/test_core_app.py -q`
Expected: FAIL for absent models/endpoints.

- [ ] **Step 3: Implement models and endpoints**

Add typed `IntentMessage`, expanded `IntentReviewRequest`, `GitHubPushRequest`, `/intent-review/{id}/retry`, `/intent-reviews/{id}/similar`, and internal `/github-push`. Use `BackgroundTasks` for push processing; each event calls `create_intent_review` in a thread then broadcasts `intent_review`. Return `202` before LLM work.

- [ ] **Step 4: Run core tests**

Run: `pytest tests/test_core_app.py tests/intent_ci -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add core/app.py tests/test_core_app.py
git commit -m "feat: expose unified intent APIs"
```

### Task 6: Signed GitHub gateway and proxies

**Files:**
- Modify: `api/src/index.ts`
- Modify: `api/tests/gateway.test.ts`
- Modify: `docker-compose.yml`

- [ ] **Step 1: Write failing gateway tests**

Add raw JSON fixture and HMAC helper. Assert missing/invalid secret signatures return `401` without Axios calls; valid `push` returns `202` and forwards delivery/payload; non-push events return `202` ignored. Test expanded intent, retry, and similar proxies.

```ts
const signature = `sha256=${createHmac('sha256', 'secret').update(raw).digest('hex')}`;
await request(app).post('/api/webhooks/github')
  .set('X-Hub-Signature-256', signature).set('X-GitHub-Delivery', 'd1')
  .set('X-GitHub-Event', 'push').send(raw).expect(202);
```

- [ ] **Step 2: Run Jest and confirm failure**

Run: `cd api && npm test -- --runInBand`
Expected: FAIL because routes/schema are absent.

- [ ] **Step 3: Implement raw-body HMAC boundary**

Register `/api/webhooks/github` with `express.raw({type:'application/json'})` before global `express.json()`. Use `timingSafeEqual`, require `GITHUB_WEBHOOK_SECRET`, validate headers, parse payload only after signature success, and forward to core. Extend Zod message/metadata schemas and proxy retry/similar endpoints. Pass `GITHUB_WEBHOOK_SECRET=${GITHUB_WEBHOOK_SECRET}` to API service in Compose.

- [ ] **Step 4: Run gateway tests and build**

Run: `cd api && npm test -- --runInBand && npm run build`
Expected: all Jest tests PASS; TypeScript build exits 0.

- [ ] **Step 5: Commit**

```bash
git add api/src/index.ts api/tests/gateway.test.ts docker-compose.yml
git commit -m "feat: verify github intent webhooks"
```

### Task 7: Web submission, flashing review, and Similar Changes UI

**Files:**
- Modify: `frontend/app/page.tsx`
- Modify: `frontend/app/page.module.css`
- Create: `frontend/app/intent-ui.test.tsx`
- Read before code: `frontend/node_modules/next/dist/docs/` relevant App Router/client-component docs per `frontend/AGENTS.md`

- [ ] **Step 1: Add UI test tooling only if absent**

Add minimal Vitest + Testing Library dev dependencies/scripts to `frontend/package.json` only when current package has no component test runner. Configure jsdom in `frontend/vitest.config.ts`.

- [ ] **Step 2: Write failing UI tests**

Test Analyze Intent submission sends prior `messages[]`, successful submissions append user/assistant session turns, incoming pending SSE review gets `intent-review--unseen`, clicking/Approve/Reject clears unseen, and Similar Changes loads/renders source/status/score.

```tsx
expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/api/intent-review'),
  expect.objectContaining({body: expect.stringContaining('"messages"')}));
expect(screen.getByTestId('intent-review-r1')).toHaveClass('intent-review--unseen');
```

- [ ] **Step 3: Run UI tests and confirm failure**

Run: `cd frontend && npm test -- --runInBand`
Expected: FAIL because submission/unseen/similar behavior is absent.

- [ ] **Step 4: Implement minimal UI behavior**

Add session `ChatMessage[]`, `unseenIntentIds`, `activeIntentReviewId`, and `similarChanges`. Add explicit `Analyze Intent` button because Composer currently has no send action. On success, clear input, store current user turn plus compact system acknowledgement, and let SSE/list state reconcile by ID. Add notification badge, finite CSS pulse (respect `prefers-reduced-motion`), seen-on-open semantics, and Similar Changes fetch/render. Preserve recommendation debounce.

- [ ] **Step 5: Run UI tests, lint, and build**

Run: `cd frontend && npm test -- --runInBand && npm run lint && npm run build`
Expected: tests PASS; lint/build exit 0.

- [ ] **Step 6: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/vitest.config.ts frontend/app/page.tsx frontend/app/page.module.css frontend/app/intent-ui.test.tsx
git commit -m "feat: review and retrieve prompt intents"
```

### Task 8: History-aware hooks and operator documentation

**Files:**
- Modify: `integrations/claude-code/loomi-intent-hook.sh`
- Modify: `integrations/codex/loomi_codex_notify.py`
- Modify: `integrations/README.md`
- Modify: `.env.example`
- Modify: `docs/RUNNING.md`

- [ ] **Step 1: Add hook contract smoke tests or shell/Python fixtures**

Extend existing hook test location or add `tests/integrations/test_hooks.py` to run payload conversion without network. Assert transcript-derived messages when available and `[]` fallback otherwise.

- [ ] **Step 2: Run tests and confirm failure**

Run: `pytest tests/integrations/test_hooks.py -q`
Expected: FAIL because converters omit history.

- [ ] **Step 3: Extend hooks and docs**

Send `messages`, stable `external_id` when native hook payload supplies one, and source metadata. Document GitHub webhook URL, `application/json`, push event selection, secret configuration, local tunnel requirement for github.com reaching localhost, retry/similar endpoints, and data redaction. Add empty `GITHUB_WEBHOOK_SECRET=` to `.env.example`.

- [ ] **Step 4: Run hook tests**

Run: `pytest tests/integrations/test_hooks.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add integrations tests/integrations .env.example docs/RUNNING.md
git commit -m "docs: configure intent review hooks"
```

### Task 9: Full verification and memory

**Files:**
- Modify: `memory/web-demo.md`

- [ ] **Step 1: Run full offline backend suite safely**

Run: `docker compose exec -T -e DATABASE_URL= -e CHROMA_HOST= core python -m pytest -q`
Expected: all offline tests PASS; live provider test skipped.

- [ ] **Step 2: Run gateway and frontend verification**

Run: `docker compose exec -T api npm test -- --runInBand`
Expected: all Jest tests PASS.

Run: `docker compose exec -T frontend npm test -- --runInBand && docker compose exec -T frontend npm run build`
Expected: UI tests PASS; production build exits 0.

- [ ] **Step 3: Rebuild and smoke local stack**

Run: `docker compose up -d --build`
Expected: five services start; Postgres, Chroma, core, and API report healthy.

Use a generated test secret and signed local webhook request. Verify `202`, SSE/list review appearance, vector `ready`, similar endpoint result, and Approve status synchronization. Do not expose real secrets in output.

- [ ] **Step 4: Append durable memory**

Append completed behavior, decisions, failures/fixes, verification counts, GitHub setup, and remaining limits to `memory/web-demo.md`. Never overwrite prior entries.

- [ ] **Step 5: Final commit**

```bash
git add memory/web-demo.md
git commit -m "docs: record unified intent review delivery"
```
