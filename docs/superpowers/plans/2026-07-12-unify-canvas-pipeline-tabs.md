# Unify Canvas and Pipeline Tabs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Canvas and Pipeline tabs read as one product by sharing a top-nav component and reskinning the Pipeline console to the Loomi Graphite palette, without changing Pipeline behavior.

**Architecture:** Extract Canvas's inline 64px nav into a reusable `TopNav` client component with a `children` slot for page-specific controls; both pages render it. Then remap every hard-coded GitHub-dark color/font/button in `pipeline/page.tsx` to Loomi tokens, keeping the existing sidebar + stage-flow + log-panel layout and all SSE/deep-link/approve logic untouched.

**Tech Stack:** Next.js 16.2.10 (App Router), React 19, TypeScript, plain CSS (`globals.css` design tokens). No test runner in this project — verification is `npm run build` (typecheck) + `npm run lint` + manual visual check.

## Global Constraints

- Loomi palette only (DESIGN.md §2): Graphite `#181A19`, Chalk `#F4F6F2`, Moss `#3D6B4F`, Moss Soft `#C9D9CC`, Slate `#66706A`, Structural Line dark `#373D38`, Alert Rust `#A65338`. Never pure black/white, blue neon, or purple.
- Fonts: Cabinet Grotesk via `var(--font-sans)`; Geist Mono via `var(--font-mono)`. Banned: Inter, IBM Plex, serif.
- No em dash character in visible copy.
- Do NOT change any API call, SSE handler, deep-link parsing, or the approve flow in `pipeline/page.tsx`.
- All work is under `frontend/`. Run every command from `frontend/`.
- Read `node_modules/next/dist/docs/` before using unfamiliar Next.js APIs (this is Next 16, not the training-data Next).

---

### Task 1: Extract shared `TopNav` component

**Files:**
- Create: `frontend/app/components/TopNav.tsx`
- Modify: `frontend/app/page.tsx` (replace inline `<nav>` at lines ~471-540 with `<TopNav>`)

**Interfaces:**
- Produces: `export default function TopNav({ children }: { children?: React.ReactNode }): JSX.Element`. Renders the 64px sticky nav: brand `Loomi` + `MEM-ORGANIZATION` mono tag + `.view-switch` pill (`Canvas | Pipeline`) with `aria-current="page"` set from `usePathname()`. Renders `children` right-aligned in the nav's right slot.
- Consumes: nothing from other tasks.

- [ ] **Step 1: Create the component**

Create `frontend/app/components/TopNav.tsx`:

```tsx
"use client";

import React from 'react';
import { usePathname } from 'next/navigation';

// Shared 64px product nav for Canvas and Pipeline. The `children` slot holds
// page-specific controls (Canvas: role + health; Pipeline: polling status +
// open-in-canvas). aria-current marks the active tab from the current path.
export default function TopNav({ children }: { children?: React.ReactNode }) {
  const pathname = usePathname();
  const onPipeline = pathname?.startsWith('/pipeline');

  return (
    <nav style={{
      height: '64px',
      borderBottom: '1px solid var(--border-color)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: '0 24px',
      backgroundColor: 'var(--panel-bg)',
      backdropFilter: 'blur(10px)',
      position: 'sticky',
      top: 0,
      zIndex: 100,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{ fontWeight: 600, fontSize: '18px', color: 'var(--text-primary)' }}>Loomi</span>
          <span style={{
            fontSize: '11px',
            fontFamily: 'var(--font-mono)',
            padding: '2px 6px',
            border: '1px solid var(--accent-color)',
            color: 'var(--accent-color)',
            borderRadius: '4px',
          }}>MEM-ORGANIZATION</span>
        </div>
        <nav className="view-switch" aria-label="Product views">
          <a href="/" aria-current={onPipeline ? undefined : 'page'}>Canvas</a>
          <a href="/pipeline" aria-current={onPipeline ? 'page' : undefined}>Pipeline</a>
        </nav>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
        {children}
      </div>
    </nav>
  );
}
```

- [ ] **Step 2: Import TopNav in Canvas**

In `frontend/app/page.tsx`, add after the existing imports (after line 5):

```tsx
import TopNav from './components/TopNav';
```

- [ ] **Step 3: Replace the inline nav in Canvas with `<TopNav>`**

In `frontend/app/page.tsx`, the inline nav currently spans from `{/* 1. TOP NAVIGATION */}` / `<nav style={{ height: '64px' ...` through its closing `</nav>` (around lines 470-540). Replace that whole block with:

