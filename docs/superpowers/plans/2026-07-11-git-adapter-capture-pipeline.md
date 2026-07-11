# Git Adapter and Capture Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Ấn's tested Git-to-SQLite/Chroma capture path with Featherless GLM-5.2 rationale extraction.

**Architecture:** `db/client.py` exclusively owns SQLite and Chroma access. Git adapter persists canonical events; capture pipeline versions assets, calls a small Featherless boundary, validates rationale, embeds shared text, and finalizes processing with retry-safe failure behavior.

**Tech Stack:** Python 3.11, SQLite, ChromaDB, sentence-transformers, OpenAI Python SDK, pytest, Conda.

---

## File Map

- `environment.yml`: reproducible `loomi-an` Conda environment.
- `.env.example`, `.gitignore`: safe runtime configuration and artifact exclusions.
- `db/client.py`: schema, SQLite connection, and Chroma collection factories.
- `adapters/git_adapter.py`: Git inspection and canonical raw-event persistence.
- `capture_pipeline/llm.py`: Featherless request and rationale response validation.
- `capture_pipeline/process.py`: transactional version/rationale/vector orchestration.
- `tests/`: behavioral unit/integration tests plus opt-in live smoke test.
- `README.md`, `docs/components/`, `memory/an.md`: operator, component, and session documentation.

### Task 1: Environment and Storage Contract

**Files:**
- Create: `environment.yml`
- Create: `.env.example`
- Create: `.gitignore`
- Create: `db/__init__.py`
- Create: `db/client.py`
- Create: `tests/conftest.py`
- Create: `tests/db/test_client.py`

- [ ] **Step 1: Write failing storage tests**

```python
def test_connection_initializes_required_tables(isolated_runtime):
    from db.client import get_pg_connection
    conn = get_pg_connection()
    names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"raw_events", "users", "assets", "asset_versions", "rationale"} <= names

def test_vector_collection_is_persistent(isolated_runtime):
    from db.client import get_vector_collection
    assert get_vector_collection().name == "organizational_memory"
```

- [ ] **Step 2: Run tests and confirm missing-module failure**

Run: `pytest tests/db/test_client.py -v`
Expected: FAIL because `db.client` does not exist.

- [ ] **Step 3: Add environment/config files and minimal storage implementation**

`environment.yml` names `loomi-an` and pins Python 3.11; pip dependencies are `openai`, `chromadb`, `sentence-transformers`, `python-dotenv`, and `pytest`. `db/client.py` reads `LOOMI_DB_PATH` and `LOOMI_CHROMA_PATH`, enables foreign keys, creates the MVP schema idempotently, and returns `chromadb.PersistentClient(...).get_or_create_collection("organizational_memory")`.

- [ ] **Step 4: Verify storage tests pass**

Run: `pytest tests/db/test_client.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit storage foundation**

```bash
git add environment.yml .env.example .gitignore db tests/conftest.py tests/db/test_client.py
git commit -m "feat: add persistent memory clients"
```

### Task 2: Git Adapter

**Files:**
- Create: `adapters/__init__.py`
- Create: `adapters/git_adapter.py`
- Create: `tests/adapters/test_git_adapter.py`

- [ ] **Step 1: Write failing adapter tests**

```python
def test_capture_commit_persists_canonical_event(git_repo, isolated_runtime, monkeypatch):
    monkeypatch.chdir(git_repo.path)
    result = capture_commit(git_repo.sha)
    assert result["source_tool"] == "git"
    assert result["title"] == "add support prompt"
    assert "prompts/support.md" in result["content"]
    row = get_pg_connection().execute(
        "SELECT processed, raw_signal FROM raw_events WHERE id = ?", (result["raw_event_id"],)
    ).fetchone()
    assert row["processed"] == 0
    assert git_repo.sha in row["raw_signal"]

def test_capture_commit_rejects_unknown_sha(git_repo, isolated_runtime, monkeypatch):
    monkeypatch.chdir(git_repo.path)
    with pytest.raises(ValueError, match="Unknown commit"):
        capture_commit("deadbeef")
