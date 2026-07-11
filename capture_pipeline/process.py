"""Transactional raw-event processing into versioned, searchable assets."""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from capture_pipeline.llm import extract_rationale
from db.client import get_pg_connection, get_vector_collection


def _resolve_user(connection, name: str | None, email: str | None) -> str | None:
    """Map a git author to a users row (create on first sight). Returns user id."""
    if not email:
        return None
    row = connection.execute(
        "SELECT id FROM users WHERE email = ?", (email,)
    ).fetchone()
    if row is not None:
        return row["id"]
    user_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"loomi-user:{email}"))
    connection.execute(
        "INSERT INTO users (id, name, email) VALUES (?, ?, ?)",
        (user_id, name or email, email),
    )
    return user_id


def _failure(message: str) -> dict:
    return {
        "asset_id": None,
        "version_id": None,
        "rationale": None,
        "embedded": False,
        "error": message,
    }


def _asset_identity(raw_signal: dict[str, Any]) -> str:
    repository = raw_signal.get("repository_root")
    paths = raw_signal.get("paths")
    if not isinstance(repository, str) or not repository:
        raise ValueError("Raw event lacks repository identity")
    if not isinstance(paths, list) or not paths or not all(
        isinstance(path, str) for path in paths
    ):
        raise ValueError("Raw event lacks captured paths")
    canonical = json.dumps(
        {"repository_root": repository, "paths": sorted(set(paths))},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _infer_asset_type(paths: list[str]) -> str:
    joined = " ".join(paths).lower()
    if "workflow" in joined:
        return "workflow"
    if "agent" in joined or "config" in joined:
        return "agent_config"
    return "prompt"


def _deserialize_rationale(row) -> dict:
    return {
        "problem": row["problem"],
        "failed_attempts": json.loads(row["failed_attempts"]),
        "constraints": json.loads(row["constraints"]),
        "confidence": row["confidence"],
    }


def _statement_id(version_id: str, index: int, statement: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"loomi-statement:{version_id}:{index}:{statement}"))


def _rationale_to_statements(rationale: dict) -> list[dict]:
    rows = [{
        "statement_type": "problem",
        "statement": rationale["problem"],
    }]
    rows.extend({"statement_type": "failed_attempt", "statement": item} for item in rationale["failed_attempts"])
    rows.extend({"statement_type": "constraint", "statement": item} for item in rationale["constraints"])
    return [
        {
            **row,
            "original_statement": row["statement"],
            "evidence_kind": "inferred",
            "confidence": 0.7,
            "alternative_explanation": None,
        }
        for row in rows
        if row["statement"]
    ]


def _pending_result(connection, version_id: str) -> dict:
    row = connection.execute(
        "SELECT asset_id FROM asset_versions WHERE id = ?", (version_id,)
    ).fetchone()
    statements = connection.execute(
        """
        SELECT id, statement_type, statement
        FROM rationale_statements
        WHERE version_id = ?
        ORDER BY CASE statement_type
          WHEN 'problem' THEN 0
          WHEN 'failed_attempt' THEN 1
          WHEN 'constraint' THEN 2
          ELSE 3
        END, id
        """,
        (version_id,),
    ).fetchall()
    rationale = {
        "problem": next((s["statement"] for s in statements if s["statement_type"] == "problem"), ""),
        "failed_attempts": [s["statement"] for s in statements if s["statement_type"] == "failed_attempt"],
        "constraints": [s["statement"] for s in statements if s["statement_type"] == "constraint"],
        "confidence": "auto",
    }
    return {
        "asset_id": row["asset_id"],
        "version_id": version_id,
        "rationale": rationale,
        "embedded": False,
        "draft_embedded": True,
        "review_status": "pending",
        "statement_ids": [s["id"] for s in statements],
    }


def _persisted_result(connection, version_id: str) -> dict:
    row = connection.execute(
        """
        SELECT av.asset_id, av.id AS version_id, r.problem, r.failed_attempts,
               r.constraints, r.confidence
        FROM asset_versions av
        JOIN rationale r ON r.version_id = av.id
        WHERE av.id = ?
        """,
        (version_id,),
    ).fetchone()
    if row is None:
        raise ValueError("Processed event points to incomplete version")
    return {
        "asset_id": row["asset_id"],
        "version_id": row["version_id"],
        "rationale": _deserialize_rationale(row),
        "embedded": True,
    }


