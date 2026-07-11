# Task 3 report — Python core API and lifecycle boundary

## Scope delivered

- Added a thin FastAPI service for health, recommendation, grounded asset review,
  explanation, usage recording, capture processing, and an internal SSE stream.
- Delegated recommendation, explanation, capture, and shared storage to the
  existing domain contracts without changing their public signatures.
- Added a small in-process event bus; `memory_ready` is published only when the
  capture result confirms `embedded=True` and includes an asset id.

## TDD evidence

- RED: `pytest tests/core_service -v` failed during collection because FastAPI
  and `core_service` did not exist.
- GREEN focused: `uv run --with 'fastapi>=0.115,<1' --with 'httpx>=0.28,<1'
  --with 'pytest>=8' python -m pytest tests/core_service -v` passed 7 tests.
- Full offline: `uv run --with-requirements requirements.txt python -m pytest
  -m 'not live' -v` passed 46 tests with 1 live test deselected.

## Self-review

- Request strings are trimmed and reject whitespace-only input at the HTTP
  boundary; `top_k` is bounded to 1..20.
- Usage insertion and counter update share one transaction and return the
  current prompt content without duplicating recommendation/onboarding logic.
- The event backlog is intentionally capped at 100 for the single-process MVP;
  durable replay and multi-replica delivery remain out of scope.
- One dependency warning remains from FastAPI's TestClient compatibility layer;
  it does not affect test results.

## Review-fix TDD evidence

- RED command: `uv run --with-requirements requirements.txt python -m pytest
  tests/core_service -v`
- RED output: `5 failed, 3 passed, 1 warning in 0.33s`. Failures proved the
  untrimmed question, missing `capture_commit` delegation, absent retry
  lifecycle behavior, missing loop-safe event API, and missing clear test
  boundary. The warning came from importing TestClient.
- GREEN command: `uv run --with-requirements requirements.txt python -m pytest
  tests/core_service -v`
- GREEN output after the first implementation pass: `10 passed in 0.26s` with
  no warnings. A separate process-exception regression test was then added;
  final focused and full-suite results are recorded below.

## Review fixes

- `/internal/capture` now publishes `capture_started`, routes the SHA through
  `capture_commit`, passes its exact `raw_event_id` to `process_raw_event`, and
  publishes either grounded `memory_ready` metadata or `capture_retrying`.
- Blocking Git/capture functions run in FastAPI's threadpool while all event
  publication and subscription stays on the serving asyncio loop.
- Replaced TestClient usage with HTTPX ASGI transport, removing the deprecation
  warning instead of suppressing it.
- Optional explanation questions are stripped, reject whitespace-only values,
  and are capped at 2,000 characters.

## Final verification

- Focused: `uv run --with-requirements requirements.txt python -m pytest
  tests/core_service -v` -> `11 passed in 0.27s`, pristine output.
- Full offline: `uv run --with-requirements requirements.txt python -m pytest
  -m 'not live' -q` -> `50 passed, 1 deselected in 2.83s`.
- `git diff --check` produced no output.

## Sensitive-error review fix

- RED: `uv run --with-requirements requirements.txt python -m pytest
  tests/core_service -v` -> `4 failed, 7 passed in 0.41s`. The failures showed
  capture/process exception details and domain failure text reaching the HTTP
  result or `capture_retrying` event.
- GREEN: the same focused command -> `11 passed in 0.27s`, pristine output.
- External capture failures now always expose `error: capture failed`; exception
  details remain available through internal exception/warning logs only.
- Final focused rerun: `11 passed in 0.26s`; full offline suite: `50 passed, 1
  deselected in 2.72s`; both produced pristine output.