```

- [ ] **Step 2: Run tests and confirm import failure**

Run: `pytest tests/adapters/test_git_adapter.py -v`
Expected: FAIL because `adapters.git_adapter` does not exist.

- [ ] **Step 3: Implement Git capture**

Use `subprocess.run(["git", ...], check=True, text=True, capture_output=True)` to resolve repository root, commit, subject, changed paths, file contents, and unified diff. Support `.md`, `.txt`, `.prompt`, `.json`, `.yaml`, and `.yml`; reject commits with no supported surviving file. Serialize structured `raw_signal` as JSON and insert one UUID raw event through `get_pg_connection()`.

- [ ] **Step 4: Verify adapter tests pass**

Run: `pytest tests/adapters/test_git_adapter.py -v`
Expected: all adapter tests pass.

- [ ] **Step 5: Commit adapter**

```bash
git add adapters tests/adapters
git commit -m "feat: capture git commits as raw events"
```

### Task 3: Featherless Rationale Boundary

**Files:**
- Create: `capture_pipeline/__init__.py`
- Create: `capture_pipeline/llm.py`
- Create: `tests/capture_pipeline/test_llm.py`

- [ ] **Step 1: Write failing response/request tests**

```python
def test_extract_rationale_uses_required_endpoint_and_model(monkeypatch):
    fake = FakeOpenAI('{"problem":"Reduce misroutes","failed_attempts":[],"constraints":["JSON only"],"confidence":"auto"}')
    monkeypatch.setenv("FEATHERLESS_API_KEY", "test-key")
    result = extract_rationale("prompt", "diff", client_factory=fake.factory)
    assert fake.base_url == "https://api.featherless.ai/v1"
    assert fake.request["model"] == "zai-org/GLM-5.2"
    assert result["problem"] == "Reduce misroutes"

@pytest.mark.parametrize("content", ["not json", '{"problem": 3}'])
def test_extract_rationale_rejects_invalid_payload(content, monkeypatch):
    monkeypatch.setenv("FEATHERLESS_API_KEY", "test-key")
    with pytest.raises(RationaleError):
        extract_rationale("prompt", "diff", client_factory=FakeOpenAI(content).factory)
```

- [ ] **Step 2: Run tests and confirm import failure**

Run: `pytest tests/capture_pipeline/test_llm.py -v`
Expected: FAIL because `capture_pipeline.llm` does not exist.

- [ ] **Step 3: Implement validated Featherless call**

Define constants `FEATHERLESS_BASE_URL` and `FEATHERLESS_MODEL`; define `RationaleError`; build `OpenAI(base_url=..., api_key=...)`; call `chat.completions.create` with system/user messages and low temperature. Strip one optional JSON fence, decode object, require non-empty string `problem`, string lists for `failed_attempts`/`constraints`, and confidence in `{auto, user_provided}`. Wrap SDK/parse errors in sanitized `RationaleError` without response headers or API key.

- [ ] **Step 4: Verify LLM boundary tests pass**

Run: `pytest tests/capture_pipeline/test_llm.py -v`
Expected: all LLM tests pass.

- [ ] **Step 5: Commit LLM boundary**

```bash
git add capture_pipeline tests/capture_pipeline/test_llm.py
git commit -m "feat: extract rationale with Featherless"
```

### Task 4: Capture Orchestrator

**Files:**
- Create: `capture_pipeline/process.py`
- Create: `tests/capture_pipeline/test_process.py`

- [ ] **Step 1: Write failing success/version/idempotency tests**

```python
def test_process_creates_searchable_asset(raw_event, fake_services, isolated_runtime):
    result = process_raw_event(raw_event)
    assert result["rationale"]["problem"] == "Reduce misroutes"
    assert result["embedded"] is True
    conn = get_pg_connection()
    assert conn.execute("SELECT processed FROM raw_events WHERE id=?", (raw_event,)).fetchone()[0] == 1

def test_process_is_idempotent(raw_event, fake_services, isolated_runtime):
    first = process_raw_event(raw_event)
    second = process_raw_event(raw_event)
    assert second == first
    assert get_pg_connection().execute("SELECT count(*) FROM asset_versions").fetchone()[0] == 1
```

- [ ] **Step 2: Run success tests and confirm import failure**

Run: `pytest tests/capture_pipeline/test_process.py -v -k 'creates or idempotent'`
Expected: FAIL because `capture_pipeline.process` does not exist.

- [ ] **Step 3: Implement minimal successful pipeline**

Load event; decode repository/path identity; infer type; create/find asset; calculate `max(version_number)+1`; insert version and rationale; embed `content + "\n\nProblem: " + problem` with exactly `sentence-transformers/all-MiniLM-L6-v2`; upsert Chroma by version UUID; update asset current version and event processing fields; commit. Persist JSON lists in SQLite text columns and deserialize them in result dictionaries.

- [ ] **Step 4: Verify success tests pass**

Run: `pytest tests/capture_pipeline/test_process.py -v -k 'creates or idempotent'`
Expected: selected tests pass.

- [ ] **Step 5: Write failing rollback/version tests**

```python
def test_llm_failure_keeps_event_retryable(raw_event, failing_services, isolated_runtime):
    result = process_raw_event(raw_event)
    assert result["embedded"] is False
    assert "error" in result
    conn = get_pg_connection()
    assert conn.execute("SELECT processed FROM raw_events WHERE id=?", (raw_event,)).fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM asset_versions").fetchone()[0] == 0