```tsx
      {/* 1. TOP NAVIGATION */}
      <TopNav>
        {/* Role lens switcher — personalization, not access control */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span className="mono-text" style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Viewing as</span>
          <select
            value={role}
            onChange={(e) => handleRoleChange(e.target.value)}
            className="mono-text"
            style={{
              fontSize: '12px',
              padding: '4px 8px',
              borderRadius: '6px',
              border: '1px solid var(--border-color)',
              backgroundColor: 'var(--panel-bg)',
              color: 'var(--text-primary)',
              cursor: 'pointer',
            }}
          >
            {ROLE_PRESETS.map(r => (
              <option key={r} value={r}>{r}</option>
            ))}
          </select>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span style={{
            width: '8px',
            height: '8px',
            borderRadius: '50%',
            backgroundColor: health.status === 'ok' ? 'var(--accent-color)' : 'var(--alert-color)',
            display: 'inline-block',
          }} />
          <span className="mono-text" style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
            System: {health.status === 'ok' ? 'HEALTHY' : 'DEGRADED'}
          </span>
        </div>
      </TopNav>
```

Confirm the brand + view-switch markup you removed is NOT duplicated (it now lives only in TopNav).

- [ ] **Step 4: Typecheck + lint**

Run from `frontend/`:
```bash
npm run build && npm run lint
```
Expected: build succeeds, no type errors, no new lint errors.

- [ ] **Step 5: Manual visual check (Canvas unchanged)**

Run `npm run dev`, open `http://localhost:3000/`. Confirm the nav looks identical to before: brand, MEM-ORGANIZATION tag, `Canvas | Pipeline` pill with Canvas active, role dropdown, health dot on the right.

- [ ] **Step 6: Commit**

```bash
git add frontend/app/components/TopNav.tsx frontend/app/page.tsx
git commit -m "refactor: extract shared TopNav component from Canvas"
```

---

### Task 2: Adopt `TopNav` in Pipeline and remove the old top bar

**Files:**
- Modify: `frontend/app/pipeline/page.tsx` (add import; wrap page; remove old top-bar row lines ~286-326; move title into main column)

**Interfaces:**
- Consumes: `TopNav` from Task 1 (`import TopNav from '../components/TopNav'`).
- Produces: nothing new; behavior preserved.

- [ ] **Step 1: Import TopNav**

In `frontend/app/pipeline/page.tsx`, after line 3 (`import React, { useEffect, useState } from 'react';`):

```tsx
import TopNav from '../components/TopNav';
```

- [ ] **Step 2: Restructure the page root to stack nav over the console**

The current root `<div style={{ height: '100vh', width: '100%', display: 'flex', ...}}>` puts sidebar + main side-by-side. Wrap it so `TopNav` sits above. Change the outer return so it is:

```tsx
  return (
    <div style={{ height: '100vh', width: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      <TopNav>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--accent-color)', display: 'inline-block', animation: 'blinkDot 1.6s ease-in-out infinite' }} />
          <span className="mono-text" style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
            Polling {'kvgkvg/test_loomi_repo'}
          </span>
        </div>
        {linkedAssetId && (
          <a href={`/?asset=${encodeURIComponent(linkedAssetId)}`} className="btn btn-primary" style={{ minHeight: '36px', padding: '6px 14px', fontSize: '13px' }} title="Open this asset on the Narrative Canvas">
            Open in Canvas
          </a>
        )}
      </TopNav>
      <div style={{ flex: 1, minHeight: 0, display: 'flex', background: '#181A19', color: '#F4F6F2', fontFamily: 'var(--font-sans)', overflow: 'hidden' }}>
```

Note: this replaces the OLD root `<div ...display:'flex'...>`. The old root's `background: '#0d1117'` etc. move onto this inner flex row (retheme values applied here already). Add a matching extra `</div>` before the final `</div>);` at the end of the component to close the new wrapper (the file ends with `</div>\n  );`—add one more `</div>` above it).

- [ ] **Step 3: Delete the old in-console top bar**

Remove the entire `{/* top bar */}` block — the `<div>` starting `{/* top bar */}` / `<div style={{ flex: 'none', display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '16px 28px', borderBottom: '1px solid #21262d', gap: 16 }}>` through its closing `</div>` (originally lines ~286-326). Its title + subtitle move into the run-summary area in the next step; its duplicate `Canvas` and `Open in Canvas` links are dropped (TopNav owns navigation).

- [ ] **Step 4: Add a lightweight pipeline title above the run summary**

Immediately inside `<div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, overflow: 'hidden' }}>` (the MAIN column), before the `{!active ? (` conditional, insert:

```tsx
        <div style={{ flex: 'none', padding: '14px 28px 10px', borderBottom: '1px solid #373D38' }}>
          <div style={{ fontSize: 15, fontWeight: 600, color: '#F4F6F2' }}>Git Capture Pipeline</div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11.5, color: '#8A938C', marginTop: 2 }}>
            capture_commit → process_raw_event → extract_rationale → embed → finalize
          </div>
        </div>
```

