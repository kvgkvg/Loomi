# Git Capture Pipeline

## Responsibilities

| Component | Responsibility | Dependencies |
|---|---|---|
| `db/client.py` | Initialize SQLite schema; return SQLite and persistent Chroma clients | SQLite, ChromaDB |
| `adapters/git_adapter.py` | Read one Git commit; persist canonical `raw_events` row | Git CLI, DB client |
| `capture_pipeline/llm.py` | Call Featherless; validate rationale JSON | OpenAI SDK |
| `capture_pipeline/process.py` | Version asset, persist rationale, embed, upsert vector, finalize event | DB client, LLM boundary, sentence-transformers |

No component opens its own database outside `db/client.py`.

## Public Contracts

```python
def capture_commit(commit_sha: str) -> dict:
    """Return raw_event_id, source_tool, title, content, and raw_signal."""

def process_raw_event(raw_event_id: str) -> dict:
    """Return asset_id, version_id, rationale, and embedded status."""
```

Signatures match `task.md` and must not change without team coordination.

## Data Flow

1. Adapter resolves commit through `git rev-parse`.
2. It selects surviving `.md`, `.txt`, `.prompt`, `.json`, `.yaml`, and `.yml` files.
3. It stores file content plus structured JSON signal containing repository root, commit SHA, sorted paths, and diff.
4. Pipeline derives asset key as SHA-256 of repository root plus sorted path set.
5. Existing key appends next version; new key creates an asset.
6. Featherless reads content and raw source signal.
7. Valid rationale is stored in SQLite.
8. Exact shared embedding model encodes `content + "\n\nProblem: " + rationale.problem`.
9. Chroma stores vector with deterministic version UUID and asset/version metadata.
10. SQL transaction sets asset current version and raw event processed state.

MVP deliberately ignores branch identity. Same repository/path set across branches maps to one asset, consistent with project out-of-scope rules.

## Featherless Request

Implementation follows Featherless OpenAI-compatible API:

- SDK client: `OpenAI(base_url="https://api.featherless.ai/v1", api_key=...)`
- Chat model: `zai-org/GLM-5.2`
- Temperature: `0.1`
- Credential source: `FEATHERLESS_API_KEY` process environment only

System prompt requires one JSON object:

```json
{
  "problem": "non-empty string",
  "failed_attempts": ["string"],
  "constraints": ["string"],
  "confidence": "auto"
}
```

Parser accepts plain JSON or one JSON Markdown fence. Wrong types, invalid confidence, malformed JSON, empty response, missing key, and SDK errors become sanitized `RationaleError` values.

Official Featherless model/API example: <https://featherless.ai/blog/whats-new-in-glm-5-2-run-it-on-featherless>

## Transactions and Retry

SQL inserts and updates run in one transaction. Any LLM, validation, embedding, vector, or SQL exception rolls back asset/version/rationale changes. Pipeline then explicitly leaves `raw_events.processed=0` and returns:

```python
{
    "asset_id": None,
    "version_id": None,
    "rationale": None,
    "embedded": False,
    "error": "Pipeline processing failed",
}
```

Chroma cannot join SQLite transaction. Version UUID derives deterministically from raw event ID; retry upserts same vector ID rather than duplicating it. Reprocessing a completed event loads persisted result and creates no new version.

## Schema Notes

SQLite mirrors MVP tables from `task.md`. PostgreSQL `UUID`, `JSONB`, timestamps, and booleans map to SQLite text/integer forms. `assets.asset_key` is extra internal unique identity. Public `get_pg_connection()` name remains unchanged for compatibility even though MVP backend is SQLite.

## Extension Points

- Add another source by emitting same canonical `raw_events` fields.
- Replace SQLite with PostgreSQL inside `db/client.py`; consumers remain unchanged.
- Downstream recommendation must use `sentence-transformers/all-MiniLM-L6-v2`, otherwise query and stored vectors are incomparable.
- Background polling/webhooks may call public adapter and pipeline functions; they are outside current MVP.

## Security

Never persist or log Featherless key. `.env`, runtime SQLite, Chroma directory, caches, and worktrees are ignored. Tests use fake keys except explicit live test; errors never interpolate SDK exception text.