def process_raw_event(raw_event_id: str) -> dict:
    """Version, enrich, embed, and finalize one raw event without raising failures."""
    connection = get_pg_connection()
    try:
        event = connection.execute(
            "SELECT * FROM raw_events WHERE id = ?", (raw_event_id,)
        ).fetchone()
        if event is None:
            return _failure("Raw event not found")
        if event["processed"] and event["processed_asset_version_id"]:
            return _persisted_result(connection, event["processed_asset_version_id"])
        if event["processed_asset_version_id"]:
            return _pending_result(connection, event["processed_asset_version_id"])

        connection.execute("BEGIN")
        raw_signal = json.loads(event["raw_signal"] or "{}")
        asset_key = _asset_identity(raw_signal)
        paths = raw_signal["paths"]
        editor_id = _resolve_user(
            connection,
            raw_signal.get("author_name"),
            raw_signal.get("author_email"),
        )
        asset = connection.execute(
            "SELECT id FROM assets WHERE asset_key = ?", (asset_key,)
        ).fetchone()
        if asset is None:
            asset_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"loomi-asset:{asset_key}"))
            connection.execute(
                """
                INSERT INTO assets (id, asset_key, type, title, source_tool, owner_id)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    asset_id,
                    asset_key,
                    _infer_asset_type(paths),
                    event["title"] or "Untitled Git knowledge",
                    event["source_tool"],
                    editor_id,
                ),
            )
        else:
            asset_id = asset["id"]

        version_number = connection.execute(
            "SELECT COALESCE(MAX(version_number), 0) + 1 FROM asset_versions WHERE asset_id = ?",
            (asset_id,),
        ).fetchone()[0]
        version_id = str(
            uuid.uuid5(uuid.NAMESPACE_URL, f"loomi-version:{raw_event_id}")
        )
        connection.execute(
            """
            INSERT INTO asset_versions
                (id, asset_id, raw_event_id, version_number, content, diff_summary, editor_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                version_id,
                asset_id,
                raw_event_id,
                version_number,
                event["content"],
                raw_signal.get("diff", ""),
                editor_id,
            ),
        )

        rationale = extract_rationale(event["content"], event["raw_signal"] or "")
        statement_ids = []
        for index, statement in enumerate(_rationale_to_statements(rationale)):
            statement_id = _statement_id(version_id, index, statement["statement"])
            statement_ids.append(statement_id)
            connection.execute(
                """
                INSERT INTO rationale_statements
                  (id, version_id, statement_type, statement, original_statement, evidence_kind,
                   confidence, alternative_explanation, review_status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending')
                """,
                (
                    statement_id,
                    version_id,
                    statement["statement_type"],
                    statement["statement"],
                    statement["original_statement"],
                    statement["evidence_kind"],
                    statement["confidence"],
                    statement["alternative_explanation"],
                ),
            )
            connection.execute(
                "INSERT INTO rationale_statement_versions (statement_id, version_id) VALUES (?, ?)",
                (statement_id, version_id),
            )
            connection.execute(
                "INSERT INTO rationale_statement_commits (statement_id, raw_event_id) VALUES (?, ?)",
                (statement_id, raw_event_id),
            )

        document = f"{event['content']}\n\nProblem: {rationale['problem']}"
        # Precompute a draft vector under a non-asset id. Recommend joins by
        # asset_id, so pending rationale stays out of normal search results.
        get_vector_collection().upsert(
            ids=[f"draft:{version_id}"],
            documents=[document],
            metadatas=[
                {
                    "asset_id": asset_id,
                    "version_id": version_id,
                    "source_tool": event["source_tool"],
                    "review_status": "pending",
                }
            ],
        )
        connection.execute(
            """
            UPDATE raw_events
            SET processed = 0, processed_asset_version_id = ?
            WHERE id = ?
            """,
            (version_id, raw_event_id),
        )
        connection.commit()
        return {
            "asset_id": asset_id,
            "version_id": version_id,
            "rationale": rationale,
            "embedded": False,
            "draft_embedded": True,
            "review_status": "pending",
            "statement_ids": statement_ids,
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        connection.rollback()
        try:
            connection.execute(
                "UPDATE raw_events SET processed = 0 WHERE id = ?", (raw_event_id,)
            )
            connection.commit()
        except Exception:
            connection.rollback()
        return _failure("Pipeline processing failed")
    finally:
        connection.close()