- [ ] **Step 5: Typecheck + lint**

Run from `frontend/`:
```bash
npm run build && npm run lint
```
Expected: build succeeds. If `linkedAssetId` is referenced in `TopNav` children before its declaration, move the `<TopNav>` usage after the `const linkedAssetId = ...` computation — it already sits inside the render body after those consts, so no change is needed; just confirm no "used before declaration" error.

- [ ] **Step 6: Manual visual check**

`npm run dev`, open `/pipeline`. Confirm: shared TopNav on top with Pipeline tab active; right slot shows Polling status and (when a run has an asset) Open in Canvas; the old duplicate title-bar buttons are gone; the "Git Capture Pipeline" title appears above the run list content. Deep-link `/pipeline?run=<id>` still selects a run.

- [ ] **Step 7: Commit**

```bash
git add frontend/app/pipeline/page.tsx
git commit -m "refactor: use shared TopNav in Pipeline, drop duplicate top bar"
```

---

### Task 3: Reskin Pipeline colors and fonts to the Loomi palette

**Files:**
- Modify: `frontend/app/pipeline/page.tsx` (all remaining hard-coded GitHub-dark hex values + font imports/constants)

**Interfaces:**
- Consumes: nothing new.
- Produces: nothing new; purely visual.

Color mapping (apply every occurrence):

| Old | New |
| --- | --- |
| `#0d1117` | `#181A19` |
| `#0a0d12` | `#141615` |
| `#21262d` | `#373D38` |
| `#30363d` | `#373D38` |
| `#161b22` | `#20241F` |
| `#58a6ff` | `#7FA98C` (text/SHA) or `#3D6B4F` (active border/fill) |
| `#3fb950` | `#5C8B6B` (text) / `#3D6B4F` (fill/border) |
| `#2ea043` / `#2ea04355` | `#3D6B4F` / `#3D6B4F55` |
| `#f85149` / `#ffa198` | `#C97B5F` (text on dark) / `#A65338` (border/fill) |
| `#d29922` / `#f0c36a` | `#B08A4A` / `#CBA96A` (amber = running only) |
| `#e6edf3` / `#c9d1d9` | `#F4F6F2` / `#B9C1BB` |
| `#6e7681` / `#8b949e` / `#484f58` | `#8A938C` / `#8A938C` / `#5A625C` |

- [ ] **Step 1: Replace fonts**

In `frontend/app/pipeline/page.tsx`:
- Change `const mono = "'IBM Plex Mono', var(--font-mono), monospace";` (line ~189) to `const mono = "var(--font-mono), monospace";`.
- In the `<style>{...}` block (line ~226), delete the `@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans...IBM+Plex+Mono...')` line entirely.
- Change the root inner flex row `fontFamily: "'IBM Plex Sans', system-ui, sans-serif"` to `fontFamily: 'var(--font-sans)'` (this was already set in Task 2 Step 2 — confirm it reads `var(--font-sans)`).
- Any inline `fontFamily: "'IBM Plex Sans', system-ui, sans-serif"` (e.g. the human-review notice at line ~448) → `fontFamily: 'var(--font-sans)'`.

- [ ] **Step 2: Remap all hard-coded hex colors**

Go through `frontend/app/pipeline/page.tsx` and replace every hex value per the mapping table above. Concretely this covers: sidebar (`background: '#0a0d12'`, borders `#21262d`, brand svg `fill="#8b949e"`→`#8A938C`, polling green `#3fb950`→`#5C8B6B`, run-card SHA `#58a6ff`→`#7FA98C`, active border `#58a6ff`→`#3D6B4F`, message `#c9d1d9`→`#B9C1BB`, meta `#6e7681`→`#8A938C`), the status-color ternaries (`statusColor = '#3fb950'`→`#5C8B6B`, running `#d29922`→`#B08A4A`, failed `#f85149`→`#C97B5F`), the failure banner (`rgba(248,81,73,...)` backgrounds → `rgba(166,83,56,0.10)` bg + `rgba(166,83,56,0.35)` border + text `#C97B5F`), the stage-node status blocks (running amber `#d29922`→`#B08A4A`, success `#2ea043...`→`#3D6B4F...` + `#3fb950`→`#5C8B6B`, failed `#f85149`→`#A65338`/`#C97B5F` text, connector colors), the detail-panel header/status labels, and the Result key/value colors (`#79c0ff`→`#7FA98C`, `#a5d6ff`→`#B9C1BB`).

