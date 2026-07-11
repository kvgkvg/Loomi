# Role-Aware Prompt History Graph — Design Proposal

## Status

Approved proposal. Documentation only; no implementation included.

## Problem

Loomi currently captures Git changes and turns them into versioned AI assets. The intended organizational memory is broader: preserve how employees create and refine prompts in ChatGPT or Claude, distill reusable prompt assets from that history, explain why each prompt exists, and present the same evidence differently for Intern, Developer, Tech Lead, and Manager roles.

Git remains useful, but only as optional downstream outcome evidence. Conversation history is the primary evidence source.

## Goals

- Import ChatGPT and Claude conversation exports.
- Preserve conversation turns, prompt revisions, regenerations, feedback, and attribution.
- Distill reusable prompt assets and revisions from conversation history.
- Materialize typed relations for prompt lineage, intent, constraints, attempts, dependencies, and outcomes.
- Let an LLM fetch bounded graph context and explain why a prompt was written.
- Support both explicit rationale from chat and AI-inferred rationale when chat is silent.
- Personalize recommendation, cards, graph focus, and onboarding explanation by role.
- Reuse current SQLite, Chroma, Featherless, MiniLM, and Streamlit stack.

## Non-goals

- RBAC or permission filtering.
- Neo4j or another graph database.
- Background scraping of private conversations.
- Full retention, legal hold, PII compliance, or governance platform.
- Cross-encoder reranking, LangChain, or graph analytics frameworks.

## User experience

User imports a ChatGPT or Claude export, then selects or enters an organizational role and task. Loomi recommends distilled prompt assets, shows a role-appropriate card, renders a focused lineage/dependency graph, and answers “why was this prompt written?” with cited evidence.

Role changes presentation and relevance, not underlying facts or visibility:

- **Intern:** why-first explanation, glossary, safe usage steps, constraints, examples.
- **Developer:** full prompt, revisions, failed attempts, implementation context, dependencies.
- **Tech Lead:** trade-offs, alternatives, confidence, impact radius, reusable patterns.
- **Manager:** outcome, owner, adoption, risk, and team impact; raw technical detail collapsed by default.

## Architecture

```text
ChatGPT / Claude export
  -> chat adapter
  -> canonical raw event
  -> conversations + conversation_turns + turn_feedback
  -> rationale extraction and prompt distillation
  -> assets + asset_versions + rationale
  -> graph node/edge materialization
  -> Chroma index of distilled assets

Optional Git event
  -> existing Git adapter/capture
  -> explicit link to prompt turn/session/version
  -> graph outcome evidence

Role + task + selected asset
  -> role lens
  -> Chroma candidate retrieval
  -> graph feature/context retrieval
  -> role-aware reranking and Graph Reasoner
  -> Streamlit cards + explanation + graph panel
```

New module boundaries:

- `adapters/chat_adapter.py`: normalize ChatGPT/Claude exports into canonical conversation events.
- `role_lens/`: convert a role name into a validated structured viewing policy.
- `graphify/`: extract, validate, persist, and query graph nodes and edges.
- `graphify/reasoner.py`: tool-driven LLM reasoning over bounded graph context.
- Existing `recommend/`, `onboarding/`, and future `delivery/` consume these modules without owning storage connections.

All storage access continues through `db/client.py`.

## Storage model

Keep existing asset/version/rationale tables. Add:

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

Use external turn IDs when available. Fallback identity uses conversation ID, sequence, speaker role, and content hash.

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
- `evidence_kind`: `observed` or `inferred`
- `confidence`: numeric value from 0 to 1
- `alternative_explanation`
- `created_at`

This additive table holds multiple cited statements per version. The existing `rationale` row remains the compact current-version summary used by current recommendation and onboarding contracts. Graph extraction projects `rationale_statements` into typed nodes and edges.

Statement citations use join tables `rationale_statement_turns`, `rationale_statement_versions`, and `rationale_statement_commits`. Join rows are the source of truth; the JSON output shown below is the API projection.

### `graph_nodes`

- `id`
- `node_type`
- `ref_table`
- `ref_id`
- `label`
- `properties_json`
- `created_at`

Initial node types: `CONVERSATION`, `TURN`, `INTENT`, `ATTEMPT`, `CONSTRAINT`, `OUTCOME`, `ASSET`, `VERSION`, `USER`, `GIT_COMMIT`.

### `graph_edges`

- `id`
- `source_node_id`
- `target_node_id`
- `edge_type`
- `evidence_version_id`
- `confidence`
- `properties_json`
- `created_at`

Initial edge types: `HAS_TURN`, `RESPONDS_TO`, `REFINES`, `EXPRESSES_INTENT`, `FAILED_BECAUSE`, `SATISFIED_BY`, `DISTILLED_INTO`, `HAS_VERSION`, `CONSTRAINED_BY`, `USES_PROMPT`, `CALLS_AGENT`, `PART_OF_WORKFLOW`, `DEPENDS_ON`, and `PRODUCED_CHANGE`.

Node and edge IDs must be deterministic so re-import and retry are idempotent.

## Dual-rationale model

Every rationale statement has this logical shape:

```json
{
  "statement": "...",
  "kind": "observed | inferred",
  "confidence": 0.0,
  "source_turn_ids": [],
  "source_version_ids": [],
  "source_commit_ids": [],
  "alternative_explanation": null
}
```

### Observed rationale

