# Loomi Organizational AI Memory

MVP capture layer for turning Git changes to prompts, workflows, and agent configuration into versioned organizational memory. One call captures a commit; another extracts rationale with Featherless GLM-5.2, embeds it, and stores it in SQLite plus Chroma.

## Setup

Create isolated environment:

```bash
conda env create -f environment.yml --solver libmamba
conda activate loomi-an
```

If environment already exists:

```bash
conda env update -n loomi-an -f environment.yml --prune --solver libmamba
```

Configure runtime without committing secrets:

```bash
cp .env.example .env
# Edit .env, then load values into current shell:
set -a
source .env
set +a
```

Required for rationale extraction:

```text
FEATHERLESS_API_KEY=<your-key>
```

Optional paths default to `.loomi/loomi.sqlite3` and `.loomi/chroma`:

```text
LOOMI_DB_PATH=.loomi/loomi.sqlite3
LOOMI_CHROMA_PATH=.loomi/chroma
```

## Capture and Process a Commit

Run from Git repository containing commit. If repository differs from Loomi, add Loomi root to `PYTHONPATH`.

```python
from adapters.git_adapter import capture_commit
from capture_pipeline.process import process_raw_event

event = capture_commit("HEAD")
result = process_raw_event(event["raw_event_id"])
print(result)
```

Expected success shape:

```python
{
    "asset_id": "...",
    "version_id": "...",
    "rationale": {
        "problem": "...",
        "failed_attempts": [],
        "constraints": [],
        "confidence": "auto",
    },
    "embedded": True,
}
```

On LLM, parsing, embedding, Chroma, or SQL failure, pipeline returns `embedded=False`; raw event stays unprocessed for retry.

## Inspect Stored Memory

SQLite:

```bash
sqlite3 .loomi/loomi.sqlite3 \
  'SELECT a.title, av.version_number, r.problem FROM assets a JOIN asset_versions av ON av.asset_id=a.id JOIN rationale r ON r.version_id=av.id;'
```

Chroma by produced version ID:

```python
from db.client import get_vector_collection

record = get_vector_collection().get(ids=["<version-id>"])
print(record["documents"], record["metadatas"])
```

## Tests

Offline suite never spends Featherless credits:

```bash
conda run -n loomi-an pytest -m "not live" -v
```

Explicit live connectivity/model test:

```bash
RUN_FEATHERLESS_LIVE=1 \
FEATHERLESS_API_KEY="<your-key>" \
conda run -n loomi-an pytest tests/integration/test_featherless_live.py -v
```

## Fixed Technology Contracts

- Featherless base URL: `https://api.featherless.ai/v1`
- Rationale model: `zai-org/GLM-5.2`
- Embedding model: `sentence-transformers/all-MiniLM-L6-v2`
- Public functions: `capture_commit(commit_sha: str) -> dict` and `process_raw_event(raw_event_id: str) -> dict`
- Storage access: only through `db/client.py`

See [component design](docs/components/git-capture-pipeline.md) for data flow and extension rules.