def test_later_commit_appends_version(two_events_same_identity, fake_services, isolated_runtime):
    process_raw_event(two_events_same_identity[0])
    result = process_raw_event(two_events_same_identity[1])
    assert get_pg_connection().execute(
        "SELECT version_number FROM asset_versions WHERE id=?", (result["version_id"],)
    ).fetchone()[0] == 2
```

- [ ] **Step 6: Run rollback/version tests and verify failures**

Run: `pytest tests/capture_pipeline/test_process.py -v -k 'failure or later'`
Expected: FAIL until rollback and stable identity behavior exist.

- [ ] **Step 7: Add rollback and version handling**

Wrap pipeline work in one SQL transaction, roll back on every caught exception, and force `processed=0` in a separate short transaction. Return `{"asset_id": None, "version_id": None, "rationale": None, "embedded": False, "error": sanitized_message}`. Use deterministic SHA-256 identity from repository root plus sorted path list.

- [ ] **Step 8: Verify full pipeline tests pass**

Run: `pytest tests/capture_pipeline/test_process.py -v`
Expected: all process tests pass.

- [ ] **Step 9: Commit orchestrator**

```bash
git add capture_pipeline/process.py tests/capture_pipeline/test_process.py
git commit -m "feat: process raw events into searchable assets"
```

### Task 5: Live API Smoke Test and End-to-End Test

**Files:**
- Create: `tests/integration/test_end_to_end.py`
- Create: `tests/integration/test_featherless_live.py`
- Create: `pytest.ini`

- [ ] **Step 1: Write end-to-end and opt-in live tests**

```python
def test_commit_to_vector_flow(git_repo, isolated_runtime, fake_services, monkeypatch):
    monkeypatch.chdir(git_repo.path)
    event = capture_commit(git_repo.sha)
    result = process_raw_event(event["raw_event_id"])
    assert result["embedded"] is True
    assert get_vector_collection().get(ids=[result["version_id"]])["ids"] == [result["version_id"]]

@pytest.mark.live
def test_featherless_returns_valid_rationale():
    if not os.getenv("RUN_FEATHERLESS_LIVE"):
        pytest.skip("set RUN_FEATHERLESS_LIVE=1")
    result = extract_rationale("Classify support tickets into billing or technical queues.", "Add strict JSON output.")
    assert result["problem"]
```

- [ ] **Step 2: Run offline suite and fix fixture integration only**

Run: `pytest -m 'not live' -v`
Expected: all offline tests pass; live test deselected.

- [ ] **Step 3: Run live Featherless smoke test**

Run with secret supplied only in process environment: `RUN_FEATHERLESS_LIVE=1 pytest tests/integration/test_featherless_live.py -v`
Expected: 1 passed and no secret appears in output.

- [ ] **Step 4: Commit integration tests**

```bash
git add pytest.ini tests/integration
git commit -m "test: cover git capture end to end"
```

### Task 6: Documentation and Final Verification

**Files:**
- Modify: `README.md`
- Create: `docs/components/git-capture-pipeline.md`
- Create: `memory/an.md`

- [ ] **Step 1: Document setup and components**

README must include exact Conda creation/activation, placeholder environment variables, offline/live test commands, capture/process Python example, DB inspection, and Chroma query. Component doc must cover contracts, tables, asset identity, request model/base URL, embedding invariant, error/retry semantics, and extension points. Memory entry must record decisions, errors/fixes, completed work, and next steps without including secrets.

- [ ] **Step 2: Verify no secret or placeholders are tracked**

Run: `git grep -n -E 'rc_[A-Za-z0-9]{20,}|TBD|[T]ODO|implement later' -- ':!docs/superpowers/plans/*'`
Expected: no output.

- [ ] **Step 3: Build isolated Conda environment from manifest**

Run: `conda env create -f environment.yml` (or `conda env update -f environment.yml --prune` if `loomi-an` exists)
Expected: exit 0 and `conda run -n loomi-an python --version` reports Python 3.11.

- [ ] **Step 4: Run complete fresh verification**

Run: `conda run -n loomi-an pytest -m 'not live' -v`
Expected: all offline tests pass, zero failures.

Run: `conda run -n loomi-an python -m compileall -q adapters capture_pipeline db tests`
Expected: exit 0.

Run: `git diff --check`
Expected: exit 0.

- [ ] **Step 5: Commit documentation**

```bash
git add README.md docs/components memory/an.md
git commit -m "docs: explain git capture pipeline"
```
