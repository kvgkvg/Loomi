# Unify Canvas and Pipeline Tabs — Design

Date: 2026-07-12
Status: Approved

## Problem

The delivery UI has two tabs, Canvas (`frontend/app/page.tsx`) and Pipeline
(`frontend/app/pipeline/page.tsx`). They currently look like two separate
products. Canvas follows the Loomi design system (Porcelain/Graphite palette,
Cabinet Grotesk + Geist Mono, `.btn` / `.view-switch` components from
`globals.css`, light/dark aware). Pipeline is a hard-coded GitHub-dark console
(`#0d1117` background, IBM Plex fonts, blue `#58a6ff` accents, GitHub green/red
status colors). We want the two tabs to read as one product without changing
Pipeline's working behavior.

## Decisions

- **Theme scope:** Pipeline stays an always-dark console (fits its log/terminal
  character) but is reskinned to the Loomi Graphite palette. It does not follow
  the light/dark toggle — the console is intentionally always dark.
- **Layout:** Keep Pipeline's existing structure (runs sidebar, horizontal
  stage-node flow, detail/log panel). Retheme only. Do not restructure into the
  Canvas 12-column grid — that would risk the working SSE live-update UI before
  the demo.

## Components

### 1. Shared top navigation (`frontend/app/components/TopNav.tsx`, new)

Extract the 64px sticky nav currently inline in Canvas into a reusable client
component so both tabs share identical chrome.

- Left: brand `Loomi` + `MEM-ORGANIZATION` mono tag + `.view-switch` pill
  (`Canvas | Pipeline`). The component sets `aria-current="page"` on the link
  matching the current path.
- Right: a `children` slot for page-specific controls.
  - Canvas passes the role-lens switcher + system health indicator (unchanged
    markup, moved into the slot).
  - Pipeline passes a repo polling-status indicator
    (`kvgkvg/test_loomi_repo · Polling tracked repository`) and, when a run has a
    linked `asset_id`, the moss "Open in Canvas" pill (`/?asset=...`).
- The nav uses Loomi tokens (`var(--panel-bg)`, `var(--border-color)`, etc.),
  same as today's Canvas nav. On a page that forces dark (Pipeline), the nav
  reads the Pipeline-scoped dark tokens.

Canvas: replace inline `<nav>` markup with `<TopNav>`; no visual change.

Pipeline: the old top bar row (`Git Capture Pipeline` title + duplicate
`Canvas` / `Open in Canvas` buttons) is removed. Navigation now lives in the
shared nav. The pipeline title + stage-flow subtitle
(`capture_commit → process_raw_event → ...`) move into the main column as a
lightweight section header (kept for orientation, not chrome).

### 2. Pipeline retheme — Loomi dark console

Scope the Loomi Graphite palette locally to the Pipeline page (do not mutate
global CSS vars). Color mapping:

| Current (GitHub dark)         | New (Loomi)                                   |
| ----------------------------- | --------------------------------------------- |
| `#0d1117` background          | `#181A19` Graphite Canvas                      |
| `#0a0d12` deep panel          | `#141615` deeper graphite panel               |
| `#21262d` / `#30363d` borders | `#373D38` Structural Line (dark)              |
| `#58a6ff` blue (SHA/active/link) | `#7FA98C` light moss (text on dark) / `#3D6B4F` Moss (fills/active border) |
| `#3fb950` green success       | `#5C8B6B` moss-success text / `#3D6B4F` fill  |
| `#f85149` red / `#ffa198`     | `#A65338` Alert Rust / `#C97B5F` rust-on-dark text |
| `#d29922` amber running       | `#B08A4A` desaturated amber (running only)    |
| `#e6edf3` / `#c9d1d9` text    | `#F4F6F2` Chalk / `#B9C1BB` muted chalk       |
| `#6e7681` / `#8b949e` meta    | `#8A938C` slate-on-dark                       |

- Fonts: drop the IBM Plex `@import`. Body text uses `var(--font-sans)`
  (Cabinet Grotesk); mono uses `var(--font-mono)` (Geist Mono). Replace the
  local `mono` constant accordingly.
- Buttons/pills: reuse `.btn`, `.btn-secondary`, `.btn-ghost` where they fit;
  the human-review Approve button becomes `.btn-primary` (moss).
- `lineColor(text)` log coloring: success (`✓`) → moss `#5C8B6B`; error/`⚠` →
  rust `#C97B5F`; command (`$`/`POST`/`INSERT`/...) → light moss `#7FA98C`;
  default → slate `#8A938C`.
- Status blink dots and stage pulse/spin animations are kept — they signal live
  processing state, which DESIGN.md explicitly allows ("alive only when
  organizational knowledge changes"). Their colors follow the mapping above.

### 3. Behavior — unchanged

No change to: SSE `pipeline_stage` handling, `GET /api/runs` load, run
selection, stage selection, deep links (`?asset=`, `?run=`), or the rationale
approve flow (`POST /api/rationale-review/version/:id/approve`).

## Files touched

- `frontend/app/components/TopNav.tsx` — new shared nav.
- `frontend/app/page.tsx` — replace inline nav with `<TopNav>`; pass role +
  health as children.
- `frontend/app/pipeline/page.tsx` — retheme colors/fonts/buttons; remove old
  top bar; use `<TopNav>` with polling-status + Open-in-Canvas children.
- `frontend/app/globals.css` — minor additions only if a shared class is needed
  (e.g. a nav status-indicator utility). Prefer reusing existing classes.

## Verification (manual, pre-demo)

1. Open `/` and `/pipeline`; confirm the top nav is visually identical and the
   `view-switch` highlights the correct active tab on each.
2. Trigger / observe a pipeline run; confirm stage nodes, log panel, and status
   colors render on the graphite palette with WCAG-AA-readable text.
3. Confirm deep links `/pipeline?asset=<id>` and `?run=<id>` still select the
   matching run, and "Open in Canvas" appears + links correctly.
4. Confirm the human-review approve button still approves and refreshes.
5. Confirm Canvas is visually unchanged after the nav extraction.

## Out of scope

- Light-mode variant of the Pipeline console.
- Restructuring Pipeline into the 12-column grid.
- Any API or pipeline-backend change.
