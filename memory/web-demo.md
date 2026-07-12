
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
