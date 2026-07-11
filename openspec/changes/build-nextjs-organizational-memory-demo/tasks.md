## 1. Workspace and Runtime Foundations

- [ ] 1.1 Create the Next.js frontend and Express API workspaces with TypeScript, test scripts, and shared environment examples.
- [ ] 1.2 Add Dockerfiles and a Compose stack for frontend, API, core, PostgreSQL, and Chroma with persistent volumes and health checks.
- [ ] 1.3 Add repository ignore rules for local Compose state and visual-companion artifacts.

## 2. Storage Compatibility

- [ ] 2.1 Add PostgreSQL selection to `db/client.py` while preserving SQLite test behavior and the existing public client functions.
- [ ] 2.2 Add PostgreSQL schema bootstrap and persisted Git poll state.
- [ ] 2.3 Add contract tests for SQLite and PostgreSQL-compatible placeholder and row behavior.
- [ ] 2.4 Add remote Chroma configuration while retaining embedded Chroma fallback and the fixed MiniLM embedding behavior.

## 3. Core Service and Capture Events

- [ ] 3.1 Add a thin FastAPI service that delegates health, recommend, asset review, explanation, and usage operations to existing Python modules.
- [ ] 3.2 Add capture lifecycle event publishing and focused tests proving that `memory_ready` follows relational and vector persistence only.
- [ ] 3.3 Add a bounded-backoff Git poller with persisted SHA state, duplicate prevention, and retry-safe tests.

## 4. Express Gateway

- [ ] 4.1 Add Express request validation, Python-core proxy endpoints, timeout normalization, and health aggregation.
- [ ] 4.2 Add a reconnectable SSE endpoint that fans out internal capture lifecycle events to browser clients.
- [ ] 4.3 Add Express integration tests for successful proxying, timeout safety, degraded health, and SSE event mapping.

## 5. Next.js Narrative Canvas

- [ ] 5.1 Add global theme, Cabinet Grotesk and Geist Mono typography, semantic tokens, and the shared accessible layout primitives from `DESIGN.md`.
- [ ] 5.2 Add the server-rendered narrative shell, latest-memory feed, health state, and responsive navigation.
- [ ] 5.3 Add the client task composer with 650 ms debounce, 24-character gate, stale-request cancellation, and threshold-gated ghost suggestion.
- [ ] 5.4 Add grounded asset review, explanation, explicit Use prompt adoption, and contextual empty/loading/error states.
- [ ] 5.5 Add isolated GSAP narrative and evidence modules with reduced-motion fallback and no global scroll listener.
- [ ] 5.6 Add component and accessibility tests for keyboard flow, mobile collapse, dark mode, debounce, cancellation, and adoption behavior.

## 6. Integrated Demo Verification

- [ ] 6.1 Add a deterministic demo seed and documented command sequence that creates a prompt-changing Git commit.
- [ ] 6.2 Add Compose smoke and browser flow verification from captured commit to SSE notification to ghost suggestion to prompt adoption.
- [ ] 6.3 Run the existing Python suite, Node suites, builds, Compose health checks, browser console/network checks, and OpenSpec validation.
