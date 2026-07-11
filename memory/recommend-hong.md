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
