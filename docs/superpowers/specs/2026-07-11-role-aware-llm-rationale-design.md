# Role-Aware View and LLM Rationale — Design Proposal

## Status

Approved revised proposal. Documentation only; no implementation included.

## Scope decision

Keep Loomi's current asset/version/rationale architecture. Do not add graph storage, graph traversal, Graph Reasoner, or graph visualization. Add only two capabilities:

1. role-aware personalization across recommendation and onboarding views;
2. LLM-enhanced rationale from prompt history, including explicit and inferred reasoning.

## Problem

Loomi currently captures Git changes and extracts one rationale per asset version. Organizational knowledge also lives in ChatGPT and Claude prompt history: prompt edits, regenerations, feedback, and successful outcomes. Employees in different roles need different depth and emphasis when reusing that knowledge.

## Goals

- Import ChatGPT and Claude conversation exports as an additional source.
- Distill reusable prompt assets and revisions from conversation history.
- Extract rationale explicitly stated in chat.
- Infer likely rationale when chat does not state it, using prompt revisions, responses, feedback, and optionally linked Git evidence.
- Clearly label explicit evidence and AI inference.
- Require user review of LLM-produced rationale before treating it as trusted organizational knowledge.
- Personalize ranking, result cards, and onboarding explanation for a supplied role.
- Preserve current SQLite, Chroma, Featherless, MiniLM, and Streamlit choices.

## Non-goals

- Knowledge graph storage or visualization.
- Generic node/edge schemas or multi-hop graph reasoning.
- RBAC or permission filtering.
- Automatic private-chat scraping.
- Full governance, retention, or compliance controls.
- LangChain, cross-encoder reranking, or a new vector model.

## Architecture

```text
ChatGPT / Claude export
  -> chat adapter
  -> canonical raw event
  -> conversation turns and feedback
  -> LLM rationale extraction/inference
  -> user approve / edit / reject
  -> distilled asset + asset version + rationale statements
  -> Chroma upsert of distilled asset

Optional linked Git event
  -> existing Git adapter
  -> supporting evidence for an inferred rationale

Role + task/question
  -> validated role lens
  -> current recommend/onboarding pipeline
  -> role-aware ranking and presentation
```

New boundaries:

- `adapters/chat_adapter.py`: normalize ChatGPT and Claude exports.
- `capture_pipeline/chat_process.py`: distill prompt assets and generate rationale statements while following existing retry behavior.
- `role_lens/`: map a role name to a validated personalization policy.

Existing `recommend/engine.py` and `onboarding/assistant.py` remain orchestration boundaries. All storage access continues through `db/client.py`.

## Prompt-history storage

Keep current asset tables. Add minimal relational tables.

### `conversations`

- `id`
- `source_tool`
- `external_conversation_id`
- `title`
- `owner_id`
- `started_at`, `updated_at`
- unique `(source_tool, external_conversation_id)`

### `conversation_turns`

- `id`
- `conversation_id`
- `external_turn_id`
- `parent_turn_id`
- `sequence_number`
- `speaker_role`
- `content`
- `model_name`
- `created_at`
- `content_hash`

Use external turn IDs when available. Otherwise derive deterministic identity from conversation, sequence, speaker role, and content hash.

### `turn_feedback`

- `id`
- `turn_id`
- `feedback_type`: `edit`, `regenerate`, `accept`, or `rating`
- `value_json`
- `created_at`

### `rationale_statements`

- `id`
- `version_id`
- `statement_type`: `problem`, `intent`, `constraint`, `failed_attempt`, or `outcome`
- `statement`
- `original_statement`: immutable LLM output retained when reviewer edits
- `evidence_kind`: `observed` or `inferred`
- `confidence`: numeric value from 0 to 1
- `alternative_explanation`
- `review_status`: `pending`, `approved`, `edited`, or `rejected`
- `reviewer_id`
- `reviewed_at`
- `review_note`
- `created_at`

Citation join tables associate statements with source turns, asset versions, and optional Git commits. The existing `rationale` row remains a compact compatibility summary for current recommendation and onboarding code.

## Dual-rationale behavior

Logical statement contract:

```json
{
  "statement": "...",
  "statement_type": "intent",
  "evidence_kind": "observed",
  "confidence": 0.95,
  "source_turn_ids": [],
  "source_version_ids": [],
  "source_commit_ids": [],
  "alternative_explanation": null
}
```

### Observed rationale

When chat explicitly states why a prompt was written or changed, Featherless extracts the source span, normalizes wording, deduplicates repeated statements, and classifies it as problem, intent, constraint, failed attempt, or outcome. The stored statement cites the original turns.

### Inferred rationale

When chat is silent, Featherless may infer a hypothesis from:

- prompt before/after revisions;
- assistant responses;
- regenerate, edit, accept, and rating signals;
- asset version diffs;
- Git commit or diff only when explicitly linked to the conversation or asset version.

Inferred statements require confidence, citations, and an alternative explanation when ambiguity is material. They never overwrite observed evidence. Conflicts remain visible.

UI labels statements as `Explicit` or `AI-inferred`. Low-confidence text uses qualified wording such as “likely” rather than asserting a fact.

## Human review gate

Every LLM-produced rationale statement is first stored as `pending`, whether extracted from prompt history or inferred from prompt/code evidence. The review UI shows:

- proposed statement and statement type;
- `Explicit` or `AI-inferred` label;
- confidence and alternative explanation;
- cited conversation turns, asset-version diff, and linked code/commit evidence;
- before/after prompt revision when available.

Reviewer actions:

- **Approve:** retain statement unchanged and set `review_status=approved`.
- **Edit and approve:** preserve original LLM text in audit metadata, store reviewer text, set `review_status=edited`, and record reviewer attribution.
- **Reject:** retain record for audit/retraining feedback, set `review_status=rejected`, and exclude it from trusted retrieval.

