# Task 2 Report — Portable Python Storage

## Scope

- Preserved public `get_pg_connection()` and `get_vector_collection()` names.
- Selected PostgreSQL only when `DATABASE_URL` is set; otherwise retained SQLite.
- Selected remote Chroma only when `CHROMA_HOST` is set; otherwise retained embedded Chroma.
- Added PostgreSQL schema bootstrap and persisted `git_poll_state` in both dialects.
- Added `psycopg[binary]`; no ORM and no domain-function signature changes.

## RED

Command:

```text
pytest tests/db/test_postgres_compat.py -v
```

Observed expected failure (`exit 1`):

```text
collected 3 items
test_postgres_adapter_accepts_sqlite_style_placeholders FAILED
test_postgres_adapter_rows_support_names_and_indexes FAILED
test_remote_chroma_selected_from_environment FAILED

AttributeError: module 'db.client' has no attribute '_connect_postgres'
AttributeError: 'FakeChroma' object has no attribute 'PersistentClient'
3 failed in 0.03s
```

The failures showed that PostgreSQL selection/compatibility and remote Chroma selection did not exist.

## GREEN — Focused Contract

Command:

```text
.venv311/bin/pytest tests/db/test_client.py tests/db/test_postgres_compat.py -v
```

Observed (`exit 0`):

```text
collected 5 items
tests/db/test_client.py::test_connection_initializes_required_tables PASSED
tests/db/test_client.py::test_vector_collection_is_persistent PASSED
tests/db/test_postgres_compat.py::test_postgres_adapter_accepts_sqlite_style_placeholders PASSED
tests/db/test_postgres_compat.py::test_postgres_adapter_rows_support_names_and_indexes PASSED
tests/db/test_postgres_compat.py::test_remote_chroma_selected_from_environment PASSED
5 passed in 0.49s
```

## GREEN — Full Offline Suite

Command:

```text
.venv311/bin/pytest -m "not live" -v
```

The first sandboxed run reached 35 passing tests but 4 Chroma embedding tests
could not create `/home/pearspringmind/.cache/chroma` because the home directory
was read-only. The identical command was rerun with access to the existing model
cache and produced (`exit 0`):

```text
collected 40 items / 1 deselected / 39 selected
39 passed, 1 deselected in 18.92s
```

## Implementation Notes

- `_PostgresConnection` and `_PostgresCursor` are deliberately small wrappers.
- SQLite-style `?` placeholders become psycopg `%s` placeholders centrally.
- `_PostgresRow` supports both `row["column"]` and `row[index]`, matching current callers.
- PostgreSQL bootstrap uses `db/schema.postgres.sql`; SQLite continues using `db/schema.sql`.
- Chroma document/query behavior and collection metadata remain unchanged.

## Concern

The PostgreSQL path is contract-tested with a DB-API fake, not a live Compose
database in this task. Full Compose runtime verification belongs after the thin
core service and poller are added, as sequenced by the implementation plan.
