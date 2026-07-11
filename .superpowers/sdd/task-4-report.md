# Task 4 Report: Retry-safe Git polling

## Status

Complete.

## Delivered

- `GitPoller.poll_once()` captures each unchanged HEAD once, persists observed
  and processed SHAs, and retries the same raw event after incomplete processing.
- Retry delay starts at the three-second poll interval, doubles, and caps at 30
  seconds by default; success resets it.
- Lifecycle publication is `capture_started` -> `capture_retrying` or
  `memory_ready`, with success gated on embedding, asset ID, and version ID.
- FastAPI owns one optional poller worker through lifespan when
  `LOOMI_GIT_REPOSITORY` points to the configured repository.
- Shared poll-state reads/writes remain in `db/client.py` for SQLite/PostgreSQL.

## TDD evidence

- Initial red: `pytest tests/core_service/test_poller.py -v` failed collection
  with `ModuleNotFoundError: No module named 'core_service.poller'`.
- Review red: advancing HEAD during a pending failure processed `raw-def`
  instead of retrying `raw-abc`; the focused regression test failed as expected.
- Focused green: `pytest tests/core_service/test_poller.py
  tests/capture_pipeline/test_process.py -v` -> 11 passed.
- Full offline green: `.venv311/bin/pytest -m 'not live' -q` -> 56 passed,
  1 deselected.
- `git diff --check` -> clean.

## Concerns

- The worker is intentionally disabled unless `LOOMI_GIT_REPOSITORY` is set;
  Compose must mount/configure a Git repository before automatic capture runs.
- A failed pending raw-event ID is in-memory. On a crash before processing
  succeeds, restart observes the persisted SHA and safely recaptures it; completed
  SHAs remain deduplicated across restarts.
