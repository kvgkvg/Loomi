
## 2026-07-12 — Link Narrative Canvas ↔ Pipeline (UI)

### Done
- Professional view switcher on Canvas nav: pill segment `Canvas | Pipeline` (`.view-switch` in globals.css).
- Quiet CTA on feed header: ghost button "Capture pipeline →".
- Per git event card: ghost **Pipeline** (`/pipeline?asset=…`) next to secondary **Review** (Review stays primary action).
- Deep links: `/?asset=` opens Evidence Stack; `/pipeline?asset=` / `?run=` selects matching run.
- Pipeline top bar: pill **Open in Canvas** when `asset_id` present in stage results + outlined **Canvas**.

### Why this pattern
- DESIGN.md: primary moss / secondary outline; ghost for tertiary navigation so it doesn't fight Review.
- Segment control = product chrome (Linear-style), not a random text link.

## 2026-07-12 — frontend/app/page.tsx composer debounce cold start

### Problem
User reports: first-time page load composer does not load recommendations.
Even after typing into composer with content near-identical to a recent
commit, no ghost suggestion appears.

### Root cause
frontend/app/page.tsx (Next.js + FastAPI) had two guards:
- Composer input threshold `< 24 chars` returned early with no fetch.
- Debounce was 650 ms after the threshold.

User composer messages close to short diff lines stayed under 24 chars, so
the recommend fetch was never triggered. The long 650 ms wait also made the
UX feel unresponsive.

### Fix
- Lowered min-char guard `24 -> 6` (still avoids per-keystroke spam but
  matches short commit subjects).
- Lower debounce `650 ms -> 300 ms` per user request.
- Updated helper text "min 24 to match" -> "min 6 to match".

### Verify
`./node_modules/.bin/tsc --noEmit -p .` (frontend) — clean.
`./node_modules/.bin/eslint app/page.tsx` — only pre-existing errors
(foundGitOwner capture, @typescript-eslint/no-explicit-any, html-link),
unchanged from before this fix.

### Open follow-up
If cold start still feels empty, consider:
- Server-side default recommend when composer empty (top assets by usage).
- Placeholder hint inside composer after first idle tick.

## 2026-07-12 — composer persistence across view switch

### Problem
User reports: while typing in the composer and debounce still pending,
switching to /pipeline then back to / (Canvas) loses the composer text,
but the ghost-suggestion eventually appears after they retype. Feels like
suggestions only fire after a view switch round-trip.

### Root cause
frontend/app/page.tsx view-switcher (line 497-500) uses plain `<a href>`
links. Browser full-page navigates between / and /pipeline, unmounting
the Canvas component. `useState` resets -> composerInput back to \"\".
The "appearance of suggestions after a round-trip" is just the user
retyping and the debounce finally firing — coincidental, not causal.

### Fix
- Persist composer draft in `window.localStorage` under key
  `loomi-composer` (mirrors the role-persistence pattern at line 139-147).
  Single effect restores on mount; second effect writes on every change.
- No change to debounce/AbortController logic — already correct.

### Verify
`./node_modules/.bin/tsc --noEmit -p .` — clean.
`./node_modules/.bin/eslint app/page.tsx` — 2 new lint warnings
(setState in effect at line 142/153) match the same pattern already
present for role-restore (line 142 of original). Not a regression;
folder-wide cleanup is out of scope for this fix.

### Open follow-up
- Replace `<a href>` in view-switcher with `next/link` Link (Next.js 16
  SPA navigation would also solve this without localStorage). Currently
  Lint forbids this; flagged by @next/next/no-html-link-for-pages.
- After persist is in, brainstorming a "filled-by-default last session"
  prefilled placeholder in the textarea.

## 2026-07-12 — Chroma host vs container mismatch (root-caused)

### Symptom
Frontend fetch /api/recommend returns [] even though db/seed.py reports
"Seeded 6 assets, 4 users, 6 vectors in Chroma." when run on host.

### Root cause
Backend runs inside Docker (compose: loomi-core -> loomi-chroma HTTP server).
CHROMA_HOST=chroma -> embed/query via http://chroma:8000.
docker-compose.yml mounts `chroma_data:/chroma/data` (a named volume), BUT
inspecting `/chroma/data` inside the running container shows it empty.

Host-side `python -m db.seed` writes to `db/chroma/chroma.sqlite3` on the
host filesystem via PersistentClient(). Backend reads from chroma:8000 HTTP.
Two completely independent Chroma stores. Recommended fix:

```bash
docker exec loomi-core python -m db.seed   # writes to the HTTP-backed store
```

Verified: after running the seed in container, GET /api/recommend for
"triage support ticket" returns 3 real assets with score>=0.24.

### Open follow-up
1. `chroma_data` named volume appears unused (folder empty after seed in
   container). Either chromadb/chroma:0.5.3 image defaults to ephemeral
   storage or compose line needs adjustment. Investigate before relying
   on volume persistence for production.
2. Add a make target / docs note: `seed-in-docker` runs `db.seed` inside
   `loomi-core` so it lands in the right Chroma. Avoid host-only seed in
   demos.
3. If team wants to keep host-side seed for fast iteration, point
   host-side `LOOMI_CHROMA_PATH` at the host port forward of chroma
   (read-only — writes need HTTP).

## 2026-07-12 — bootstrap improvements (Chroma mismatch follow-ups)

### Done
- Confirmed chroma_data volume is real (docker stop+start kept 6 vectors
  and the collection id). Initial empty `/chroma/data` listing earlier
  was a red herring — chromadb/chroma:0.5.3 stores in duckdb+parquet shards,
  not a single sqlite3 file at the root.
- New `Makefile` with `seed` alias, `seed-in-docker`, `seed-host`,
  `docker-up`, `docker-down`, `logs`, `clean`. `make seed` always runs
  inside the container so seeds land where the backend reads.
- `db/seed.py` now calls `_docker_chroma_running()` before wiping/inserting;
  if `loomi-chroma` is up it prints a WARNING pointing at
  `make seed-in-docker`. Host-side seed still works (escape hatch for
  unit tests) but no longer silent about the wrong destination.

### Verify
`make help` -> prints target list.
`.venv/bin/python -m db.seed` -> WARN about docker, then seeds host disk
(as before — local CLI path).
`make seed-in-docker` -> seeds inside loomi-core; lands in chroma:8000
HTTP-backed store.
Recommend API after docker-exec seed:
  task="lead scoring", role="Intern" -> 2 hits, top
  "Lead qualification agent for inbound sales" @0.428 (role-adjusted).

### Open follow-up
- Depending on `docker` CLI on host is brittle for users without Docker
  Desktop installed; the helper just gracefully no-ops (no warning).
- Consider moving the seed entrypoint to a script under `scripts/` so
  non-Makefile users still find it (`scripts/seed_in_docker.py`).

## 2026-07-12 — composer cold-start feedback (UX)

### Problem
First-time users report "no recommendation shows up". Backend can be empty
(docker restart wipes in-memory chroma state if volume mis-mount) or the
composer query falls under the 0.45 strong-match threshold -> frontend
silently cleared `ghostSuggestion` and the panel vanished.

### Fix
frontend/app/page.tsx:
- New state `composerHint` (string|null).
- Reworked recommend useEffect to ALWAYS surface something:
  - score >= 0.45 -> ghostSuggestion + clear hint (existing panel).
  - score  < 0.45 -> ghostSuggestion still rendered as low-match,
    composerHint explains confidence level.
  - empty array  -> composerHint suggests seed/commit.
  - network err  -> composerHint warns backend down.
- composerHint rendered as a small panel under the composer with
  accent-color left border (subtle but visible).

### Why
User typed "Review architecture workflow" -> backend returned n8n
workflow digest @ 0.378 (below 0.45). With old logic the panel
disappeared entirely, looking like the feature was broken. Now the
same input renders the low-match suggestion with explicit 
## 2026-07-12 — composer cold-start feedback (UX)

### Problem
First-time users report "no recommendation shows up". Backend can be empty
(docker restart wipes in-memory chroma state if volume mis-mount) or the
composer query falls under the 0.45 strong-match threshold -> frontend
silently cleared ghostSuggestion and the panel vanished.

### Fix
frontend/app/page.tsx:
- New state composerHint (string|null).
- Reworked recommend useEffect to ALWAYS surface something:
  - score >= 0.45 -> ghostSuggestion + clear hint (existing panel).
  - score  < 0.45 -> ghostSuggestion still rendered as low-match,
    composerHint explains confidence level.
  - empty array  -> composerHint suggests seed/commit.
  - network err  -> composerHint warns backend down.
- composerHint rendered as a small panel under the composer with
  accent-color left border (subtle but visible).

