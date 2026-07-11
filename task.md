# Organizational AI Memory — Context & Work Assignment (Team of 4)

Principle: everyone codes against the **input/output contract** defined below, without waiting for others to finish first. Use mock/seed data to test independently before integration. Read the Context section before jumping into your own part — understand *why*, not just *what*.

---

## 1. The problem (Track P5 — Founder Mode, GenAI Fund Build Week)

**Challenge statement:** Employees create effective prompts, useful workflows, and well-configured agents in their daily work — but when they change roles or leave, that knowledge disappears with them. How do we turn individual AI knowledge into permanent organizational capability?

**5 pain points identified:**
1. **Tool silos** — knowledge is scattered across personal Claude Projects, individual n8n accounts, local Cursor configs — nobody (not even leadership) knows they exist to be reused, even if the end result has been "deployed" and is visible.
2. **Missing "why it worked" context** — only the final prompt/workflow is saved, losing the reasoning, failed attempts, and constraints that shaped the final version.
3. **No timely reuse signal** — the person who needs the knowledge doesn't know to look for it, because they don't think to search while busy with something else.
4. **No governance/version control process** — nobody reviews or keeps a change history for prompts/agents the way code gets reviewed.
5. **No one owns standardization** — no role or incentive to maintain a shared knowledge base.

**Scope decision:** The team focuses effort on pain points 1+3 (core loop — discovery & timely recommendation, ~60%), pain point 2 (differentiator — "why" context, ~25%), pain points 4+5 are light UX touches only, not built as standalone features (~15%).

### Core demo scenario (every design decision traces back to this)
> An (support team) builds a support-ticket chatbot; the prompt and lessons learned live in his personal Claude Project. Three months later, Hồng (sales-ops) is assigned a similar task (a lead-classification agent) but has no idea An already solved something close — she starts from zero, spends two weeks, and repeats the same mistakes An already fixed. **System goal: Hồng should be proactively notified "An already built something close to this" the moment she starts, without having to search for it herself.**

