"""Featherless boundary for cited observed/inferred rationale statements."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Callable

from adapters.chat_adapter import redact_secrets
from capture_pipeline.llm import FEATHERLESS_BASE_URL, FEATHERLESS_MODEL


class RationaleStatementsError(RuntimeError):
    pass


_TYPES = {"problem", "intent", "constraint", "failed_attempt", "outcome"}
_KINDS = {"observed", "inferred"}
_SYSTEM = """Extract and enhance rationale from prompt history. Return JSON object with a statements array.
Each statement requires statement_type, statement, evidence_kind (observed or inferred), confidence 0..1,
source_turn_ids, source_version_ids, source_commit_ids, and alternative_explanation. Cite only supplied IDs.
statement_type MUST be exactly one of: problem, intent, constraint, failed_attempt, outcome — no other value.
evidence_kind MUST be exactly observed or inferred. Observed means explicit text. Inferred means a supported
hypothesis. source_turn_ids may only contain id values copied verbatim from the supplied turns; when no
version or commit IDs are supplied, source_version_ids and source_commit_ids MUST be empty arrays. No markdown."""


def _strip_fence(text: str) -> str:
    match = re.fullmatch(r"\s*```(?:json)?\s*\n?(.*?)\n?```\s*", text, re.DOTALL)
    return match.group(1).strip() if match else text.strip()


def _string_list(value: Any, name: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise RationaleStatementsError(f"{name} must be a string list")
    return value


def _validate(payload: Any, allowed: dict[str, set[str]]) -> list[dict]:
    if not isinstance(payload, dict) or not isinstance(payload.get("statements"), list):
        raise RationaleStatementsError("response must contain statements")
    output = []
    for item in payload["statements"]:
        if not isinstance(item, dict):
            raise RationaleStatementsError("statement must be an object")
        statement_type = item.get("statement_type")
        statement = item.get("statement")
        evidence_kind = item.get("evidence_kind")
        confidence = item.get("confidence")
        if statement_type not in _TYPES or evidence_kind not in _KINDS:
            raise RationaleStatementsError("invalid statement classification")
        if not isinstance(statement, str) or not statement.strip():
            raise RationaleStatementsError("statement text is required")
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            raise RationaleStatementsError("confidence must be between 0 and 1")
        turn_ids = _string_list(item.get("source_turn_ids"), "source_turn_ids")
        version_ids = _string_list(item.get("source_version_ids"), "source_version_ids")
        commit_ids = _string_list(item.get("source_commit_ids"), "source_commit_ids")
        if not set(turn_ids) <= allowed["turns"] or not set(version_ids) <= allowed["versions"] or not set(commit_ids) <= allowed["commits"]:
            raise RationaleStatementsError("statement cites unavailable evidence")
        alternative = item.get("alternative_explanation")
        if alternative is not None and not isinstance(alternative, str):
            raise RationaleStatementsError("alternative explanation must be text")
        output.append(
            {
                "statement_type": statement_type,
                "statement": statement.strip(),
                "original_statement": statement.strip(),
                "evidence_kind": evidence_kind,
                "confidence": float(confidence),
                "source_turn_ids": turn_ids,
                "source_version_ids": version_ids,
                "source_commit_ids": commit_ids,
                "alternative_explanation": alternative,
                "review_status": "pending",
            }
        )
    return output


def extract_rationale_statements(
    turns: list[dict],
    code_evidence: dict | None = None,
    *,
    client_factory: Callable[..., Any] | None = None,
) -> list[dict]:
    api_key = os.getenv("FEATHERLESS_API_KEY")
    if not api_key:
        raise RationaleStatementsError("FEATHERLESS_API_KEY is not set")
    evidence = code_evidence or {}
    safe_turns = [
        {**turn, "content": redact_secrets(str(turn.get("content", "")))} for turn in turns
    ]
    allowed = {
        "turns": {str(turn["id"]) for turn in safe_turns if "id" in turn},
        "versions": {str(value) for value in evidence.get("version_ids", [])},
        "commits": {str(value) for value in evidence.get("commit_ids", [])},
    }
    if client_factory is None:
        from openai import OpenAI

        client_factory = OpenAI
    client = client_factory(base_url=FEATHERLESS_BASE_URL, api_key=api_key)
    try:
        response = client.chat.completions.create(
            model=FEATHERLESS_MODEL,
            temperature=0.1,
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": json.dumps({"turns": safe_turns, "code_evidence": evidence}, ensure_ascii=False)},
            ],
        )
        text = response.choices[0].message.content
        payload = json.loads(_strip_fence(text))
    except RationaleStatementsError:
        raise
    except Exception as exc:
        raise RationaleStatementsError("rationale statement request failed") from exc
    return _validate(payload, allowed)
