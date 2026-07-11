## Context

Loomi currently has tested Python modules for Git capture, retry-safe rationale
extraction, Chroma recommendation, and grounded onboarding. The repository has
no browser UI or network API, and `db/client.py` currently creates embedded
SQLite and Chroma clients. The demo must preserve those contracts while adding
a Next.js product surface, an Express public gateway, PostgreSQL, live Git
notifications, and a reproducible Compose runtime.

The primary stakeholder is an AI Lead demonstrating one employee's prompt
change being discovered and reused by another employee. The implementation is
time-constrained, must remain understandable by the hackathon team, and must
not turn the Express layer into a second domain implementation.

## Goals / Non-Goals

**Goals:**

- Deliver one narrative canvas connecting Git capture to proactive task-time
  reuse.
- Preserve the existing Python function signatures and single embedding model.
- Make Express the only browser-facing API and event boundary.
- Run all runtime dependencies through one health-checked Compose stack.
- Keep offline Python tests fast through the existing SQLite fallback.
- Provide deterministic loading, empty, degraded, retry, and success states.

**Non-Goals:**

- Rewriting Python domain logic in TypeScript.
- Full authentication, RBAC, governance, or cross-department policy.
- Graph storage, multi-branch asset identity, or multi-environment rollout.
- A generic workflow builder, admin dashboard, or production Git webhook fleet.
- Shipping motion-anything as an application dependency.

## Decisions

### Next.js App Router with small client islands

The frontend uses Next.js App Router. The page shell, typography, and initial
health/event content render as Server Components. The task composer, SSE
subscription, notification arrival, and asset-review transitions are isolated
Client Components because they require browser state and Motion values.

Alternative considered: a client-only single-page application. It is rejected
because the approved stack requires Next.js and benefits from a server-rendered
shell with isolated interactive client components.

### Express is the public gateway

The browser calls Express for REST and Server-Sent Events. Express validates
payloads, applies timeouts, normalizes errors, records usage, and proxies domain
operations to the internal Python service. Next.js route handlers do not
duplicate these APIs.

Alternative considered: expose FastAPI directly. It is simpler but removes the
requested Node/Express boundary and spreads browser policy into the Python core.

### Thin Python HTTP wrapper

FastAPI exposes health, capture/process, recommendation, asset evidence, and
explanation endpoints. Handlers delegate to existing functions and translate
safe result objects into HTTP responses. Domain logic remains in the existing
modules.

Alternative considered: Express subprocess calls. It avoids one service but
creates weak timeout, concurrency, lifecycle, and logging behavior.

### PostgreSQL compatibility stays inside `db/client.py`

`DATABASE_URL` selects PostgreSQL via psycopg in Compose; absence of that
variable selects SQLite. A small connection adapter normalizes mapping rows and
placeholder syntax so existing callers can keep their shared connection
contract. PostgreSQL uses its own schema bootstrap file; SQLite keeps the
existing schema and test behavior.

Alternative considered: migrate all data access to an ORM. It creates a large
cross-cutting rewrite with no hackathon-demo benefit.

### Chroma supports remote and embedded modes

`CHROMA_HOST` selects `chromadb.HttpClient` in Compose, while
`LOOMI_CHROMA_PATH` retains `PersistentClient` for offline tests and CLI use.
Documents and queries continue through Chroma's default MiniLM embedding
function so capture and recommendation cannot select different models.

### Git polling belongs to the Python core service

A single background poller observes the configured repository every three
seconds. PostgreSQL stores observed and processed SHAs. The poller routes all
work through existing capture/process functions, retries unprocessed events
with bounded backoff, and emits lifecycle events only from confirmed results.

Alternative considered: poll from Express. It would force Node to understand
Python retry state and duplicate orchestration knowledge.

### SSE transports lifecycle events

The Python core publishes lifecycle events to Express through an internal
stream; Express fans them out to browsers through `/api/events/stream`. SSE is
unidirectional, reconnectable, and sufficient for notifications. WebSocket is
not added because the browser sends normal REST actions.

### Recommendation remains cancellable and conservative

The composer waits 650 milliseconds after edits, requires 24 normalized
characters, aborts stale requests, and shows only the top result at score 0.45
or above. The threshold is an environment calibration knob because retrieval
scores depend on the demo corpus. A suggestion never edits user input until
Use prompt is selected.

### Visual system and motion

The narrative canvas uses Geist and Geist Mono, automatic light/dark semantic
tokens, neutral zinc surfaces, one muted green accent, panel radius 14px, input
radius 12px, and pill actions. Motion is limited to notification arrival,
suggestion appearance, and review-panel transitions and becomes immediate under
reduced motion. motion-anything is used only to inspect and adapt these focused
patterns during development.

### Container topology

Compose builds separate `frontend`, `api`, and `core` images and runs official
PostgreSQL and Chroma images. Each service has a health check; named volumes
persist relational and vector state. Service readiness, not startup order
alone, gates dependencies.

## Risks / Trade-offs

- [PostgreSQL differs from current SQLite SQL behavior] -> keep dialect changes
  behind `db/client.py`, add contract tests against both backends, and avoid ORM
  migration.
- [Chroma remote mode may embed in a different process than expected] -> assert
  collection metadata and run a known semantic query during Compose smoke tests.
- [Git poller processes an unrelated commit] -> configure captured path filters
  and retain the adapter's existing prompt/workflow/agent-config classification.
- [SSE clients miss events while disconnected] -> reconnect automatically and
  refresh the latest memory feed after reconnection; historical event replay is
  outside MVP scope.
- [A fixed recommendation threshold is corpus-sensitive] -> keep a documented
  default and one environment calibration value, then verify against seeded and
  captured demo tasks.
- [Multiple core replicas could poll the same repository] -> Compose runs one
  core replica for MVP; distributed locking is deferred until horizontal scale.
- [LLM/network delays weaken the live demo] -> expose processing state, preserve
  retry semantics, seed one known asset, and never fabricate a success event.

## Migration Plan

1. Add OpenSpec contracts and keep the current Python suite green.
2. Add PostgreSQL and remote-Chroma modes behind existing client functions.
3. Add the thin Python HTTP wrapper and Git poller with focused tests.
4. Add Express REST/SSE gateway and contract tests.
5. Add the Next.js narrative canvas and component tests.
6. Add Dockerfiles, Compose health checks, seed/bootstrap commands, and docs.
7. Run the offline suites, Compose smoke test, and real browser demo flow.

Rollback removes the web/API services and unsets `DATABASE_URL` and
`CHROMA_HOST`; the existing Python CLI returns to SQLite and embedded Chroma
without a data-destructive migration. Compose volumes are retained unless the
operator explicitly removes them.

## Open Questions

None. Implementation thresholds, boundaries, and scope are fixed by the
approved design and capability specs.
