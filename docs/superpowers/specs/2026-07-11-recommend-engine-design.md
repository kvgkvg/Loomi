# Recommend Engine — Design Spec (Hồng, Track P5)

Date: 2026-07-11
Owner: Hồng
Component: `recommend/` (task.md §7)

## Goal

Take a free-text task description, return 3–5 organizational assets ranked by
semantic relevance + trust signals — proving "match by meaning, not keywords".

Demo proof: seed An's support-ticket chatbot asset, call
`recommend("build a lead-classification agent for sales")`, An's asset ranks top
despite zero shared keywords.

## Public contract (do not change without team sign-off)

```python
# recommend/engine.py
def recommend(task_description: str, top_k: int = 5) -> list[dict]:
    """
    Output: [
      {
        "asset_id": str,       # UUID
        "title": str,
        "problem": str,        # rationale.problem, shortened
        "score": float,        # 0-1, after weighted rerank
        "usage_count": int,
        "owner_name": str
      },
      ...
    ]  # sorted descending by score
    """
```

## Architecture

Two focused units + a temporary DB stub:

```
recommend/engine.py   # orchestration: embed → retrieve → join → score → sort
recommend/scoring.py  # pure fn: combine signals into 0-1 score (unit-testable)
db/client_stub.py     # TEMP local stand-in for Khang's db/client.py (same signature)
scripts/seed_recommend.py  # 5-8 fake assets into stub DB + Chroma for local test
```

Boundaries:
- `scoring.py` is pure (numbers in → number out). No DB, no model. Fully unit-testable.
- `engine.py` owns all IO (embedding, Chroma, SQL). Imports scoring.
- `db/client_stub.py` mirrors Khang's exact API: `get_pg_connection()`,
  `get_vector_collection()`. At integration, swap import `db.client_stub` →
  `db.client`, zero other changes. Kept separate to avoid clobbering Khang's file.

## Data flow inside `recommend()`

```
task_description
  → embed(all-MiniLM-L6-v2, normalized)      # SAME model as Ấn's embed step
  → chroma.query(query_emb, n_results=20)    # over-fetch for rerank headroom
  → get [(asset_id, distance)]
  → SQL: join assets + users + rationale (+ usage_count from assets)
         over the returned asset_ids
  → per candidate: scoring.compute(cosine, confidence, usage_count)
  → sort desc by score
  → slice top_k
  → shape to contract, return
```

Empty query OR no Chroma hits → return `[]` (never raise). UI shows "nothing found".

## Scoring (`recommend/scoring.py`)

```python
W_COS, W_CONF, W_USE = 0.7, 0.2, 0.1   # module constants — tune live at demo

def compute(cosine: float, confidence: str, usage_count: int) -> float:
    conf_weight = 1.0 if confidence == "user_provided" else 0.6
    usage_boost = min(math.log1p(usage_count) / math.log1p(20), 1.0)
    return W_COS * cosine + W_CONF * conf_weight + W_USE * usage_boost
```

- `cosine = 1 - chroma_distance` (Chroma cosine space → similarity 0-1).
- Weights sum to 1 → score stays in 0-1.
- `confidence` from `rationale.confidence` ('auto' | 'user_provided').
- Missing rationale (asset with no rationale row) → treat confidence='auto',
  problem="" — still rankable on cosine alone.

## Cross-team contract with Ấn (Chroma) — must agree verbatim

- Collection name: `assets`
- Embedding model: `sentence-transformers/all-MiniLM-L6-v2`, normalized
- Vector `id` = `asset_id`
- Vector metadata carries at minimum `asset_id`
- Ấn embeds `content + rationale.problem` (per AGENTS.md line 34);
  Hồng embeds `task_description` alone. Same model both sides → vectors comparable.

## Error handling

- No exceptions leak from `recommend()`. Any failure → log + return `[]`.
- Embedding model load is once at import/first-call (cache the model object).

## Testing

1. `tests/test_scoring.py` — pure unit tests on `compute()`:
   monotonic in cosine, user_provided > auto, usage_boost saturates at 20.
2. `scripts/seed_recommend.py` — seed 5-8 assets incl. An's support-chatbot
   (title/problem worded differently from the query on purpose).
3. Integration smoke: `recommend("build a lead-classification agent for sales")`
   → An's asset in top results, score printed, contract shape verified.

## Out of scope (YAGNI, MVP)

- No cross-encoder reranker (ponytail: keep simple; weighted signals enough).
- No caching layer, no async, no pagination.
- No governance/RBAC filtering of results.

## Integration steps (later, with team)

1. Khang ships real `db/client.py` → swap import in `engine.py`.
2. Ấn confirms Chroma collection name + embed input match this spec.
3. Re-run integration smoke against real captured data (not seed).

## Memory logging (AGENTS.md rule)

After each sub-task, append to `memory/recommend-hong.md`: what done, decisions +
why, bugs+fixes, next step. Never overwrite.