### Why
User typed "Review architecture workflow" -> backend returned n8n
workflow digest @ 0.378 (below 0.45). With old logic the panel
disappeared entirely, looking like the feature was broken. Now the
same input renders the low-match suggestion with explicit %
confidence so the user knows Loomi responded but found weak priors.

### Verify
./node_modules/.bin/tsc --noEmit -p . (frontend) -> clean.
Tested 5 queries via API:
- 3 STRONG >=0.45 (panel + no hint).
- 2 low-match <0.45 (panel + Low-match (XX%) hint).
- Cold-empty case shows "No related knowledge yet" hint.

### Follow-up
- Add a slight visual diff between strong and low-match panel
  (border colour, badge) so glanceability is even better.
- Persist composerHint in last-known-good state across view-switch
  the same way composerInput is now persisted.

## 2026-07-12 — pipeline UI works end-to-end (PR merged)

### Triggered real capture path
- Created commit `6933625 → 7e7cdb8` on test_loomi_repo branch
  `loomi-pr-trigger-demo-20260712-0555`
- Opened & merged PRs #2 and #3 via `gh`
- Repo URL tracked: kvgkvg/test_loomi_repo.git (mounted to
  /repo inside loomi-core)
- Poller interval: 3s (core/app.py:420)

### Verified
- DB raw_events went 0 -> 2
- /api/runs returns 2 runs, both status "running" with all 6 stages
  success/finalize_skipped_pending_review
- Chroma count went 6 -> 8 (each new asset pre-embedded)
- Recommend API returns new asset top hits:
  task="composer pipeline visualization" -> score=0.485 STRONG

### Bug found and fixed mid-run
core/app.py:145 was hard-coding
  f"Upserted draft vector id=draft:{version_id}"
to mirror the OLD capture pipeline (draft: prefix). Now that
process.py upserts under asset_id directly, the evidence string
would mislead anyone checking the pipeline UI. Replaced with
  f"Upserted Chroma vector id={asset_id}"
reflecting the implemented fact. Restart core container, merge PR #3,
embed log now shows correct vector_id matching what's in Chroma.

### Push workflow quirks (worth noting)
- repo remote changed to https via gh auth token (no SSH for this account)
- Token passed via https://x-access-token:${TOKEN}@github.com/...
- Each "demo" file must be push + PR + merge (gh pr merge --merge --delete-branch)
  because the git poller only moves on main HEAD change

## 2026-07-12 — ghost suggestion now lives above Evidence Stack

### Layout change
Composer (LEFT) is now a pure input + composerHint only.
The PROACTIVE RECOMMENDATION panel moved to the top of the RIGHT
Evidence Stack panel (page.tsx around line 853). It is rendered
unconditionally of whether the user has opened an asset review yet
(so a fresh composer query shows up immediately in the empty
"Asset Onboarding Review" placeholder area).

### Why this UX
- User wanted to see the recommendation while Evidence Stack is
  open, not as a composer overlay that could be hidden behind it.
- Composer stays a clean write surface — user keeps typing freely.
- Switching composer content re-runs recommend useEffect (already
  debounced 300ms, AbortController cancels stale requests), and the
  Evidence Stack-header panel updates in place. No code change needed
  to the recommend logic — it was already independent of
  activeAsset.

### Caveat for the live demo
Frontend container loomi-frontend runs `next start` with a baked
`.next` build. Code changes to frontend require either:
- full rebuild (`docker compose build frontend` then
  `docker compose up -d loomi-frontend`), OR
- switch to `next dev` for hot reload.
Production cache will keep serving the old JS until one of those runs.

## 2026-07-12 — Git Sync and Conflict Resolution for feature/app-demo

### Done
- Checked the status of `feature/app-demo` branch, noting a divergence of 1 commit local and 6 commits remote.
- Ran `git fetch origin` and `git merge origin/feature/app-demo`.
- The merge completed with auto-merging of `frontend/app/page.tsx` and no manual conflicts to resolve.
- Committed the merge locally with `Merge remote-tracking branch 'origin/feature/app-demo' into feature/app-demo`.
- Pushed changes successfully back to remote. Branch is now fully up to date with remote and working tree is clean.
- Added explicit ignore rule for `.worktrees/nextjs-memory-demo` to `.gitignore`.

### Why this pattern
- Followed standard git merge procedure to integrate remote changes before pushing.
- Since auto-merge handled everything cleanly, no manual conflict resolution step was required.
