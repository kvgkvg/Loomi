# Role-Aware View and LLM Rationale Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Import prompt-history exports, generate reviewable observed/inferred rationale, promote trusted rationale, and personalize recommendation/onboarding by organizational role.

**Architecture:** SQLite remains source of truth through `db/client.py`; Chroma indexes only approved distilled assets. New focused modules normalize chat exports, validate LLM rationale statements, manage review transitions, and resolve role lenses. Existing public APIs remain backward compatible through optional parameters.

**Tech Stack:** Python 3.11, SQLite, Chroma/all-MiniLM-L6-v2, Featherless OpenAI-compatible API, pytest.

---

## File map

- Modify `db/schema.sql`: prompt-history, rationale-statement, citation, and review schema.
- Create `adapters/chat_adapter.py`: pure ChatGPT/Claude normalization plus raw-event persistence.
- Create `capture_pipeline/rationale_statements.py`: LLM statement contract, redaction, validation.
- Create `capture_pipeline/chat_process.py`: transactional conversation import and pending rationale persistence.
- Create `rationale/review.py`: approve/edit/reject state transitions and trusted-summary/vector promotion.
- Create `role_lens/lens.py`: structured role policy with safe fallback/cache.
- Modify `recommend/engine.py`: additive `role` argument and bounded role-aware reranking.
- Modify `onboarding/assistant.py`: trusted statements and role lens in evidence/prompt/output.
- Create matching focused tests under `tests/`.

### Task 1: Relational schema

**Files:** Modify `db/schema.sql`; modify `tests/db/test_client.py`.

- [ ] Write a failing schema test asserting `conversations`, `conversation_turns`, `turn_feedback`, `rationale_statements`, and citation tables exist and `review_status` rejects invalid values.
- [ ] Run `conda run -n loomi-an pytest tests/db/test_client.py -q`; expect missing-table failure.
- [ ] Add idempotent SQLite DDL with deterministic IDs, foreign keys, unique source IDs, and review-state checks.
- [ ] Re-run focused test; expect pass.

### Task 2: Chat export adapter

**Files:** Create `adapters/chat_adapter.py`; create `tests/adapters/test_chat_adapter.py`.

- [ ] Write failing tests for ChatGPT mapping trees, Claude linear messages, malformed input, secret redaction, and idempotent raw-event ID.
- [ ] Run focused tests; expect import failure.
- [ ] Implement `normalize_chat_export(payload, source_tool) -> dict` and `capture_chat_export(payload, source_tool) -> dict`. Canonical result contains `external_conversation_id`, `title`, ordered `turns`, and deterministic `raw_event_id`.
- [ ] Re-run focused tests; expect pass.

### Task 3: Dual-rationale LLM boundary

**Files:** Create `capture_pipeline/rationale_statements.py`; create `tests/capture_pipeline/test_rationale_statements.py`.

- [ ] Write failing tests for observed/inferred statements, confidence/citation validation, alternative explanations, fenced JSON, provider errors, and redaction before request.
- [ ] Run focused tests; expect import failure.
- [ ] Implement `extract_rationale_statements(turns, code_evidence=None, client_factory=None) -> list[dict]`; require `statement_type`, `statement`, `evidence_kind`, numeric confidence, resolvable source IDs, and optional alternative.
- [ ] Re-run focused tests; expect pass.

### Task 4: Chat processing and pending review

**Files:** Create `capture_pipeline/chat_process.py`; create `tests/capture_pipeline/test_chat_process.py`.

- [ ] Write failing tests proving import persists conversation/turns, distills a prompt asset/version, stores statements as `pending`, avoids Chroma, re-import is idempotent, and LLM failure keeps event retryable.
- [ ] Run focused tests; expect import failure.
- [ ] Implement `process_chat_event(raw_event_id) -> dict` with one SQLite transaction and existing safe-result pattern. Use deterministic conversation/turn/asset/version/statement IDs.
- [ ] Re-run focused tests; expect pass.

### Task 5: Human review gate

**Files:** Create `rationale/__init__.py`, `rationale/review.py`; create `tests/rationale/test_review.py`.

- [ ] Write failing tests for approve, edit-and-approve, reject, invalid transition, reviewer attribution, original-text audit, compact rationale refresh, and Chroma exclusion/promotion.
- [ ] Run focused tests; expect import failure.
- [ ] Implement `review_statement(statement_id, action, reviewer_id, edited_statement=None, note=None) -> dict`. Only approve/edit builds trusted summary and upserts current asset document; reject never embeds.
- [ ] Re-run focused tests; expect pass.

### Task 6: Role lens

**Files:** Create `role_lens/__init__.py`, `role_lens/lens.py`; create `tests/role_lens/test_lens.py`.

- [ ] Write failing tests for validated LLM JSON, arbitrary role names, fallback, bounded weights, cache, and no-secret error boundary.
- [ ] Run focused tests; expect import failure.
- [ ] Implement `resolve_role_lens(role, client_factory=None) -> dict` with four local presets, LLM enhancement for other roles, normalized process cache, and Developer fallback.
- [ ] Re-run focused tests; expect pass.

### Task 7: Role-aware recommendation

**Files:** Modify `recommend/engine.py`, `recommend/scoring.py`; modify `tests/test_engine.py`, `tests/test_scoring.py`.

- [ ] Write failing mocked-collection tests for `recommend(task, top_k, role=None)`, backward-compatible output, bounded role boost, and semantic relevance dominance.
- [ ] Run focused tests; expect unexpected-argument/scoring failures.
- [ ] Add pure bounded role score and optional role lens. Keep legacy result keys when `role is None`; add `role_reason` only for role-aware calls.
- [ ] Re-run focused tests; expect pass.

### Task 8: Role-aware trusted onboarding

**Files:** Modify `onboarding/assistant.py`; modify `tests/test_onboarding_assistant.py`.

- [ ] Write failing tests proving only approved/edited statements load, pending/rejected never appear, role lens enters prompt, citations validate, and old call remains valid.
- [ ] Run focused tests; expect failure.
- [ ] Implement `explain_asset(asset_id, question=None, role=None)` and additive output fields `rationale_statements`, `role`, and `primary_actions` only for role-aware calls.
- [ ] Re-run focused tests; expect pass.

### Task 9: Integration, docs, and verification

**Files:** Modify `README.md`; create `tests/integration/test_prompt_history_review.py`; append `memory/role-aware-prompt-history.md`.

- [ ] Write integration test: Claude export -> pending rationale -> approval -> vector upsert -> role-aware onboarding/recommendation using fake LLM/vector boundaries.
- [ ] Run integration test; expect failure, then add only missing glue until pass.
- [ ] Run focused offline suite excluding real Chroma embedding tests.
- [ ] Run full `conda run -n loomi-an pytest -m "not live" -q`; if Chroma download still blocks, report command/time and separately prove all mocked/relational tests.
- [ ] Update README contracts and append required memory entry.
- [ ] Run `git diff --check` and inspect `git status` before completion.
