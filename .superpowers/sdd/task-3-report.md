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
