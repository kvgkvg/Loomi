"""CI-style intent review for user prompts from any chat environment.

Every submitted prompt runs three checks, each producing
{name, status, detail} with status pass | fail | action_required | error:

- policy_secrets     deterministic: credentials/API keys in the prompt
- reuse_available    Chroma: the org already has knowledge matching this intent
- intent_clarity     LLM: extracted {intent, confidence}; low confidence fails

Every review lands 'pending' and waits for a human approve/reject
(resolve_intent_review) — the checks inform the reviewer's decision. Set
INTENT_CI_AUTO_PASS=1 to let all-green reviews skip the gate as 'passed'.
LLM failure degrades to an 'error' check, never an exception (pipeline rule).
"""

from __future__ import annotations

import json
import os
import uuid
from typing import Any, Callable

from adapters.chat_adapter import _SECRET_PATTERNS, redact_secrets
from capture_pipeline.llm import FEATHERLESS_BASE_URL, FEATHERLESS_MODEL, _strip_json_fence
from db.client import get_pg_connection
from recommend.engine import recommend

REUSE_THRESHOLD = 0.45  # same bar the composer suggestion uses
CLARITY_THRESHOLD = 0.6
MAX_HISTORY_ITEMS = 20
MAX_HISTORY_ITEM_CHARS = 1000

_INTENT_SYSTEM = """Classify the intent of one user prompt sent to an AI assistant.
Return exactly one JSON object: {"intent": <one imperative sentence stating what the user wants>,
"confidence": <0..1, how unambiguous the request is>}. No markdown."""


def _extract_intent(prompt: str, *, client_factory: Callable[..., Any] | None = None) -> dict:
    api_key = os.getenv("FEATHERLESS_API_KEY")
    if not api_key:
        raise RuntimeError("FEATHERLESS_API_KEY is not set")
    if client_factory is None:
        from openai import OpenAI

        client_factory = OpenAI
    client = client_factory(base_url=FEATHERLESS_BASE_URL, api_key=api_key)
    response = client.chat.completions.create(
        model=FEATHERLESS_MODEL,
        temperature=0.1,
        messages=[
            {"role": "system", "content": _INTENT_SYSTEM},
            {"role": "user", "content": redact_secrets(prompt)},
        ],
    )
    payload = json.loads(_strip_json_fence(response.choices[0].message.content))
    intent = payload.get("intent")
    confidence = payload.get("confidence")
    if not isinstance(intent, str) or not intent.strip():
        raise ValueError("intent must be a non-empty string")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
        raise ValueError("confidence must be within 0..1")
    return {"intent": intent.strip(), "confidence": float(confidence)}


def _check_policy_secrets(prompt: str) -> dict:
    hits = [pattern.pattern for pattern in _SECRET_PATTERNS if pattern.search(prompt)]
    if hits:
        return {
            "name": "policy_secrets",
            "status": "fail",
            "detail": "prompt appears to contain a credential or API key",
        }
    return {"name": "policy_secrets", "status": "pass", "detail": "no credentials detected"}


def _check_reuse_available(prompt: str) -> dict:
    try:
        results = recommend(prompt, top_k=1)
    except Exception as exc:
        return {"name": "reuse_available", "status": "error", "detail": f"search failed: {exc}"}
    if results and results[0]["score"] >= REUSE_THRESHOLD:
        best = results[0]
        return {
            "name": "reuse_available",
            "status": "action_required",
            "detail": f"existing asset matches ({best['score']:.2f}): {best['title']}",
            "asset_id": best["asset_id"],
        }
    return {"name": "reuse_available", "status": "pass", "detail": "no overlapping org knowledge"}


def _check_intent_clarity(prompt: str, *, client_factory: Callable[..., Any] | None = None) -> tuple[dict, str | None]:
    try:
        extracted = _extract_intent(prompt, client_factory=client_factory)
    except Exception as exc:
        return (
            {"name": "intent_clarity", "status": "error", "detail": f"intent extraction failed: {exc}"},
            None,
        )
    status = "pass" if extracted["confidence"] >= CLARITY_THRESHOLD else "fail"
    detail = f"confidence {extracted['confidence']:.2f}: {extracted['intent']}"
    return {"name": "intent_clarity", "status": status, "detail": detail}, extracted["intent"]


def _normalize_chat_history(chat_history: list[str] | None) -> list[str]:
    if not chat_history:
        return []
    cleaned: list[str] = []
    for item in chat_history:
        if not isinstance(item, str):
            continue
        text = item.strip()
        if not text:
            continue
        cleaned.append(redact_secrets(text[:MAX_HISTORY_ITEM_CHARS]))
    return cleaned[-MAX_HISTORY_ITEMS:]


