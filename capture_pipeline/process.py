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
        connection.execute(
            """
            INSERT INTO rationale
                (id, version_id, problem, failed_attempts, constraints, confidence)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid5(uuid.NAMESPACE_URL, f"loomi-rationale:{version_id}")),
                version_id,
                rationale["problem"],
                json.dumps(rationale["failed_attempts"], ensure_ascii=False),
                json.dumps(rationale["constraints"], ensure_ascii=False),
                rationale["confidence"],
            ),
        )

        document = f"{event['content']}\n\nProblem: {rationale['problem']}"
        # Vector id = asset_id (one vector per asset, latest version) so the
        # recommend engine can join hits[ids] -> assets.id directly. Chroma
        # embeds the document with its default function (team's shared model).
        get_vector_collection().upsert(
            ids=[asset_id],
            documents=[document],
            metadatas=[
                {
                    "asset_id": asset_id,
                    "version_id": version_id,
                    "source_tool": event["source_tool"],
                }
            ],
        )
        connection.execute(
            """
            UPDATE assets
            SET current_version_id = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (version_id, asset_id),
        )
        connection.execute(
            """
            UPDATE raw_events
            SET processed = 1, processed_asset_version_id = ?
            WHERE id = ?
            """,
            (version_id, raw_event_id),
        )
        connection.commit()
        return {
            "asset_id": asset_id,
            "version_id": version_id,
            "rationale": rationale,
            "embedded": True,
        }
    except Exception:
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