When chat explicitly states a problem, intent, constraint, or failed attempt, the LLM extracts the supporting span, normalizes it, deduplicates it, and classifies it. It is stored as `observed` with direct turn citations.

### Inferred rationale

When chat is silent, the LLM may infer a hypothesis from prompt before/after revisions, assistant responses, regenerations, acceptance signals, asset diffs, and explicitly linked Git diffs or outcomes. It is stored as `inferred`, with confidence, citations, and an alternative explanation when ambiguity is material.

Observed and inferred statements can coexist. Inference fills gaps and never overwrites observed evidence. Contradictions remain visible and are flagged rather than silently merged. UI wording must distinguish `Explicit` from `AI-inferred`.

## Graph Reasoner

The LLM does not receive a raw graph dump and does not write SQL. It receives tool contracts that return bounded, typed, cited subgraphs:

- `get_prompt_lineage(asset_id, version_id)`
- `get_related_turns(node_id, edge_types, max_hops=2)`
- `get_constraints_and_attempts(node_id)`
- `get_linked_git_outcomes(node_id)`

The default maximum traversal is two hops. Role lens selects relevant edge types and detail level but cannot change facts.

Reasoner output:

```json
{
  "reason": "...",
  "intent": "...",
  "key_constraints": [],
  "failed_attempts": [],
  "change_outcomes": [],
  "confidence": 0.0,
  "cited_node_ids": [],
  "cited_turn_ids": [],
  "cited_commit_ids": []
}
```

Post-validation removes unknown citations. If evidence is too weak, output says so. Git evidence is used only through an explicit stored relation; temporal proximity alone cannot create a `PRODUCED_CHANGE` fact.

## Role lens

Role names are not limited to four hard-coded values. Featherless GLM-5.2 maps a role name to strict JSON:

```json
{
  "role": "Developer",
  "goals": [],
  "detail_level": "technical",
  "graph_focus": [],
  "ranking_weights": {},
  "explanation_style": "...",
  "primary_actions": []
}
```

Validate keys, types, allowed graph edge types, and bounded ranking weights. Cache valid lenses by normalized role name for the process lifetime. Invalid output or LLM failure uses a neutral Developer-like fallback.

## Recommendation and onboarding

Keep current Chroma embedding behavior and `all-MiniLM-L6-v2`. Index distilled asset title, current content, and rationale problem; do not index every raw conversation turn for MVP.

Recommendation flow:

1. Chroma retrieves semantic candidates.
2. SQLite joins owner, usage, rationale, and graph-derived features.
3. Existing semantic/confidence/usage score is combined with bounded role relevance.
4. Results retain the existing public fields; role-aware extensions require an additive contract rather than silently breaking `recommend()`.

Onboarding loads evidence and Graph Reasoner output, then renders it according to role lens. All citations are checked against stored turns, versions, nodes, and commits.

## Capture, transaction, and retry behavior

- Manual export import is opt-in; no background scraping.
- Re-import performs deterministic upserts.
- Secret-like values are redacted before LLM calls and embedding.
- Raw turns remain in SQLite; Chroma receives only distilled knowledge.
- Parse failure rejects malformed items with item-level diagnostics.
- Distillation or graph extraction failure leaves source data pending for retry.
- Relational asset, rationale, and graph persistence is transactional.
- Chroma remains outside the SQLite transaction; deterministic IDs make vector upsert retry-safe.
- Graph query failure falls back to current semantic recommendations and marks graph explanation unavailable.
- Reasoner failure returns deterministic lineage without generated rationale.
- Role-lens failure uses the neutral fallback.

## Delivery UI

Streamlit remains the delivery stack. One chat screen contains:

- role input/selector;
- task or question input;
- role-aware recommendation cards;
- explanation with `Explicit` and `AI-inferred` badges;
- confidence and source citations;
- PyVis embedded graph panel focused by role;
- controls to expand one-hop or two-hop evidence.

PyVis is a rendering dependency only. Graph traversal and truth remain in SQLite.

## Testing strategy

- Adapter fixtures for representative ChatGPT and Claude exports.
- Re-import and deterministic graph-upsert idempotency tests.
- Pure validation tests for role lenses, graph nodes/edges, and scoring.
- Transaction rollback and retry tests for partial failure.
- Mocked Featherless contract tests for observed extraction, inference, and alternatives.
- Grounding tests requiring every rendered citation to resolve in SQLite.
- Negative test proving an unlinked Git commit never appears as evidence.
- Role test: identical underlying evidence for four roles, with different ranking emphasis, graph focus, and explanation depth.
- End-to-end demo: refinement conversation -> distilled prompt -> optional linked commit -> role-aware “why?” -> cross-person recommendation.

## MVP rollout

1. Chat export schema, adapter, redaction, and idempotent import.
2. Distillation, dual-rationale extraction, graph schema, and materialization.
3. Bounded Graph Reasoner tools and grounded output validation.
4. Role lens integration into recommendation and onboarding.
5. Streamlit role-aware cards and PyVis graph panel.

Demo data needs one conversation with at least two prompt refinements, one accepted result, one distilled prompt with at least two versions, and one explicitly linked Git outcome.

## Stack alignment

- SQLite through `db/client.py`
- Chroma with `sentence-transformers/all-MiniLM-L6-v2`
- Featherless OpenAI-compatible API with current GLM-5.2 default
- Streamlit
- PyVis for visualization
- Python stdlib JSON/dataclasses plus existing pytest suite