Also update the `<style>` keyframe `pulseRing` rgba from `rgba(210,153,34,...)` (amber) — keep amber for the running pulse but desaturate to `rgba(176,138,74,0.45)` / `rgba(176,138,74,0)`. Update `.lp-run:hover { background: #161b22 }`→`#20241F`, `.lp-stage:hover { border-color: #58a6ff }`→`#3D6B4F`, `.lp-scroll` thumb `#30363d`→`#373D38`.

- [ ] **Step 3: Update `lineColor` log coloring**

Replace the `lineColor` function body (lines ~69-74) with:

```tsx
function lineColor(text: string) {
  if (text.indexOf('⚠') === 0 || text.indexOf('Error') !== -1) return '#C97B5F';
  if (text.indexOf('✓') !== -1) return '#5C8B6B';
  if (text.indexOf('$') === 0 || text.indexOf('POST') === 0 || text.indexOf('INSERT') === 0 || text.indexOf('UPDATE') === 0 || text.indexOf('COMMIT') === 0) return '#7FA98C';
  return '#8A938C';
}
```

- [ ] **Step 4: Convert the human-review Approve button to `.btn-primary`**

At line ~434, replace the inline-styled `<button ... onClick={approveRationale} ...>` with:

```tsx
                        <button
                          type="button"
                          onClick={approveRationale}
                          disabled={reviewBusy}
                          className="btn btn-primary"
                          style={{ minHeight: '32px', padding: '5px 12px', fontSize: '12px' }}
                        >
                          {reviewBusy ? 'Approving…' : 'Human review: approve'}
                        </button>
```

Keep the review-message color logic but map `#3fb950`→`#5C8B6B` and `#f85149`→`#C97B5F` (line ~452), and the review-notice box amber `#d29922`/`#f0c36a` → `#B08A4A`/`#CBA96A` (line ~448).

- [ ] **Step 5: Grep for stragglers**

Run from `frontend/`:
```bash
grep -nE "#0d1117|#0a0d12|#21262d|#30363d|#161b22|#58a6ff|#3fb950|#2ea043|#f85149|#ffa198|#d29922|#f0c36a|#e6edf3|#c9d1d9|#6e7681|#8b949e|#484f58|IBM Plex" app/pipeline/page.tsx
```
Expected: no output (all remapped). Any hit → remap it per the table.

- [ ] **Step 6: Typecheck + lint**

Run from `frontend/`:
```bash
npm run build && npm run lint
```
Expected: build succeeds, no new lint errors.

- [ ] **Step 7: Manual visual + contrast check**

`npm run dev`, open `/pipeline`. Confirm graphite background, moss accents, rust errors, mono log text readable (WCAG AA) on dark. Trigger or select a run: stage nodes, running pulse, success/fail states, log panel, and the approve button all render in Loomi colors. Confirm the tab now visually matches Canvas's family. Confirm deep links and approve still work (behavior unchanged).

- [ ] **Step 8: Commit**

```bash
git add frontend/app/pipeline/page.tsx
git commit -m "style: reskin Pipeline console to Loomi Graphite palette"
```

---

## Self-Review

**Spec coverage:**
- Shared TopNav (spec §1) → Task 1 + Task 2. ✓
- Canvas nav replaced, no visual change (spec §1) → Task 1 Step 3/5. ✓
- Pipeline old top bar removed, title moved to main column (spec §1) → Task 2 Step 3/4. ✓
- Pipeline retheme colors (spec §2 table) → Task 3 Step 2. ✓
- Fonts to Cabinet Grotesk + Geist Mono, drop IBM Plex (spec §2) → Task 3 Step 1. ✓
- Buttons reuse `.btn*`; approve = `.btn-primary` (spec §2) → Task 2 (Open in Canvas) + Task 3 Step 4. ✓
- `lineColor` remap (spec §2) → Task 3 Step 3. ✓
- Blink/pulse/spin kept, recolored (spec §2) → Task 3 Step 2. ✓
- Behavior unchanged: SSE, runs, deep links, approve (spec §3) → constraint enforced; no task edits those handlers. ✓
- Files touched match spec §"Files touched"; `globals.css` untouched because existing classes suffice (spec allowed "only if needed"). ✓

**Placeholder scan:** No TBD/TODO; every code step shows full code; grep step gives exact command + expected empty output.

**Type consistency:** `TopNav` signature `({ children })` consistent across Task 1 (def) and Task 2 (use). `linkedAssetId`, `reviewBusy`, `approveRationale` reused with existing names/types from the file. No renamed identifiers.

Note: this project has no test runner, so "verify it fails" TDD steps are replaced by `npm run build` (typecheck) + `npm run lint` + explicit manual visual checks — appropriate for a pure visual retheme with no runtime-testable logic change.
