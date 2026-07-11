"""Normalize ChatGPT/Claude exports into retryable canonical raw events."""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

from db.client import get_pg_connection


class ChatExportError(ValueError):
    pass


_SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"(?i)\b(api[_ -]?key|token|password)\s*[:=]\s*\S+"),
)


def redact_secrets(text: str) -> str:
    result = text
    for pattern in _SECRET_PATTERNS:
        result = pattern.sub(
            lambda match: (
                f"{match.group(1)}=[REDACTED]" if match.lastindex else "[REDACTED]"
            ),
            result,
        )
    return result


def _content(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        parts = value.get("parts")
        if isinstance(parts, list):
            return "\n".join(part for part in parts if isinstance(part, str))
        text = value.get("text")
        if isinstance(text, str):
            return text
    return ""


def _chatgpt(payload: dict) -> tuple[str, str, list[dict]]:
    external_id = payload.get("id") or payload.get("conversation_id")
    mapping = payload.get("mapping")
    if not isinstance(external_id, str) or not isinstance(mapping, dict):
        raise ChatExportError("invalid ChatGPT export")
    turns = []
    for key, node in mapping.items():
        if not isinstance(node, dict) or not isinstance(node.get("message"), dict):
            continue
        message = node["message"]
        role = ((message.get("author") or {}).get("role"))
        text = _content(message.get("content"))
        if role not in {"user", "assistant", "system", "tool"} or not text:
            continue
        turns.append(
            {
                "external_id": str(node.get("id") or key),
                "parent_external_id": node.get("parent"),
                "role": role,
                "content": redact_secrets(text),
                "model": ((message.get("metadata") or {}).get("model_slug")),
                "created_at": message.get("create_time"),
            }
        )
    turns.sort(key=lambda turn: (turn["created_at"] is None, turn["created_at"] or 0))
    return external_id, str(payload.get("title") or "Imported ChatGPT conversation"), turns


def _claude(payload: dict) -> tuple[str, str, list[dict]]:
    external_id = payload.get("uuid") or payload.get("id")
    messages = payload.get("chat_messages") or payload.get("messages")
    if not isinstance(external_id, str) or not isinstance(messages, list):
        raise ChatExportError("invalid Claude export")
    turns = []
    previous = None
    for message in messages:
        if not isinstance(message, dict):
            continue
        external_turn_id = message.get("uuid") or message.get("id")
        sender = message.get("sender") or message.get("role")
        role = "user" if sender in {"human", "user"} else sender
        text = _content(message.get("text") or message.get("content"))
        if not isinstance(external_turn_id, str) or role not in {"user", "assistant", "system", "tool"} or not text:
            continue
        turns.append(
            {
                "external_id": external_turn_id,
                "parent_external_id": previous,
                "role": role,
                "content": redact_secrets(text),
                "model": message.get("model"),
                "created_at": message.get("created_at"),
            }
        )
        previous = external_turn_id
    return external_id, str(payload.get("name") or payload.get("title") or "Imported Claude conversation"), turns


def normalize_chat_export(payload: dict, source_tool: str) -> dict:
    if not isinstance(payload, dict):
        raise ChatExportError("chat export must be an object")
    if source_tool == "chatgpt":
        external_id, title, turns = _chatgpt(payload)
    elif source_tool == "claude":
        external_id, title, turns = _claude(payload)
    else:
        raise ChatExportError("unsupported chat source")
    if not turns:
        raise ChatExportError("chat export has no supported turns")
    return {
        "source_tool": source_tool,
        "external_conversation_id": external_id,
        "title": title,
        "turns": turns,
    }


def capture_chat_export(payload: dict, source_tool: str) -> dict:
    normalized = normalize_chat_export(payload, source_tool)
    identity = f"{source_tool}:{normalized['external_conversation_id']}"
    event_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"loomi-chat-event:{identity}"))
    content = "\n\n".join(
        f"{turn['role']}: {turn['content']}" for turn in normalized["turns"]
    )
    signal = json.dumps(normalized, ensure_ascii=False, sort_keys=True)
    connection = get_pg_connection()
    try:
        existing = connection.execute(
            "SELECT raw_signal FROM raw_events WHERE id = ?", (event_id,)
        ).fetchone()
        if existing is None:
            connection.execute(
                """
                INSERT INTO raw_events (id, source_tool, title, content, raw_signal, processed)
                VALUES (?, ?, ?, ?, ?, 0)
                """,
                (event_id, source_tool, normalized["title"], content, signal),
            )
            connection.commit()
        elif existing["raw_signal"] != signal:
            # Conversation changed since last capture: refresh payload and
            # reopen the event so the pipeline distills a new version.
            connection.execute(
                """
                UPDATE raw_events
                SET title = ?, content = ?, raw_signal = ?, processed = 0
                WHERE id = ?
                """,
                (normalized["title"], content, signal, event_id),
            )
            connection.commit()
    finally:
        connection.close()
    return {"raw_event_id": event_id, "source_tool": source_tool, "turn_count": len(normalized["turns"])}