### Comparison with adjacent solutions (in case judges ask)
- **claude-mem**: solves the "time axis" (one agent recalling its own past sessions), not the "social axis" (one person discovering another person's knowledge). Complementary, not competing.
- **CodeGraph Store (MOSAIC)**: solves technical relationships *within a single codebase* (function calls function); prompts/agents are just one of ~13 node types. Our product solves cross-team human knowledge, not limited to code.

---

## 2. Overall architecture

```
Data sources (3 types)
  Git & IDE hooks | Chat & agent logs | Workflow tools
        │
        ▼
  Adapter (one adapter per source, translates into a canonical event)
        │
        ▼
  Capture pipeline (Diff & version → Rationale extraction LLM → Embedding)
        │
        ▼
  Memory store (Postgres/SQLite: assets, rationale... + Chroma: vector)
        │
        ├──────────────┐
        ▼              ▼
  Recommend engine   Onboarding assistant
  (task → asset)     (asset → explanation for new hires)
        │              │
        └──────┬───────┘
               ▼
        Delivery layer (demo UI)
```

**Why split into these layers:** Adapters are separated so adding a new source (Slack, Notion...) later doesn't require touching the capture pipeline. The capture pipeline is split into 3 sequential steps because each has different characteristics (diff is fast, LLM call is slow, embedding depends on both prior steps). The memory store is split into two storage systems because vector DB is optimized for semantic search while relational data (owner, version, tags) fits relational storage better. Recommend engine and onboarding assistant are separate because they answer two different questions ("what's related" vs "how does this work") even though both read from the same memory store.

---

## 3. Full database schema (Khang builds exactly this)

```sql
-- Staging table: receives raw adapter output before the capture pipeline processes it
CREATE TABLE raw_events (
  id UUID PRIMARY KEY,
  source_tool TEXT NOT NULL,        -- 'git' | 'claude_chat' | 'n8n'
  title TEXT,
  content TEXT NOT NULL,
  raw_signal TEXT,                   -- original data (diff, transcript...) for the LLM to read
  received_at TIMESTAMP DEFAULT now(),
  processed BOOLEAN DEFAULT FALSE,
  processed_asset_version_id UUID    -- points to the resulting record once processed
);

CREATE TABLE users (
  id UUID PRIMARY KEY,
  name TEXT NOT NULL,
  email TEXT UNIQUE,
  team TEXT
);

CREATE TABLE assets (
  id UUID PRIMARY KEY,
  type TEXT NOT NULL CHECK (type IN ('prompt', 'workflow', 'agent_config')),
  title TEXT NOT NULL,
  source_tool TEXT NOT NULL,
  owner_id UUID REFERENCES users(id),
  previous_asset_id UUID REFERENCES assets(id),  -- lineage when an asset is split/renamed
  current_version_id UUID,
  usage_count INT DEFAULT 0,
  created_at TIMESTAMP DEFAULT now(),
  updated_at TIMESTAMP DEFAULT now()
);

CREATE TABLE asset_versions (
  id UUID PRIMARY KEY,
  asset_id UUID REFERENCES assets(id) ON DELETE CASCADE,
  raw_event_id UUID REFERENCES raw_events(id),   -- traceback to the original raw source
  version_number INT NOT NULL,
  content TEXT NOT NULL,
  diff_summary TEXT,
  editor_id UUID REFERENCES users(id),
  created_at TIMESTAMP DEFAULT now(),
  UNIQUE(asset_id, version_number)
);

CREATE TABLE rationale (
  id UUID PRIMARY KEY,
  version_id UUID UNIQUE REFERENCES asset_versions(id) ON DELETE CASCADE,
  problem TEXT,
  failed_attempts JSONB,
  constraints JSONB,
  confidence TEXT CHECK (confidence IN ('auto', 'user_provided'))
);

-- Multiple sources can confirm one rationale, each with its own confidence (not required for MVP)
CREATE TABLE rationale_evidence (
  id UUID PRIMARY KEY,
  rationale_id UUID REFERENCES rationale(id) ON DELETE CASCADE,
  evidence_type TEXT CHECK (evidence_type IN ('git_diff', 'chat_log', 'user_manual')),
  confidence NUMERIC(3,2) CHECK (confidence BETWEEN 0 AND 1)
);

CREATE TABLE tags (
  id UUID PRIMARY KEY,
  name TEXT UNIQUE NOT NULL
);

CREATE TABLE asset_tags (
  asset_id UUID REFERENCES assets(id) ON DELETE CASCADE,
  tag_id UUID REFERENCES tags(id) ON DELETE CASCADE,
  PRIMARY KEY (asset_id, tag_id)
);

CREATE TABLE asset_usage (
  id UUID PRIMARY KEY,
  asset_id UUID REFERENCES assets(id) ON DELETE CASCADE,
  user_id UUID REFERENCES users(id),
  task_description TEXT,
  used_at TIMESTAMP DEFAULT now()
);

-- Typed relations between assets — answers "what breaks if I change this" (not required for MVP)
CREATE TABLE asset_relations (
  id UUID PRIMARY KEY,
  source_asset_id UUID REFERENCES assets(id) ON DELETE CASCADE,
  target_asset_id UUID REFERENCES assets(id) ON DELETE CASCADE,
  relation_type TEXT CHECK (relation_type IN ('USES_PROMPT', 'CALLS_AGENT', 'PART_OF_WORKFLOW')),
  CHECK (source_asset_id <> target_asset_id)
);
```

**Priority if time is short:** `raw_events`, `users`, `assets`, `asset_versions`, `rationale`, `asset_usage`, `tags`/`asset_tags` are required. `rationale_evidence` and `asset_relations` can be dropped if needed — just mention in the pitch that "the architecture is designed to extend."

---

## 4. Dependency order (read before starting)

```
Khang (DB setup)  ──── blocks everyone, do this first (first 1-2 hours)
       │
       ├──> Ấn (Adapter + Capture pipeline)
       │
       ├──> Hồng (Recommend engine)  ──── can use seed data, doesn't need to wait for Ấn
       │
       └──> Trí (Onboarding assistant + Delivery UI) ──── can use seed data, doesn't need to wait for Ấn
```

**Important:** Hồng and Trí **don't need to wait** for Ấn to finish the capture pipeline — as long as Khang inserts 5-10 sample rows into the DB (seed data), Hồng and Trí can code and test in parallel from the start.

---

## 5. Khang — Memory store (DB setup)

### 🎯 Final goal
Anyone on the team can run `from db.client import get_pg_connection` and connect immediately — no errors, no need to ask about config. Opening the DB in any tool (TablePlus, psql, DB Browser) shows 5-10 reasonable sample rows already in the `assets` table.

### Tasks
1. Stand up Postgres (or SQLite for speed) + Chroma (vector DB) running locally.
2. Run the finalized DDL (9 tables: `raw_events`, `users`, `assets`, `asset_versions`, `rationale`, `rationale_evidence`, `tags`, `asset_tags`, `asset_usage`, `asset_relations`).
3. Write a **seed script** — insert 5-10 sample assets (with versions, rationale) so Ấn/Hồng/Trí can test in parallel right away.
4. Provide a connection string / shared client helper for the whole team (one file: `db/client.py`).

### Input
- The finalized DDL (SQL schema) above.

### Output — what the whole team depends on
```python
# db/client.py — everyone imports this file, no one connects to the DB independently
from db.client import get_pg_connection, get_vector_collection

conn = get_pg_connection()          # returns a Postgres/SQLite connection
collection = get_vector_collection() # returns a Chroma collection object
```
- Connection string (written to `.env`, shared with the team via Slack/notes).
- 5-10 rows of seed data in `assets`/`asset_versions`/`rationale` — so Hồng and Trí have test data immediately.

### Internal deadline
Done within the first 1-2 hours — everyone else is waiting on `db/client.py` to start coding.

---

## 6. Ấn — Adapter (Git) + Capture pipeline

### 🎯 Final goal
In front of the whole team, commit a real prompt change to Git → wait a few seconds → open the DB, see a new `assets` row appear automatically, with a `rationale.problem` written by the LLM that actually makes sense (not fake), and that asset is findable via vector search. This is the most important "magic moment" of the demo.

### Tasks
Own both blocks end-to-end (not split across people, due to tight sequential dependency):
1. Adapter that reads Git commits (webhook or `git log` polling).
2. Diff & version → write to `assets` + `asset_versions`.
3. Rationale extraction (LLM call) → write to `rationale`.
4. Embedding → write to Chroma.

### Input
- A real Git repo (use the hackathon project's own repo for an authentic demo).
- `db/client.py` from Khang.

### Output — specific files/functions
```python
# adapters/git_adapter.py
def capture_commit(commit_sha: str) -> dict:
    """
    Input: commit_sha (string)
    Output: {
      "raw_event_id": UUID,
      "source_tool": "git",
      "title": str,
      "content": str,       # the changed file/prompt content
      "raw_signal": str     # diff + commit message
    }
    """
```
```python
# capture_pipeline/process.py
def process_raw_event(raw_event_id: str) -> dict:
    """
    Input: raw_event_id (string, points to a row in the raw_events table)
    Output: {
      "asset_id": UUID,
      "version_id": UUID,
      "rationale": {
        "problem": str,
        "failed_attempts": list[str],
        "constraints": list[str],
        "confidence": "auto" | "user_provided"
      },
      "embedded": bool
    }
    """
```

### Notes
- If the LLM rationale step fails, set `raw_events.processed = false` — don't raise an exception that kills the pipeline; retry later.
- Test independently by creating a few fake commits in a test repo before wiring it into the real demo.

---

## 7. Hồng — Recommend engine

### 🎯 Final goal
Type any sentence like "I need to build a lead-classification agent for sales" into `recommend()`, and the terminal immediately prints 3-5 related assets with scores — even when the phrasing is completely different from the original asset (test by rephrasing, not copying verbatim). This proves "matching by meaning, not keywords."

### Tasks
Take a new task description → return a ranked list of related assets, scored by relevance + confidence.

### Input
```python
# recommend/engine.py
def recommend(task_description: str, top_k: int = 5) -> list[dict]:
    """
    Input: task_description (string) — description of the task the user is working on
           top_k (int) — max number of suggestions
    """
```

### Output
```python
    """
    Output: [
      {
        "asset_id": UUID,
        "title": str,
        "problem": str,           # rationale.problem, shortened
        "score": float,           # 0-1, relevance after reranking
        "usage_count": int,
        "owner_name": str
      },
      ...
    ]  # sorted descending by score
    """
```

### How to test independently (no need to wait for Ấn)
Use Khang's seed data — call `recommend("build a lead-classification agent")` and check it returns relevant sample assets.

### Technical note
- Embed `task_description` using **the exact same embedding model** Ấn uses in the Embedding step (agree on this in advance — e.g. `sentence-transformers/all-MiniLM-L6-v2` or the Claude embedding API) — mismatched models make vectors incomparable.

---

## 8. Trí — Onboarding assistant + Delivery UI

### 🎯 Final goal
Open a single screen (Streamlit/Gradio) in front of the judges — type a task description into one box, hit enter, and see both related suggestions (from Hồng) and an explanation of "why this asset was written this way" (your own work) displayed cleanly. This is the only screen judges will see during the demo — everything technical behind it should "disappear" behind this interface.

### Tasks
1. Onboarding assistant: takes one asset, returns a grounded explanation.
2. Delivery UI: simple demo interface (chat-style) that calls both the recommend engine (Hồng) and the onboarding assistant.

### Input — Onboarding assistant
```python
# onboarding/assistant.py
def explain_asset(asset_id: str, question: str = None) -> dict:
    """
    Input: asset_id (string)
           question (string, optional) — a specific question, if any
    """
```

### Output — Onboarding assistant
```python
    """
    Output: {
      "explanation": str,        # synthesized explanation
      "cited_versions": list[int],   # version_number cited
      "cited_constraints": list[str]  # specific constraint referenced
    }
    """
```

### Input/Output — Delivery UI
- Input: calls `recommend()` (from Hồng) and `explain_asset()` (from Trí) directly — no separate API needed, just import the functions in a Python/Streamlit demo.
- Output: a chat-style interface showing results — Streamlit/Gradio is fine (no need to build a custom frontend).

### How to test independently (no need to wait for Ấn)
Use Khang's seed data — call `explain_asset(sample_asset_id)` and check the explanation makes sense.

---

## 9. Final integration checklist (2-3 hours before the demo)

- [ ] Ấn runs a real commit capture → verifies the data lands correctly in Khang's DB.
- [ ] Hồng runs `recommend()` on real (not just seed) data → verifies results make sense.
- [ ] Trí wires the UI to call both functions above, runs the full demo flow once end to end.
- [ ] Prepare 1-2 concrete demo scenarios in advance (like the "Hồng finds An's earlier work" scenario) to present smoothly, without improvising on stage.
