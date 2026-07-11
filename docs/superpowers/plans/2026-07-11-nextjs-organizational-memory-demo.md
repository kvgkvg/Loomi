# Next.js Organizational Memory Demo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a Compose-run Next.js Narrative Canvas that turns a new Git
prompt commit into a live organizational-memory notification and a grounded
ghost prompt suggestion for another employee's related task.

**Architecture:** Next.js renders the product shell and isolated interactive
client components. Express is the sole browser API and SSE gateway. A thin
FastAPI service delegates to existing Python domain functions, hosts the Git
poller, and talks to PostgreSQL and Chroma through `db/client.py`.

**Tech Stack:** Next.js App Router, TypeScript, Express, FastAPI, PostgreSQL,
psycopg, Chroma, Docker Compose, GSAP, Vitest, Playwright, pytest.

## Global Constraints

- Preserve `capture_commit(commit_sha: str) -> dict` and
  `process_raw_event(raw_event_id: str) -> dict` signatures.
- All Python relational access stays behind `db/client.py`.
- Use `sentence-transformers/all-MiniLM-L6-v2` through Chroma-managed document
  and query embedding; no module selects another embedding model.
- Capture errors never raise through the poll loop; failed raw events stay
  retryable and must not emit `memory_ready`.
- Compose has separately built frontend, API, and core images plus PostgreSQL
  and Chroma services with health checks and persistent volumes.
- The browser talks only to Express. Express returns structured failures and
  never exposes Python stack traces.
- Composer debounce is 650 ms, minimum normalized input is 24 characters, and
  default ghost-suggestion threshold is 0.45.
- Ghost suggestions never edit input until explicit Use prompt; adoption writes
  `asset_usage`.
- Next.js uses App Router, Cabinet Grotesk, Geist Mono, zinc semantic surfaces,
  one Moss Accent, auto light/dark mode, and a strict mobile one-column layout.
- GSAP stays in isolated client components with context cleanup and static
  `prefers-reduced-motion` behavior. Do not attach a global scroll listener.
- Visible product copy contains no emoji, em dash, decorative version label,
  fake metrics, or generic dashboard content.

---

### Task 1: Establish the runnable web workspace and Compose skeleton

**Files:**

- Create: `frontend/package.json`
- Create: `frontend/app/layout.tsx`
- Create: `api/package.json`
- Create: `docker-compose.yml`
- Modify: `.gitignore`

**Interfaces:**

- Produces: `frontend` Next.js service on port 3000 and `api` Express service on port 3001.
- Produces: Docker service names `frontend`, `api`, `core`, `postgres`, `chroma`.

- [ ] **Step 1: Write failing smoke tests and service manifests**

Create Vitest tests that assert the API health route responds and Next.js has a
root route. Define scripts `test`, `build`, and `dev` in each package before
implementation.

```ts
it("returns an API health envelope", async () => {
  const response = await request(app).get("/api/health");
  expect(response.status).toBe(200);
  expect(response.body).toMatchObject({ status: "healthy" });
});
```

- [ ] **Step 2: Run tests to verify red state**

Run: `npm --prefix api test -- --run`

Expected: FAIL because the Express application does not exist.

- [ ] **Step 3: Add the minimum workspace and Compose configuration**

Create Next.js App Router and Express entry points, Dockerfiles, Compose
services, named volumes, and health checks. Add `.superpowers/` and local
runtime state to `.gitignore` without ignoring source artifacts.

- [ ] **Step 4: Verify local and container baseline**

Run: `npm --prefix api test -- --run && npm --prefix frontend run build && docker compose config`

Expected: all commands exit 0.

- [ ] **Step 5: Commit**

```bash
git add frontend api docker-compose.yml .gitignore
git commit -m "feat: scaffold Next.js demo runtime"
```

### Task 2: Make Python storage portable to Compose

**Files:**

- Modify: `db/client.py`
- Create: `db/schema.postgres.sql`
- Modify: `db/schema.sql`
- Create: `tests/db/test_postgres_compat.py`
- Modify: `requirements.txt`

**Interfaces:**

- Produces: `get_pg_connection()` selecting PostgreSQL from `DATABASE_URL` and
  SQLite otherwise.
- Produces: `get_vector_collection()` selecting remote Chroma from
  `CHROMA_HOST` and embedded Chroma otherwise.

- [ ] **Step 1: Write failing storage-contract tests**

```python
def test_postgres_adapter_accepts_sqlite_style_placeholders(monkeypatch):
    connection = make_fake_postgres_connection()
    monkeypatch.setenv("DATABASE_URL", "postgresql://example")
    monkeypatch.setattr(client, "_connect_postgres", lambda _: connection)
    client.get_pg_connection().execute("SELECT * FROM assets WHERE id = ?", ("a-1",))
    assert connection.last_query == "SELECT * FROM assets WHERE id = %s"
```

- [ ] **Step 2: Verify red state**

Run: `pytest tests/db/test_postgres_compat.py -v`

Expected: FAIL because no PostgreSQL adapter exists.