For MVP, reviewer identity is the imported conversation/asset owner or the explicitly selected demo user. This provides attribution only; it is not an authorization system.

Only `approved` and `edited` statements update the compact `rationale` summary, contribute to Chroma's distilled asset document, affect recommendation scoring, or appear as established knowledge in onboarding. Pending statements may appear only inside the review queue. Rejected statements never influence retrieval or explanation.

When no reviewer is available, capture remains retry-safe and asset history remains stored, but rationale stays pending. This is not a pipeline failure: processing status and review status are separate.

### Codebase evidence boundary

Inference may use code only when Loomi has a bounded evidence reference, such as repository root plus captured paths, an asset-version diff, or an explicitly linked Git commit. The LLM does not scan an arbitrary organization codebase. Review UI cites file paths and commit IDs used by the inference. Missing links mean codebase evidence is omitted.

## Role-aware view

Role is personalization, not authorization. Featherless maps any role name to strict JSON:

```json
{
  "role": "Developer",
  "goals": [],
  "detail_level": "technical",
  "ranking_weights": {},
  "explanation_style": "...",
  "primary_actions": []
}
```

Validate keys, types, and bounded weights. Cache valid lenses by normalized role name. Invalid output or LLM failure uses a neutral Developer-like fallback.

Default role behavior:

- **Intern:** why-first explanation, glossary, usage steps, constraints, examples.
- **Developer:** full prompt, revisions, failed attempts, implementation context.
- **Tech Lead:** trade-offs, alternatives, confidence, reuse and downstream impact.
- **Manager:** outcome, owner, adoption, risk, and team impact; technical details collapsed by default.

All roles receive the same underlying evidence. Only ranking emphasis, explanation depth, vocabulary, and primary actions change.

## Recommendation integration

Keep Chroma-managed `all-MiniLM-L6-v2`. Index distilled asset title, current content, and compact rationale summary. Do not embed every raw turn for MVP.

Recommendation flow:

1. Current Chroma query retrieves candidates.
2. SQLite joins owner, usage, confidence, and current rationale.
3. Current semantic/confidence/usage score gains a bounded role-relevance term.
4. Existing `recommend(task_description, top_k)` remains valid. Role-aware behavior should use an additive optional parameter or a separate wrapper only after team contract review.

Role relevance must not overpower semantic match. A role changes ordering among relevant candidates, not turn irrelevant assets into top results.

## Onboarding integration

Onboarding loads asset versions, observed/inferred rationale statements, and citations. Featherless renders the same evidence according to the role lens.

Output should add:

- evidence labels;
- confidence for inferred claims;
- cited turn/version/commit identifiers;
- role-specific explanation and actions.

Post-validation removes citations that do not resolve to loaded evidence. Missing evidence returns an explicit limitation instead of invented rationale.

By default onboarding consumes only `approved` and `edited` rationale. A reviewer-facing preview may render pending rationale, clearly isolated from normal onboarding results.

## Import, safety, and retry

- Conversation import is manual and opt-in.
- Re-import uses deterministic upserts.
- Secret-like values are redacted before LLM calls and embedding.
- Raw conversation content remains in SQLite; Chroma contains distilled assets only.
- Malformed export items produce item-level diagnostics.
- LLM or parsing failure leaves source data pending for retry.
- Asset, version, summary rationale, statements, and citations persist transactionally.
- Review transitions use parameterized updates and record reviewer attribution; repeated approve/reject actions are idempotent.
- Chroma remains outside SQLite transaction; deterministic asset IDs make retry safe.
- Role-lens failure uses fallback and does not block recommendation or onboarding.

## Delivery UI

Streamlit adds:

- role selector/input;
- role-aware result-card fields and primary actions;
- rationale review queue with approve, edit-and-approve, and reject actions;
- onboarding explanation adjusted to role;
- `Explicit` and `AI-inferred` badges;
- expandable citations and confidence;
- prompt revision timeline using ordinary relational history, not a graph.

## Testing strategy

- ChatGPT and Claude export adapter fixtures.
- Idempotent re-import tests.
- Redaction tests before LLM and embedding boundaries.
- Mocked Featherless tests for observed extraction, inference, alternatives, and conflicts.
- Review state-machine tests for pending, approved, edited, and rejected statements.
- Trust-boundary tests proving pending/rejected rationale cannot affect Chroma, recommendation, or onboarding.
- Audit tests preserving original LLM output after reviewer edits.
- Citation validation requiring every displayed source to resolve in SQLite.
- Negative test proving unlinked Git commits never contribute to rationale.
- Role-lens schema, fallback, and cache tests.
- Same evidence across Intern, Developer, Tech Lead, and Manager: different emphasis, same facts.
- Ranking test ensuring role relevance cannot overwhelm semantic relevance.
- Existing Git capture, recommendation, and onboarding tests remain green.

## MVP rollout

1. Chat export schema, adapter, redaction, and idempotent import.
2. Distillation and pending observed/inferred rationale statements.
3. Human review queue and trusted-rationale promotion.
4. Role lens plus onboarding presentation.
5. Bounded role-aware recommendation scoring.
6. Streamlit role cards, evidence badges, and revision timeline.

Demo flow: import one conversation with prompt refinements, generate rationale from chat plus optionally linked code evidence, let the creator edit/approve it, distill a trusted reusable prompt, ask why it exists as Intern and Tech Lead, then show another employee receiving it through recommendation.

## Stack alignment

- SQLite through `db/client.py`
- Chroma with `sentence-transformers/all-MiniLM-L6-v2`
- Featherless OpenAI-compatible API with current GLM-5.2 default
- Streamlit
- Existing pytest suite