def _ensure_chat_history_column(connection) -> None:
    # Lightweight runtime migration so old DBs can store chat history.
    try:
        cols = connection.execute("PRAGMA table_info(intent_reviews)").fetchall()
        if cols and not any(row["name"] == "chat_history" for row in cols):
            connection.execute("ALTER TABLE intent_reviews ADD COLUMN chat_history TEXT")
            connection.commit()
        return
    except Exception:
        pass

    try:
        row = connection.execute(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_name = 'intent_reviews' AND column_name = 'chat_history'
            """
        ).fetchone()
        if row is None:
            connection.execute("ALTER TABLE intent_reviews ADD COLUMN chat_history JSONB")
            connection.commit()
    except Exception:
        # Keep the pipeline resilient; callers can still continue without history.
        pass


def run_checks(prompt: str, *, client_factory: Callable[..., Any] | None = None) -> tuple[list[dict], str, str | None]:
    """Run all checks. Returns (checks, overall_status, intent)."""
    checks = [_check_policy_secrets(prompt), _check_reuse_available(prompt)]
    clarity, intent = _check_intent_clarity(prompt, client_factory=client_factory)
    checks.append(clarity)
    overall = "passed" if all(check["status"] == "pass" for check in checks) else "pending"
    return checks, overall, intent


def create_intent_review(
    prompt: str,
    source_env: str,
    user_name: str | None = None,
    chat_history: list[str] | None = None,
    *,
    client_factory: Callable[..., Any] | None = None,
) -> dict:
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt must be a non-empty string")
    if not isinstance(source_env, str) or not source_env.strip():
        raise ValueError("source_env must be a non-empty string")

    checks, status, intent = run_checks(prompt.strip(), client_factory=client_factory)
    sanitized_history = _normalize_chat_history(chat_history)
    # Default flow: the user always picks approve/reject; green checks only
    # auto-pass when explicitly opted in.
    if status == "passed" and os.getenv("INTENT_CI_AUTO_PASS") != "1":
        status = "pending"
    review_id = str(uuid.uuid4())
    connection = get_pg_connection()
    try:
        _ensure_chat_history_column(connection)
        connection.execute(
            """
            INSERT INTO intent_reviews (id, prompt, source_env, user_name, intent, checks, status, chat_history)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                review_id,
                redact_secrets(prompt.strip()),
                source_env.strip(),
                user_name,
                intent,
                json.dumps(checks, ensure_ascii=False),
                status,
                json.dumps(sanitized_history, ensure_ascii=False),
            ),
        )
        connection.commit()
    finally:
        connection.close()
    return {
        "id": review_id,
        "prompt": redact_secrets(prompt.strip()),
        "source_env": source_env.strip(),
        "user_name": user_name,
        "intent": intent,
        "chat_history": sanitized_history,
        "checks": checks,
        "status": status,
    }


def _row_to_review(row) -> dict:
    checks = row["checks"]
    if isinstance(checks, str):
        try:
            checks = json.loads(checks)
        except json.JSONDecodeError:
            checks = []
    chat_history = row["chat_history"] if "chat_history" in row.keys() else None
    if isinstance(chat_history, str):
        try:
            chat_history = json.loads(chat_history)
        except json.JSONDecodeError:
            chat_history = []
    if not isinstance(chat_history, list):
        chat_history = []

    return {
        "id": row["id"],
        "prompt": row["prompt"],
        "source_env": row["source_env"],
        "user_name": row["user_name"],
        "intent": row["intent"],
        "chat_history": [item for item in chat_history if isinstance(item, str)],
        "checks": checks or [],
        "status": row["status"],
        "reviewer": row["reviewer"],
        "created_at": str(row["created_at"]) if row["created_at"] else None,
    }


def list_intent_reviews(limit: int = 20) -> list[dict]:
    connection = get_pg_connection()
    try:
        _ensure_chat_history_column(connection)
        rows = connection.execute(
            """
            SELECT id, prompt, source_env, user_name, intent, chat_history, checks, status, reviewer, created_at
            FROM intent_reviews ORDER BY created_at DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [_row_to_review(row) for row in rows]
    finally:
        connection.close()


def resolve_intent_review(review_id: str, action: str, reviewer: str | None = None) -> dict:
    if action not in {"approve", "reject"}:
        raise ValueError("action must be approve or reject")
    target = "approved" if action == "approve" else "rejected"
    connection = get_pg_connection()
    try:
        row = connection.execute(
            "SELECT status FROM intent_reviews WHERE id = ?", (review_id,)
        ).fetchone()
        if row is None:
            raise ValueError("intent review not found")
        if row["status"] not in {"pending", "passed"}:
            raise ValueError("intent review is already resolved")
        connection.execute(
            """
            UPDATE intent_reviews
            SET status = ?, reviewer = ?, resolved_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (target, reviewer, review_id),
        )
        connection.commit()
        return {"id": review_id, "status": target, "reviewer": reviewer}
    finally:
        connection.close()