- [ ] **Step 3: Implement adapters and schemas**

Use a small DB-API compatibility wrapper, not an ORM. Add PostgreSQL schema
with poll-state storage and retain current SQLite schema/test behavior. Keep
the Chroma document/query call style unchanged.

- [ ] **Step 4: Verify both paths**

Run: `pytest tests/db/test_client.py tests/db/test_postgres_compat.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add db requirements.txt tests/db
git commit -m "feat: support PostgreSQL and remote Chroma"
```

### Task 3: Add the thin Python core API and lifecycle event boundary

**Files:**

- Create: `core_service/app.py`
- Create: `core_service/events.py`
- Create: `tests/core_service/test_app.py`
- Create: `tests/core_service/test_events.py`
- Modify: `requirements.txt`

**Interfaces:**

- Produces: `GET /health`, `POST /recommend`, `GET /assets/{asset_id}`,
  `POST /assets/{asset_id}/explain`, `POST /assets/{asset_id}/use`, and an
  internal lifecycle stream.
- Consumes: existing `recommend`, `explain_asset`, capture, and database
  contracts without reimplementing them.

- [ ] **Step 1: Write failing endpoint and event tests**

```python
def test_ready_event_is_published_only_after_successful_capture(client, monkeypatch):
    monkeypatch.setattr(app, "process_raw_event", lambda _: {"embedded": True, "asset_id": "a1"})
    response = client.post("/internal/capture", json={"commit_sha": "abc"})
    assert response.status_code == 202
    assert events.pop() == {"type": "memory_ready", "asset_id": "a1"}
```

- [ ] **Step 2: Verify red state**

Run: `pytest tests/core_service -v`

Expected: FAIL because `core_service` does not exist.

- [ ] **Step 3: Implement thin FastAPI delegation**

Make handlers validate inputs, call current domain functions, return safe
result objects, and publish lifecycle events only after confirmed `embedded`.

- [ ] **Step 4: Verify green state**

Run: `pytest tests/core_service -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add core_service tests/core_service requirements.txt
git commit -m "feat: expose Python core service"
```

### Task 4: Add retry-safe Git polling

**Files:**

- Create: `core_service/poller.py`
- Create: `tests/core_service/test_poller.py`
- Modify: `core_service/app.py`
- Modify: `db/client.py`

**Interfaces:**

- Produces: `GitPoller.poll_once() -> None`, one core-owned background poller.
- Consumes: `capture_commit`, `process_raw_event`, persisted poll state, and
  `publish(event)`.

- [ ] **Step 1: Write failing poller tests**

```python
def test_unchanged_head_is_not_recaptured(fake_repo, poller):
    fake_repo.head = "abc"
    poller.poll_once()
    poller.poll_once()
    assert fake_repo.capture_calls == ["abc"]
```

- [ ] **Step 2: Verify red state**

Run: `pytest tests/core_service/test_poller.py -v`

Expected: FAIL because `GitPoller` is unavailable.

- [ ] **Step 3: Implement minimum poll loop**

Persist observed and processed SHA, poll at three seconds by default, use
bounded backoff for failure, retain `processed=false`, and emit retry rather
than success when a pipeline result is not embedded.

- [ ] **Step 4: Verify green state**

Run: `pytest tests/core_service/test_poller.py tests/capture_pipeline/test_process.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add core_service db/client.py tests/core_service
git commit -m "feat: poll Git changes safely"
```

### Task 5: Build the Express public gateway

**Files:**

- Create: `api/src/app.ts`
- Create: `api/src/core-client.ts`
- Create: `api/src/events.ts`
- Create: `api/test/app.test.ts`
- Create: `api/test/events.test.ts`

**Interfaces:**

- Produces: `GET /api/health`, `GET /api/events/stream`, `POST /api/recommend`,
  asset review, explain, and use routes.
- Consumes: internal Python HTTP endpoints and lifecycle events.

- [ ] **Step 1: Write failing gateway tests**

```ts
it("maps a core timeout to a safe 503 response", async () => {
  coreClient.recommend.mockRejectedValue(new TimeoutError());
  const response = await request(app).post("/api/recommend").send({ task: "Build lead routing" });
  expect(response.status).toBe(503);
  expect(response.body).toEqual({ error: { code: "CORE_UNAVAILABLE" } });
});
```

- [ ] **Step 2: Verify red state**

Run: `npm --prefix api test -- --run`

Expected: FAIL because gateway modules do not exist.

- [ ] **Step 3: Implement REST, timeout, health, and SSE fanout**

Validate public inputs with a small schema library, use one bounded internal
HTTP timeout, aggregate downstream health, and fan out capture lifecycle events
as SSE. Keep browser-specific policy here only.

- [ ] **Step 4: Verify green state**

