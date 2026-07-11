# Ấn — Adapter and Capture Pipeline Memory

## 2026-07-11

### Completed

- Implemented shared SQLite/Chroma clients and MVP schema.
- Implemented Git commit adapter with canonical event contract.
- Implemented Featherless rationale extraction using `zai-org/GLM-5.2` at `https://api.featherless.ai/v1`.
- Implemented transactional asset/version/rationale creation and Chroma upsert.
- Created isolated Conda environment definition `loomi-an`.
- Added unit, integration, retry, idempotency, versioning, and opt-in live API tests.
- Added operator and component documentation.

### Decisions

- Chose SQLite plus persistent Chroma for self-contained hackathon demo.
- Asset identity is repository root plus sorted captured path set; branch is excluded by MVP scope.
- Version and asset UUIDs are deterministic so retries do not duplicate vector records.
- Featherless credential is environment-only. Project contains placeholders, never real key.
- Embedding model is fixed to `sentence-transformers/all-MiniLM-L6-v2` across components.

### Problems and Fixes

- Base Conda environment had `chromadb-client`, which is HTTP-only and cannot create `PersistentClient`. Created dedicated `loomi-an` environment with full `chromadb` package.
- Initial `conda env create` with classic resolver spent several minutes on metadata. Used libmamba solver to create Python 3.11 environment, then installed manifest pip dependencies.
- Chroma cannot share SQLite transaction. Deterministic version IDs make vector retry an idempotent upsert.

### Remaining Integration

- Hồng's recommendation engine must reuse exact MiniLM embedding model.
- Team may swap SQLite implementation for PostgreSQL only inside `db/client.py`.
- Demo runner/poller can call `capture_commit()` then `process_raw_event()`; background automation is intentionally outside current scope.
