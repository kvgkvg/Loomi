# Recommend Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `recommend(task_description, top_k)` that returns 3–5 org assets ranked by semantic relevance + trust signals, proving "match by meaning, not keywords."

**Architecture:** A pure scoring function (`recommend/scoring.py`) combines cosine similarity + rationale confidence + usage count into a 0-1 score. An orchestrator (`recommend/engine.py`) does the IO: embed query with all-MiniLM-L6-v2, vector-search Chroma, join relational metadata, call scoring, sort. A temporary `db/client_stub.py` (mirroring Khang's future `db/client.py` API) plus a seed script unblock full local testing before other components ship.

**Tech Stack:** Python 3.13, `sentence-transformers` (all-MiniLM-L6-v2), `chromadb`, `sqlite3` (stdlib), `pytest`.

## Global Constraints

- Embedding model is `sentence-transformers/all-MiniLM-L6-v2`, normalized — NEVER change; must match Ấn's embed step or vectors become incomparable.
- Chroma collection name is `assets`; each vector `id` = `asset_id`; metadata carries at least `asset_id`.
- `recommend()` NEVER raises — any failure or empty input returns `[]`.
- `recommend()` return shape is exactly: `[{asset_id: str, title: str, problem: str, score: float, usage_count: int, owner_name: str}]`, sorted descending by `score`. Do not add/rename keys without team sign-off (task.md §7).
- Score weights: `W_COS=0.7, W_CONF=0.2, W_USE=0.1`, kept as module constants.
- DB access goes through `db/client_stub.py` now; swap import to `db.client` (Khang's) at integration — same function names `get_pg_connection()`, `get_vector_collection()`.
- No cross-encoder, no caching, no async (YAGNI / ponytail — keep MVP simple).

---

### Task 1: Project env + package skeleton

**Files:**
- Create: `requirements.txt`
- Create: `recommend/__init__.py` (empty)
- Create: `db/__init__.py` (empty)
- Create: `tests/__init__.py` (empty)

**Interfaces:**
- Consumes: nothing.
- Produces: installable dependency set; importable `recommend` and `db` packages.

- [ ] **Step 1: Write requirements.txt**

```
sentence-transformers>=2.2
chromadb>=0.5
pytest>=8.0
```

- [ ] **Step 2: Create the empty package markers**

Create `recommend/__init__.py`, `db/__init__.py`, `tests/__init__.py` — all empty files.

- [ ] **Step 3: Install dependencies**

Run: `python3 -m pip install -r requirements.txt`
Expected: installs succeed (sentence-transformers pulls torch — large download, allow time). No error at exit.

- [ ] **Step 4: Verify imports work**

Run: `python3 -c "import chromadb, sentence_transformers; print('ok')"`
Expected: prints `ok`

- [ ] **Step 5: Commit**

```bash
git add requirements.txt recommend/__init__.py db/__init__.py tests/__init__.py
git commit -m "chore: recommend engine env + package skeleton"
```

---

### Task 2: Pure scoring function

**Files:**
- Create: `recommend/scoring.py`
- Test: `tests/test_scoring.py`

**Interfaces:**
- Consumes: nothing (pure, stdlib `math` only).
- Produces: `compute(cosine: float, confidence: str, usage_count: int) -> float` and module constants `W_COS`, `W_CONF`, `W_USE`. Called by `engine.py` in Task 5.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_scoring.py
import math
from recommend.scoring import compute, W_COS, W_CONF, W_USE


def test_weights_sum_to_one():
    assert W_COS + W_CONF + W_USE == 1.0


def test_perfect_match_user_provided_high_usage_near_one():
    # cosine=1, user_provided conf=1.0, usage saturated -> 0.7+0.2+0.1
    assert compute(1.0, "user_provided", 20) == 1.0


def test_user_provided_beats_auto_all_else_equal():
    assert compute(0.5, "user_provided", 0) > compute(0.5, "auto", 0)


def test_monotonic_in_cosine():
    assert compute(0.9, "auto", 0) > compute(0.4, "auto", 0)


def test_usage_boost_saturates_at_20():
    # beyond 20 usages the boost is clamped, so score stops rising from usage
    assert compute(0.5, "auto", 20) == compute(0.5, "auto", 100)


def test_unknown_confidence_treated_as_auto():
    assert compute(0.5, "", 0) == compute(0.5, "auto", 0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_scoring.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'recommend.scoring'`

- [ ] **Step 3: Write minimal implementation**

```python
# recommend/scoring.py
import math

W_COS, W_CONF, W_USE = 0.7, 0.2, 0.1
_USAGE_SATURATION = 20


def compute(cosine: float, confidence: str, usage_count: int) -> float:
    """Combine relevance + trust signals into a 0-1 score.

    cosine: similarity 0-1 (1 - chroma_distance).
    confidence: 'user_provided' | 'auto' (anything else treated as 'auto').
    usage_count: times the asset has been reused; boost saturates at 20.
    """
    conf_weight = 1.0 if confidence == "user_provided" else 0.6
    usage_boost = min(
        math.log1p(max(usage_count, 0)) / math.log1p(_USAGE_SATURATION), 1.0
    )
    return W_COS * cosine + W_CONF * conf_weight + W_USE * usage_boost
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_scoring.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add recommend/scoring.py tests/test_scoring.py
git commit -m "feat: pure weighted scoring function for recommend engine"
```

---

### Task 3: DB stub — SQLite + Chroma clients

**Files:**
- Create: `db/client_stub.py`
- Test: `tests/test_client_stub.py`

**Interfaces:**
- Consumes: `chromadb`, stdlib `sqlite3`.
- Produces:
  - `get_pg_connection() -> sqlite3.Connection` — a SQLite connection with `row_factory = sqlite3.Row`, schema created on first call (subset of task.md §3: `users`, `assets`, `asset_versions`, `rationale`).
  - `get_vector_collection()` — a persistent Chroma collection named `assets` (cosine space).
  - `DB_PATH`, `CHROMA_PATH` module constants (under `.data/` so they are gitignored).
- Mirrors Khang's future `db/client.py` names exactly so Task 5 import can be swapped 1:1.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_client_stub.py
import sqlite3
from db import client_stub


def test_pg_connection_has_expected_tables(tmp_path, monkeypatch):
    monkeypatch.setattr(client_stub, "DB_PATH", str(tmp_path / "t.db"))
    conn = client_stub.get_pg_connection()
    names = {
        r["name"]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    assert {"users", "assets", "asset_versions", "rationale"} <= names


def test_pg_connection_row_factory_is_row(tmp_path, monkeypatch):
    monkeypatch.setattr(client_stub, "DB_PATH", str(tmp_path / "t.db"))
    conn = client_stub.get_pg_connection()
    assert conn.row_factory is sqlite3.Row


def test_vector_collection_named_assets(tmp_path, monkeypatch):
    monkeypatch.setattr(client_stub, "CHROMA_PATH", str(tmp_path / "chroma"))
    col = client_stub.get_vector_collection()
    assert col.name == "assets"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_client_stub.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'db.client_stub'`

- [ ] **Step 3: Write minimal implementation**

```python
# db/client_stub.py
"""TEMP local stand-in for Khang's db/client.py.

Same public function names (get_pg_connection, get_vector_collection) so
engine.py only needs its import line swapped at integration. Uses SQLite +
a persistent local Chroma so the recommend engine is fully testable now.
"""
import os
import sqlite3

import chromadb

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".data")
DB_PATH = os.path.join(_DATA_DIR, "stub.db")
CHROMA_PATH = os.path.join(_DATA_DIR, "chroma")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  email TEXT UNIQUE,
  team TEXT
);
CREATE TABLE IF NOT EXISTS assets (
  id TEXT PRIMARY KEY,
  type TEXT NOT NULL,
  title TEXT NOT NULL,
  source_tool TEXT NOT NULL,
  owner_id TEXT REFERENCES users(id),
  current_version_id TEXT,
  usage_count INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS asset_versions (
  id TEXT PRIMARY KEY,
  asset_id TEXT REFERENCES assets(id),
  version_number INTEGER NOT NULL,
  content TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS rationale (
  id TEXT PRIMARY KEY,
  version_id TEXT UNIQUE REFERENCES asset_versions(id),
  problem TEXT,
  confidence TEXT
);
"""


def get_pg_connection() -> sqlite3.Connection:
    os.makedirs(_DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    conn.commit()
    return conn


def get_vector_collection():
    os.makedirs(CHROMA_PATH, exist_ok=True)
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    return client.get_or_create_collection(
        name="assets", metadata={"hnsw:space": "cosine"}
    )
```

- [ ] **Step 4: Add `.data/` to gitignore**

Create or append to `.gitignore`:

```
.data/
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_client_stub.py -v`
Expected: 3 passed

- [ ] **Step 6: Commit**

```bash
git add db/client_stub.py tests/test_client_stub.py .gitignore
git commit -m "feat: temp SQLite+Chroma db stub mirroring db/client.py API"
```

---

### Task 4: Seed script

**Files:**
- Create: `recommend/embedding.py`
- Create: `scripts/seed_recommend.py`
- Test: `tests/test_seed.py`

**Interfaces:**
- Consumes: `db.client_stub.get_pg_connection`, `db.client_stub.get_vector_collection`.
- Produces:
  - `recommend/embedding.py`: `embed(texts: list[str]) -> list[list[float]]` and `MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"`. Lazy-loads and caches one model instance. Used by seed script (Task 4) and engine (Task 5).
  - `scripts/seed_recommend.py`: `seed() -> int` — inserts users + 6 assets (each with one version + rationale) into SQLite AND upserts their embeddings (`content + " " + problem`) into the `assets` Chroma collection with `id=asset_id, metadata={asset_id}`. Returns number of assets seeded. Idempotent (clears its own rows first). One asset is An's support-ticket chatbot, worded to NOT share keywords with "lead-classification agent".

- [ ] **Step 1: Write the failing test**

```python
# tests/test_seed.py
import importlib

from db import client_stub


def test_seed_populates_sql_and_vectors(tmp_path, monkeypatch):
    monkeypatch.setattr(client_stub, "DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setattr(client_stub, "CHROMA_PATH", str(tmp_path / "chroma"))
    seed_mod = importlib.import_module("scripts.seed_recommend")

    n = seed_mod.seed()
    assert n >= 5

    conn = client_stub.get_pg_connection()
    rows = conn.execute("SELECT COUNT(*) AS c FROM assets").fetchone()["c"]
    assert rows == n

    col = client_stub.get_vector_collection()
    assert col.count() == n
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_seed.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.seed_recommend'`

- [ ] **Step 3: Write the embedding helper**

```python
# recommend/embedding.py
"""Single source of truth for the embedding model. MUST match Ấn's embed step."""
from functools import lru_cache

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


@lru_cache(maxsize=1)
def _model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(MODEL_NAME)


def embed(texts: list[str]) -> list[list[float]]:
    vecs = _model().encode(texts, normalize_embeddings=True)
    return [v.tolist() for v in vecs]
```

- [ ] **Step 4: Write the seed script**

```python
# scripts/seed_recommend.py
"""Seed 6 sample assets (SQL rows + Chroma vectors) for local recommend tests.

Includes An's support-ticket chatbot, deliberately worded WITHOUT the words
'lead', 'classification', or 'sales' so semantic (not keyword) match is proven.
Idempotent: clears its own rows/vectors first.
"""
from db import client_stub
from recommend.embedding import embed

USERS = [
    ("u-an", "An", "an@co.com", "support"),
    ("u-mai", "Mai", "mai@co.com", "marketing"),
    ("u-tan", "Tan", "tan@co.com", "eng"),
]

# (asset_id, type, title, source_tool, owner_id, usage_count,
#  version content, rationale problem, confidence)
ASSETS = [
    ("a-support-bot", "prompt",
     "Support ticket triage assistant", "git", "u-an", 12,
     "Prompt that reads an incoming customer support ticket and sorts it into "
     "the right category so the team can route it to the correct queue.",
     "Support agents were overwhelmed manually sorting inbound tickets; needed "
     "automatic categorization of free-text messages into fixed buckets.",
     "user_provided"),
    ("a-email-writer", "prompt",
     "Marketing email drafter", "git", "u-mai", 3,
     "Generates promotional email copy from a product brief.",
     "Marketing spent hours writing repetitive campaign emails by hand.",
     "auto"),
    ("a-meeting-notes", "prompt",
     "Meeting notes summarizer", "git", "u-tan", 7,
     "Condenses a raw meeting transcript into action items.",
     "Long meeting transcripts were never read; key decisions got lost.",
     "auto"),
    ("a-code-review", "agent_config",
     "PR review bot", "git", "u-tan", 5,
     "Agent that comments on pull requests flagging style and bug risks.",
     "Human reviewers missed repetitive style issues on every PR.",
     "user_provided"),
    ("a-invoice-parse", "workflow",
     "Invoice field extractor", "n8n", "u-mai", 2,
     "Workflow extracting totals and dates from uploaded invoice PDFs.",
     "Finance manually retyped numbers off scanned invoices.",
     "auto"),
    ("a-faq-bot", "prompt",
     "Internal FAQ answerer", "git", "u-an", 9,
     "Answers employee questions using the internal handbook.",
     "New hires kept asking HR the same policy questions.",
     "auto"),
]


def seed() -> int:
    conn = client_stub.get_pg_connection()
    cur = conn.cursor()
    # idempotent reset of the tables this script owns
    for tbl in ("rationale", "asset_versions", "assets", "users"):
        cur.execute(f"DELETE FROM {tbl}")

    for uid, name, email, team in USERS:
        cur.execute(
            "INSERT INTO users(id, name, email, team) VALUES (?,?,?,?)",
            (uid, name, email, team),
        )

    docs, ids, metas = [], [], []
    for (aid, atype, title, tool, owner, usage,
         content, problem, conf) in ASSETS:
        vid = f"v-{aid}"
        cur.execute(
            "INSERT INTO assets(id,type,title,source_tool,owner_id,"
            "current_version_id,usage_count) VALUES (?,?,?,?,?,?,?)",
            (aid, atype, title, tool, owner, vid, usage),
        )
        cur.execute(
            "INSERT INTO asset_versions(id,asset_id,version_number,content) "
            "VALUES (?,?,?,?)",
            (vid, aid, 1, content),
        )
        cur.execute(
            "INSERT INTO rationale(id,version_id,problem,confidence) "
            "VALUES (?,?,?,?)",
            (f"r-{aid}", vid, problem, conf),
        )
        docs.append(f"{content} {problem}")
        ids.append(aid)
        metas.append({"asset_id": aid})

    conn.commit()

    col = client_stub.get_vector_collection()
    existing = col.get()["ids"]
    if existing:
        col.delete(ids=existing)
    col.add(ids=ids, embeddings=embed(docs), metadatas=metas)
    return len(ASSETS)


if __name__ == "__main__":
    n = seed()
    print(f"seeded {n} assets")
```

- [ ] **Step 5: Create `scripts/__init__.py`**

Create empty file `scripts/__init__.py` so `scripts.seed_recommend` is importable.

- [ ] **Step 6: Run test to verify it passes**

Run: `python3 -m pytest tests/test_seed.py -v`
Expected: 1 passed (first run downloads the model — allow time)

- [ ] **Step 7: Commit**

```bash
git add recommend/embedding.py scripts/seed_recommend.py scripts/__init__.py tests/test_seed.py
git commit -m "feat: embedding helper + idempotent seed script (6 sample assets)"
```

---

### Task 5: Recommend engine orchestration

**Files:**
- Create: `recommend/engine.py`
- Test: `tests/test_engine.py`

**Interfaces:**
- Consumes:
  - `recommend.embedding.embed`
  - `recommend.scoring.compute`
  - `db.client_stub.get_pg_connection`, `db.client_stub.get_vector_collection`
- Produces: `recommend(task_description: str, top_k: int = 5) -> list[dict]` with the exact contract shape from Global Constraints.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_engine.py
import importlib

from db import client_stub


def _seed(tmp_path, monkeypatch):
    monkeypatch.setattr(client_stub, "DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setattr(client_stub, "CHROMA_PATH", str(tmp_path / "chroma"))
    importlib.import_module("scripts.seed_recommend").seed()


def test_empty_query_returns_empty_list(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    from recommend.engine import recommend
    assert recommend("") == []
    assert recommend("   ") == []


def test_semantic_match_ranks_support_bot_top(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    from recommend.engine import recommend
    res = recommend("build a lead-classification agent for sales", top_k=3)
    assert res  # non-empty
    assert res[0]["asset_id"] == "a-support-bot"


def test_output_shape_and_sorted(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    from recommend.engine import recommend
    res = recommend("categorize incoming messages", top_k=5)
    assert len(res) <= 5
    keys = {"asset_id", "title", "problem", "score", "usage_count", "owner_name"}
    for r in res:
        assert keys == set(r)
        assert isinstance(r["score"], float)
    scores = [r["score"] for r in res]
    assert scores == sorted(scores, reverse=True)


def test_owner_name_resolved(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    from recommend.engine import recommend
    res = recommend("triage support tickets", top_k=1)
    assert res[0]["owner_name"] == "An"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_engine.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'recommend.engine'`

- [ ] **Step 3: Write minimal implementation**

```python
# recommend/engine.py
"""Task -> ranked related assets. Public entrypoint: recommend()."""
from db import client_stub
from recommend.embedding import embed
from recommend.scoring import compute

_OVERFETCH = 20


def recommend(task_description: str, top_k: int = 5) -> list[dict]:
    """See spec: returns list of asset dicts sorted desc by score. Never raises."""
    try:
        if not task_description or not task_description.strip():
            return []

        col = client_stub.get_vector_collection()
        if col.count() == 0:
            return []

        q = embed([task_description])[0]
        hits = col.query(query_embeddings=[q], n_results=_OVERFETCH)
        ids = hits["ids"][0]
        dists = hits["distances"][0]
        if not ids:
            return []

        conn = client_stub.get_pg_connection()
        placeholders = ",".join("?" for _ in ids)
        rows = conn.execute(
            f"""
            SELECT a.id AS asset_id, a.title AS title, a.usage_count AS usage_count,
                   u.name AS owner_name, r.problem AS problem,
                   r.confidence AS confidence
            FROM assets a
            LEFT JOIN users u ON u.id = a.owner_id
            LEFT JOIN asset_versions v ON v.id = a.current_version_id
            LEFT JOIN rationale r ON r.version_id = v.id
            WHERE a.id IN ({placeholders})
            """,
            ids,
        ).fetchall()
        meta = {row["asset_id"]: row for row in rows}

        results = []
        for aid, dist in zip(ids, dists):
            row = meta.get(aid)
            if row is None:
                continue
            cosine = 1.0 - float(dist)
            score = compute(
                cosine,
                row["confidence"] or "auto",
                row["usage_count"] or 0,
            )
            results.append(
                {
                    "asset_id": aid,
                    "title": row["title"],
                    "problem": (row["problem"] or "")[:200],
                    "score": round(score, 4),
                    "usage_count": row["usage_count"] or 0,
                    "owner_name": row["owner_name"] or "",
                }
            )

        results.sort(key=lambda r: r["score"], reverse=True)
        return results[:top_k]
    except Exception:
        return []
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_engine.py -v`
Expected: 4 passed

- [ ] **Step 5: Run the full suite**

Run: `python3 -m pytest -v`
Expected: all tests pass (scoring + stub + seed + engine)

- [ ] **Step 6: Commit**

```bash
git add recommend/engine.py tests/test_engine.py
git commit -m "feat: recommend engine orchestration (embed->search->join->score)"
```

---

### Task 6: CLI smoke entrypoint + memory log

**Files:**
- Create: `recommend/__main__.py`
- Create: `memory/recommend-hong.md`

**Interfaces:**
- Consumes: `recommend.engine.recommend`, `scripts.seed_recommend.seed`.
- Produces: `python3 -m recommend "<task>"` prints ranked results — the demo terminal moment from task.md §7. No new importable API.

- [ ] **Step 1: Write the CLI entrypoint**

```python
# recommend/__main__.py
"""Demo entrypoint:  python3 -m recommend "build a lead-classification agent"
Runs seed if the collection is empty, then prints ranked recommendations.
"""
import sys

from db import client_stub
from recommend.engine import recommend
from scripts.seed_recommend import seed


def main() -> None:
    task = " ".join(sys.argv[1:]) or "build a lead-classification agent for sales"
    if client_stub.get_vector_collection().count() == 0:
        seed()
    results = recommend(task)
    print(f"\nTask: {task}\n")
    if not results:
        print("(no related assets found)")
        return
    for i, r in enumerate(results, 1):
        print(f"{i}. [{r['score']:.3f}] {r['title']}  — {r['owner_name']}")
        print(f"     problem: {r['problem']}")
        print(f"     used {r['usage_count']}x  (id={r['asset_id']})")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the smoke entrypoint**

Run: `python3 -m recommend "build a lead-classification agent for sales"`
Expected: prints a numbered list; item 1 is "Support ticket triage assistant — An".

- [ ] **Step 3: Write the memory log**

```markdown
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
```

- [ ] **Step 4: Commit**

```bash
git add recommend/__main__.py memory/recommend-hong.md
git commit -m "feat: recommend CLI smoke entrypoint + memory log"
```