Run: `npm --prefix api test -- --run`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add api
git commit -m "feat: add Express memory gateway"
```

### Task 6: Build the accessible Next.js Narrative Canvas

**Files:**

- Create: `frontend/app/page.tsx`
- Create: `frontend/components/task-composer.tsx`
- Create: `frontend/components/asset-review.tsx`
- Create: `frontend/components/memory-event.tsx`
- Create: `frontend/test/task-composer.test.tsx`

**Interfaces:**

- Consumes: Express `/api/health`, `/api/recommend`, asset routes, and SSE.
- Produces: top narrative event, task composer, ghost suggestion, review, and
  explicit use prompt behavior.

- [ ] **Step 1: Write failing interaction tests**

```tsx
it("shows a ghost suggestion after a 650 ms pause without changing task text", async () => {
  render(<TaskComposer />);
  await userEvent.type(screen.getByLabelText("Assigned task"), "Design a lead classification workflow");
  await advanceTimersByTimeAsync(650);
  expect(await screen.findByText("Lead qualification prompt")).toBeVisible();
  expect(screen.getByLabelText("Assigned task")).toHaveValue("Design a lead classification workflow");
});
```

- [ ] **Step 2: Verify red state**

Run: `npm --prefix frontend test -- --run`

Expected: FAIL because narrative components are unavailable.

- [ ] **Step 3: Implement minimum accessible UI**

Follow `DESIGN.md`: Cabinet Grotesk, Geist Mono, zinc tokens, one Moss Accent,
7/5 desktop layout, one-column mobile collapse, meaningful status regions, and
complete loading/empty/degraded/error states. Abort stale requests and gate
results by 24 characters and score 0.45.

- [ ] **Step 4: Verify green state and build**

Run: `npm --prefix frontend test -- --run && npm --prefix frontend run build`

Expected: PASS and a successful production build.

- [ ] **Step 5: Commit**

```bash
git add frontend
git commit -m "feat: add narrative memory canvas"
```

### Task 7: Add isolated GSAP narrative motion and UI quality checks

**Files:**

- Create: `frontend/components/narrative-motion.tsx`
- Create: `frontend/components/evidence-motion.tsx`
- Create: `frontend/test/motion.test.tsx`
- Modify: `frontend/app/page.tsx`
- Modify: `frontend/app/globals.css`

**Interfaces:**

- Produces: client-only GSAP narrative and evidence effects that are optional
  enhancements to the static functional UI.

- [ ] **Step 1: Write failing reduced-motion and cleanup tests**

```tsx
it("renders static evidence when reduced motion is requested", () => {
  mockReducedMotion(true);
  render(<EvidenceMotion><p>Constraint</p></EvidenceMotion>);
  expect(screen.getByText("Constraint")).toBeVisible();
  expect(registerScrollTrigger).not.toHaveBeenCalled();
});
```

- [ ] **Step 2: Verify red state**

Run: `npm --prefix frontend test -- --run motion.test.tsx`

Expected: FAIL because the motion modules do not exist.

- [ ] **Step 3: Implement minimal GSAP islands**

Use `@gsap/react` context cleanup. Apply the selected scrubbed rationale reveal
and desktop evidence-title pin only when reduced motion is off. Animate opacity
and transform only. Do not add a global scroll handler.

- [ ] **Step 4: Verify green state**

Run: `npm --prefix frontend test -- --run motion.test.tsx && npm --prefix frontend run build`

Expected: PASS and build success.

- [ ] **Step 5: Commit**

```bash
git add frontend
git commit -m "feat: add purposeful narrative motion"
```

### Task 8: Verify the real demo end to end

**Files:**

- Create: `scripts/demo_git_memory_flow.sh`
- Create: `tests/e2e/memory-flow.spec.ts`
- Modify: `README.md`
- Modify: `docker-compose.yml`
- Modify: `memory/web-demo.md`

**Interfaces:**

- Produces: a reproducible operator flow from prompt-changing commit through
  notification, recommendation, review, and adoption.

- [ ] **Step 1: Write failing browser-flow test**

```ts
test("commit becomes a notification and then a ghost prompt", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("A prompt changed")).toBeVisible();
  await page.getByLabel("Assigned task").fill("Design a lead-classification workflow for sales");
  await expect(page.getByText("Lead qualification prompt")).toBeVisible();
});
```

- [ ] **Step 2: Verify red state**

Run: `npm --prefix frontend run test:e2e -- memory-flow.spec.ts`

Expected: FAIL until the full stack and deterministic demo fixture exist.

- [ ] **Step 3: Add deterministic seed, operator script, and documentation**

Create a temporary prompt change in a configured demo repository, wait for one
`memory_ready` event, and document exact launch, reset, and troubleshooting
commands. Do not include credentials or fake success output.

- [ ] **Step 4: Run full verification**

Run: `pytest -m "not live" -v && npm --prefix api test -- --run && npm --prefix frontend test -- --run && npm --prefix frontend run build && docker compose up --build --wait && openspec validate build-nextjs-organizational-memory-demo`

Expected: every command exits 0; then run the browser flow and inspect console
and network errors in the in-app browser.

- [ ] **Step 5: Commit**

```bash
git add scripts tests/e2e README.md docker-compose.yml memory/web-demo.md
git commit -m "test: verify organizational memory demo flow"
```
