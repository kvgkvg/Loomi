"""Transactional prompt-history processing with pending human review."""

from __future__ import annotations

import hashlib
import json
import uuid

from capture_pipeline.rationale_statements import extract_rationale_statements
from db.client import get_pg_connection, get_vector_collection


def _id(kind: str, value: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"loomi-{kind}:{value}"))


def _failure(message: str) -> dict:
    return {"asset_id": None, "version_id": None, "statement_ids": [], "review_status": None, "error": message}


def _persisted(connection, event_id: str) -> dict:
    row = connection.execute(
        "SELECT processed_asset_version_id FROM raw_events WHERE id = ?", (event_id,)
    ).fetchone()
    version_id = row[0]
    asset_id = connection.execute("SELECT asset_id FROM asset_versions WHERE id = ?", (version_id,)).fetchone()[0]
    statement_ids = [r[0] for r in connection.execute("SELECT id FROM rationale_statements WHERE version_id = ? ORDER BY id", (version_id,))]
    return {"asset_id": asset_id, "version_id": version_id, "statement_ids": statement_ids, "review_status": "pending", "error": None}


def process_chat_event(raw_event_id: str) -> dict:
    connection = get_pg_connection()
    try:
        event = connection.execute("SELECT * FROM raw_events WHERE id = ?", (raw_event_id,)).fetchone()
        if event is None:
            return _failure("Raw event not found")
        if event["processed"] and event["processed_asset_version_id"]:
            return _persisted(connection, raw_event_id)
        signal = json.loads(event["raw_signal"] or "{}")
        turns = signal.get("turns")
        external_id = signal.get("external_conversation_id")
        if not isinstance(turns, list) or not isinstance(external_id, str):
            return _failure("Invalid chat event")

        connection.execute("BEGIN")
        conversation_id = _id("conversation", f"{event['source_tool']}:{external_id}")
        connection.execute(
            "INSERT INTO conversations (id, source_tool, external_conversation_id, title) VALUES (?, ?, ?, ?)",
            (conversation_id, event["source_tool"], external_id, event["title"]),
        )
        internal_turns = []
        external_to_internal = {}
        for sequence, turn in enumerate(turns, 1):
            turn_id = _id("turn", f"{conversation_id}:{turn.get('external_id') or sequence}")
            external_to_internal[turn.get("external_id")] = turn_id
            content = str(turn.get("content") or "")
            internal_turns.append({"id": turn_id, "role": turn.get("role"), "content": content})
            connection.execute(
                """
                INSERT INTO conversation_turns
                  (id, conversation_id, external_turn_id, sequence_number, speaker_role, content, model_name, created_at, content_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (turn_id, conversation_id, turn.get("external_id"), sequence, turn.get("role"), content, turn.get("model"), turn.get("created_at"), hashlib.sha256(content.encode()).hexdigest()),
            )
        for turn in turns:
            parent = external_to_internal.get(turn.get("parent_external_id"))
            current = external_to_internal.get(turn.get("external_id"))
            if parent and current:
                connection.execute("UPDATE conversation_turns SET parent_turn_id = ? WHERE id = ?", (parent, current))

        user_prompts = [turn["content"] for turn in internal_turns if turn["role"] == "user"]
        if not user_prompts:
            raise ValueError("conversation has no user prompt")
        asset_id = _id("asset", f"chat:{event['source_tool']}:{external_id}")
        version_id = _id("version", raw_event_id)
        connection.execute(
            "INSERT INTO assets (id, asset_key, type, title, source_tool) VALUES (?, ?, 'prompt', ?, ?)",
            (asset_id, f"chat:{event['source_tool']}:{external_id}", event["title"] or "Imported prompt", event["source_tool"]),
        )
        connection.execute(
            "INSERT INTO asset_versions (id, asset_id, raw_event_id, version_number, content, diff_summary) VALUES (?, ?, ?, 1, ?, ?)",
            (version_id, asset_id, raw_event_id, user_prompts[-1], "Distilled from prompt history"),
        )
        statements = extract_rationale_statements(internal_turns)
        statement_ids = []
        for index, statement in enumerate(statements):
            statement_id = _id("statement", f"{version_id}:{index}:{statement['statement']}")
            statement_ids.append(statement_id)
            connection.execute(
                """
                INSERT INTO rationale_statements
                  (id, version_id, statement_type, statement, original_statement, evidence_kind, confidence,
                   alternative_explanation, review_status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending')
                """,
                (statement_id, version_id, statement["statement_type"], statement["statement"], statement["original_statement"], statement["evidence_kind"], statement["confidence"], statement["alternative_explanation"]),
            )
            for turn_id in statement["source_turn_ids"]:
                connection.execute("INSERT INTO rationale_statement_turns (statement_id, turn_id) VALUES (?, ?)", (statement_id, turn_id))
        connection.execute("UPDATE assets SET current_version_id = ? WHERE id = ?", (version_id, asset_id))
        connection.execute("UPDATE raw_events SET processed = 1, processed_asset_version_id = ? WHERE id = ?", (version_id, raw_event_id))
        connection.commit()
        return {"asset_id": asset_id, "version_id": version_id, "statement_ids": statement_ids, "review_status": "pending", "error": None}
    except Exception:
        connection.rollback()
        return _failure("Chat pipeline processing failed")
    finally:
        connection.close()
