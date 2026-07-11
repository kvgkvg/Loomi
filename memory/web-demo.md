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
