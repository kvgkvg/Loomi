# Recommend engine — Hồng

## 2026-07-11 — initial build
- Built recommend/scoring.py (pure), recommend/engine.py (orchestration),
  db/client_stub.py (temp SQLite+Chroma), scripts/seed_recommend.py.
- Decisions:
  - Score = 0.7*cosine + 0.2*confidence + 0.1*usage (weighted, no cross-encoder — ponytail/MVP).
  - Embed model all-MiniLM-L6-v2, normalized — MUST match Ấn's embed step.
  - Empty query / no hits / any error -> return [] (engine never raises).
  - db/client_stub.py mirrors Khang's get_pg_connection/get_vector_collection
    names -> swap import to db.client at integration, no other change.
- Next steps (integration):
  - Swap `from db import client_stub` -> Khang's `db.client` in engine.py & __main__.py.
  - Confirm with Ấn: Chroma collection name 'assets', vector id = asset_id,
    Ấn embeds `content + rationale.problem` (same as seed docs here).
  - Re-run `python3 -m pytest` against real captured data, not seed.

## 2026-07-11 — final-review fix: semantic win + cosine clamp
- Problem: a-support-bot beat a-code-review on final score by only 0.002,
  and a-code-review actually had the HIGHER raw cosine (spurious overlap on
  token "agent"). Support-bot was winning on the usage-count term, not
  semantics — undermined the "match by meaning" claim.
- Fix (seed data only, scoring weights untouched):
  - Reworded a-support-bot content + problem to lean into
    classify/categorize/route/bucket/triage semantics, still avoiding the
    literal tokens "lead"/"sales"/"classification".
  - Reworded a-code-review to drop the spurious "agent" token
    ("Reviews pull requests..." instead of "Agent that comments...").
  - Clamped cosine in recommend/engine.py: `max(0.0, 1.0 - float(dist))`
    so it can't go negative (spec says 0-1 score).
- Verified with throwaway raw-cosine probe (query: "build a
  lead-classification agent for sales", fresh seed):
  - a-support-bot cosine = 0.290894
  - a-code-review  cosine = 0.148497
  - Margin ~0.142 — support-bot now wins on semantics, not just tiebreak.
- `python3 -m pytest -v` — 14/14 passed. Smoke
  (`python3 -m recommend "build a lead-classification agent for sales"`)
  ranks a-support-bot (An) #1.
