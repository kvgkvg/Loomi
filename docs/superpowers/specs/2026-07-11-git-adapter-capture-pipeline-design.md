# Git Adapter and Capture Pipeline Design

## Goal

Implement Ấn's end-to-end MVP path: capture a real Git commit, store a canonical raw event, create or version an organizational knowledge asset, extract grounded rationale through Featherless, embed the result with the shared model, and make it searchable in Chroma.

## Scope

Included:

- SQLite-backed implementation of the shared `db/client.py` contract.
- Persistent Chroma collection.
- Git commit capture through `capture_commit(commit_sha: str) -> dict`.
- Sequential capture processing through `process_raw_event(raw_event_id: str) -> dict`.
- Featherless OpenAI-compatible chat completion using `zai-org/GLM-5.2`.
- Embeddings using `sentence-transformers/all-MiniLM-L6-v2` only.
- Automated tests, optional live smoke test, environment definition, operator docs, and required session memory.

Excluded:

- Git webhooks, background polling daemon, PostgreSQL deployment, graph relationships, RBAC, multi-branch identity, and non-Git adapters.

## Architecture

### Database client

`db/client.py` owns all storage connections. `get_pg_connection()` returns a configured SQLite connection despite its legacy cross-team name. `get_vector_collection()` returns one persistent Chroma collection. Schema initialization is idempotent and implements the MVP tables needed by the adapter, pipeline, and downstream consumers.

Runtime paths come from environment variables and default to a local `.loomi/` directory. Tests override both paths with temporary directories. No other module opens SQLite or instantiates Chroma directly.

### Git adapter

`adapters/git_adapter.py` invokes Git with argument arrays, never shell interpolation. It validates the commit, reads metadata and changed paths, and selects supported knowledge files. Supported files are text files representing prompts, workflows, or agent configuration; binary/deleted files are excluded.

The canonical event contains:

- title: commit subject;
- content: current content of selected changed files, with path boundaries;
- raw signal: repository identity, commit metadata, file list, and unified diff;
- source tool: `git`.

The adapter inserts one unprocessed `raw_events` row and returns the exact contract from `task.md`. Repository root and changed paths are retained inside `raw_signal` so the pipeline can derive stable asset identity.

### Capture pipeline

`capture_pipeline/process.py` processes one raw event in this order:

1. Load the unprocessed event.
2. Derive asset key from repository root plus changed path set.
3. Create a new asset or append the next `asset_versions` row.
4. Ask Featherless for rationale JSON containing `problem`, `failed_attempts`, `constraints`, and `confidence`.
5. Validate and normalize the response before inserting `rationale`.
6. Embed version content plus rationale problem with `sentence-transformers/all-MiniLM-L6-v2`.
7. Upsert the vector using version ID as Chroma document ID and asset/version IDs as metadata.
8. Set `processed=true`, store `processed_asset_version_id`, and commit the SQL transaction.

Repeat calls for an already processed event return its persisted result without creating another version.

## Featherless Integration

The implementation uses the official OpenAI-compatible interface:

- Base URL: `https://api.featherless.ai/v1`
- Model: `zai-org/GLM-5.2`
- Authentication: `FEATHERLESS_API_KEY` environment variable
- Endpoint through SDK: `client.chat.completions.create(...)`

The system prompt demands a single JSON object. The response parser accepts plain JSON or one fenced JSON block, then validates field types. Temperature is low for stable extraction. API key is never committed, printed, persisted, or included in exceptions exposed by project code.

## Failure and Consistency Model

LLM, parsing, embedding, vector-write, and SQL failures do not escape `process_raw_event`. SQL changes are rolled back, and the event remains `processed=false` for retry. The function returns an error-shaped dictionary with `embedded=false` and a concise sanitized error field; successful output preserves the required contract.

Chroma cannot participate in the SQLite transaction. Vector upsert therefore happens before the final SQL commit and uses deterministic version IDs, making retry overwrite the same vector rather than duplicate it. If final SQL commit fails, retry may upsert the same vector safely.

Invalid inputs to pure boundaries, such as an unknown commit or missing raw event, are reported clearly. Adapter failures occur before any row is inserted where possible.

## Asset Identity and Versioning

MVP identity is repository root plus the sorted set of captured file paths. A later commit touching the same set appends a version; a different set creates another asset. Asset type is inferred from path/extension and defaults to `prompt`. This avoids filename collision across repositories while keeping multi-branch behavior explicitly out of scope.

## Interfaces

Public signatures remain exactly:

```python
def capture_commit(commit_sha: str) -> dict:
    ...

def process_raw_event(raw_event_id: str) -> dict:
    ...
```

Test seams may be private helpers or optional dependency factories, but public signatures do not change.

## Environment and Configuration

`environment.yml` creates isolated Conda environment `loomi-an`. Dependencies include Python, OpenAI SDK, Chroma, sentence-transformers, pytest, and dotenv support. `.env.example` documents variables without secrets. `.gitignore` excludes `.env`, SQLite files, Chroma data, model caches, and runtime artifacts.

## Testing

Tests follow red-green-refactor and cover:

- canonical capture from a temporary Git repository;
- invalid commit and commits without supported files;
- new asset creation and subsequent version increment;
- exact Featherless base URL/model request through a mocked client boundary;
- valid, fenced, malformed, and schema-invalid rationale responses;
- embedding text composition and deterministic Chroma metadata;
- idempotent reprocessing;
- LLM/embedding failure rollback with `processed=false`;
- secret absence from tracked files and emitted errors.

One opt-in live smoke test calls Featherless using the supplied environment variable. It verifies connectivity, model availability, and parseable rationale without printing the secret or full response. Normal tests do not spend API credits.

## Documentation and Demo

README documentation will cover setup, Conda activation, environment variables, schema initialization, capturing a commit, processing the returned event ID, inspecting SQLite, querying Chroma, running tests, and running the optional live smoke test. Component docs explain contracts, data flow, identity rules, retry behavior, and extension points. `memory/an.md` is append-only and records decisions, problems encountered, fixes, and next steps.

Demo acceptance path:

1. Activate `loomi-an` and export `FEATHERLESS_API_KEY`.
2. Commit a supported prompt/config change.
3. Call `capture_commit(sha)`.
4. Call `process_raw_event(raw_event_id)`.
5. Inspect the new asset/version/rationale rows and query its version vector from Chroma.

## Security

The supplied Featherless key is treated as runtime-only secret material. It will be passed to commands only through process environment, never written to `.env`, shell history files, tests, docs, memory, Git objects, or source code. Documentation uses placeholders exclusively.
