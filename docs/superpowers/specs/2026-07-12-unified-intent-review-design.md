# Unified Intent Review and Similar Changes Design

## Goal

Extend Loomi's existing Intent CI so every processed prompt from the web Composer,
external chat hooks, or a verified GitHub push is analyzed with bounded conversation
context. Persist the generated intent for human approval, notify the UI with a
flashing review state, and index the redacted prompt plus intent for semantic
"Similar Changes" retrieval.

Approval and rejection record human judgment only. They do not block a GitHub push,
reverse a change, create an issue, or gate organizational-memory capture.

## Existing Baseline

The repository already provides `intent_ci/engine.py`, SQL-backed intent reviews,
core and gateway review endpoints, SSE review events, external Claude Code/Codex
hooks, and an Approve/Reject panel. This feature evolves those contracts instead of
creating a second review system.

## Architecture

### Canonical intent event

All sources normalize to one input contract:

```json
{
  "source_env": "web|claude-code|codex|github",
  "prompt": "current user prompt or bounded push summary",
  "messages": [{"role": "user|assistant|system", "content": "..."}],
  "user_name": "optional display identity",
  "external_id": "optional stable source identifier",
  "metadata": {}
}
```

`messages` contains prior context only. `prompt` is the current event. Both are
redacted before they cross the LLM, SQL, Chroma, or SSE boundaries. History is
bounded by a configurable turn limit and total character budget, keeping newest
turns that fit.

### Intent analysis

The analyzer extends the existing Featherless boundary. It receives bounded history
plus current prompt and returns one imperative intent sentence and confidence in
`0..1`. Existing secret-policy, organizational reuse, and intent-clarity checks stay
in the same pipeline. LLM failures become an `intent_clarity:error` result and never
crash ingestion.

### Storage and embeddings

Relational storage remains the source of truth. `intent_reviews` gains canonical
history, external ID, source metadata, embedding state, and last embedding error.
Source identity is unique enough to make retries idempotent.

Intent-review vectors use a separate Chroma collection named `intent_reviews`, not
the approved asset collection. Each vector document is:

```text
<redacted prompt>\n<intent>
```

Vector ID equals review ID. Metadata contains review ID, source environment, review
status, external ID when present, and creation time. Resolution updates vector
metadata without changing its document. This preserves semantic history while
preventing intent reviews from polluting organizational-asset recommendations.

### Similar Changes

A new query operation embeds a task with the same Chroma-managed
`all-MiniLM-L6-v2` model and searches the intent-review collection. Results join SQL
metadata and return review ID, prompt excerpt, generated intent, source, status,
score, user, and creation time. The UI renders these results in a Similar Changes
section attached to the active/newest review.

## Source Adapters

### Web Composer

The client maintains the current session's alternating user/assistant turns. After
a prompt is submitted and processed, it POSTs the current prompt plus prior turns to
the unified review endpoint. History is session-scoped; no cross-browser identity or
long-term chat product is introduced.

### External chat hooks

The hook contract accepts `messages[]` alongside the current prompt. Hooks that can
read native transcript context send it; hooks without that capability send an empty
array. Existing prompt-only callers remain compatible.

### GitHub webhook

The gateway exposes a GitHub push webhook and verifies the raw request body with
`X-Hub-Signature-256` using `GITHUB_WEBHOOK_SECRET`. Missing or invalid signatures
return `401` and create no data.

Accepted push deliveries return quickly and enqueue in-process background work.
GitHub delivery ID and repository-plus-commit SHA provide deduplication. Each commit
becomes one intent review. Its canonical prompt contains repository, branch, author,
commit message, changed supported knowledge files, and a bounded diff summary. It
does not upload arbitrary repository contents. Earlier commits in the same push may
be represented as bounded prior messages for later commits.

This webhook is the GitHub trigger for this scope. Existing local Git polling remains
available but does not create duplicate intent reviews for webhook-seen commits.

## Review Notification and Resolution

Creation emits the existing `intent_review` SSE event. The UI prepends the review,
shows a prominent notification indicator, and applies a finite flashing/pulse
animation to the newest unseen pending card. Opening or interacting with the card
marks it seen locally and stops flashing; it remains pending until approval or
rejection.

Approve/Reject updates SQL and Chroma status metadata, then emits
`intent_review_resolved`. Rejection records judgment only; it does not mutate GitHub
or delete the vector.

## Failure and Retry Behavior

- Invalid GitHub authentication: `401`, no persistence.
- Duplicate delivery/commit: idempotent success, no duplicate SQL row or vector.
- LLM failure: pending review with error check; safe for later re-analysis.
- SQL failure: no success response from synchronous ingestion.
- Chroma failure: SQL row remains with `embedding_status=pending` and error detail.
- Retry operation re-runs missing analysis/embedding idempotently.
- Async GitHub failures are logged with delivery and commit identifiers.
- Secrets are redacted before LLM, persistence, vectorization, and notification.

## API Changes

- Extend `POST /intent-review` with optional `messages`, `external_id`, and `metadata`.
- Add `POST /intent-review/{id}/retry`.
- Add `GET /intent-reviews/{id}/similar?limit=N`.
- Add gateway `POST /api/webhooks/github` using raw-body HMAC verification.
- Preserve current list and resolve endpoints and prompt-only callers.

## Testing

Tests cover:

- canonical normalization for web, external hooks, and GitHub push payloads;
- bounded newest-first history selection and history-grounded LLM input;
- redaction across LLM, SQL, Chroma, and SSE boundaries;
- valid, invalid, and missing GitHub HMAC signatures;
- delivery and commit-SHA idempotency;
- LLM-error persistence and embedding retry;
- separate collection usage and SQL/vector status synchronization;
- semantic Similar Changes retrieval and response shape;
- SSE creation/resolution events;
- UI unseen flashing state, seen behavior, and Approve/Reject actions;
- gateway/core integration while leaving live Postgres/Chroma demo data untouched.

## Out of Scope

- Blocking or reverting GitHub pushes.
- Creating GitHub issues, reviews, or comments.
- Redis or an external job queue.
- Durable multi-device seen state.
- Replacing the existing asset recommendation collection.
- Full chat-product persistence, authentication, or RBAC.
