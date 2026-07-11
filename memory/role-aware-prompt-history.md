# Role-Aware Prompt History Graph Memory

## 2026-07-11 — proposal approved

### Completed

- Reviewed current Git-first capture, SQLite/Chroma storage, recommendation, and onboarding code.
- Designed prompt-history-first architecture for ChatGPT/Claude exports.
- Designed materialized SQLite knowledge graph, role-aware view, bounded Graph Reasoner, and optional Git outcome evidence.
- Added dual rationale: explicit chat evidence is `observed`; missing rationale may be LLM-inferred with confidence, citations, and alternatives.
- Wrote approved design to `docs/superpowers/specs/2026-07-11-role-aware-prompt-history-graph-design.md`.

### Decisions

- Conversation history is primary evidence; Git is optional outcome evidence only when explicitly linked.
- Preserve raw conversations in SQLite; embed only distilled assets in Chroma.
- Use SQLite node/edge tables, not Neo4j.
- Role is personalization, not access control. LLM generates a validated lens with Developer-like fallback.
- LLM accesses bounded graph tools, not raw graph dumps or SQL.
- Observed and inferred rationale coexist; inference never overwrites explicit evidence.
- Store multi-statement evidence in additive `rationale_statements` plus citation joins; retain current `rationale` as compatibility summary.
- Keep current MiniLM, Featherless, Streamlit, and `db/client.py` contracts.

### Problems avoided

- Initial proposal overfit the existing Git adapter and missed prompt history as the central source. Architecture was revised before spec creation.
- Strict “do not infer” grounding conflicted with product intent. Replaced with labeled, cited, confidence-scored inference.
- Temporal Git correlation could create false causality. Git evidence now requires an explicit stored relation.

### Next steps

- User reviews written spec.
- If implementation is requested, create an implementation plan before code.
- First slice should cover export fixtures, adapter normalization, redaction, and idempotent conversation import.

## 2026-07-11 — scope reduced after design review

### Decision

- Removed materialized graph, Graph Reasoner, graph traversal, and PyVis from proposal.
- Kept two features only: role-aware personalization and LLM-enhanced prompt-history rationale.
- Retained minimal relational conversation, turn, feedback, rationale-statement, and citation tables.
- Prompt revision timeline uses relational history. No generic node/edge storage.
- Git remains optional evidence only when explicitly linked.

### Reason

- Full graph duplicated relational truth and added sync, typing, extraction, and test cost before multi-hop value was proven.
- Hackathon MVP needs explainable prompt rationale and role-specific reuse, not graph infrastructure.

### Current spec

- `docs/superpowers/specs/2026-07-11-role-aware-llm-rationale-design.md`

## 2026-07-11 — human rationale review added

### Decision

- Every LLM-produced rationale starts `pending`, including explicit extraction and inference from prompt history or bounded code evidence.
- Reviewer can approve, edit-and-approve, or reject with attribution and audit history.
- Only approved/edited rationale enters compact summary, Chroma document, recommendation scoring, and normal onboarding.
- Pending review is separate from capture processing failure.
- Codebase evidence must be bounded by captured paths, version diff, or explicit commit link; no arbitrary repository scan.

### Next step

- Implementation plan must include review state transitions, trusted-rationale promotion, Chroma refresh after approval, and negative tests for pending/rejected leakage.
