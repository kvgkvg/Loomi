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

## Prompt History, Rationale Review, and Role-Aware Views

Import a ChatGPT or Claude JSON export, then generate pending rationale:

```python
import json
from adapters.chat_adapter import capture_chat_export
from capture_pipeline.chat_process import process_chat_event

payload = json.load(open("conversation.json"))
event = capture_chat_export(payload, "claude")  # or "chatgpt"
pending = process_chat_event(event["raw_event_id"])
```

LLM statements are not trusted until user review:

```python
from rationale.review import list_pending_statements, review_statement

item = list_pending_statements()[0]
review_statement(item["id"], "approve", reviewer_id="<existing-user-id>")
# Other actions: "edit" with edited_statement=..., or "reject".
```

Approval refreshes compact rationale and the asset's Chroma document. Pending and rejected statements never affect search or normal onboarding.

Pass a role for personalized ranking and explanation:

```python
from recommend.engine import recommend
from onboarding.assistant import explain_asset

results = recommend("produce reliable structured output", role="Tech Lead")
explanation = explain_asset(results[0]["asset_id"], role="Intern")
```

Run the review/discovery UI after installing requirements:

```bash
streamlit run delivery/app.py
```

Built-in role lenses: Intern, Developer, Tech Lead, Manager. Other role names use validated Featherless output with a Developer-like fallback.
