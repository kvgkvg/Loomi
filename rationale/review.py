"""Approve, edit, or reject pending rationale statements."""

from __future__ import annotations

import json
import uuid

from db.client import get_pg_connection, get_vector_collection


class ReviewError(ValueError):
    pass


def ensure_reviewer(name: str) -> str:
    if not isinstance(name, str) or not name.strip():
        raise ReviewError("reviewer name is required")
    normalized = " ".join(name.split())
    reviewer_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"loomi-reviewer:{normalized.casefold()}"))
    connection = get_pg_connection()
    try:
        connection.execute(
            "INSERT INTO users (id, name) VALUES (?, ?) ON CONFLICT(id) DO UPDATE SET name=excluded.name",
            (reviewer_id, normalized),
        )
        connection.commit()
        return reviewer_id
    finally:
        connection.close()


def list_pending_statements(asset_id: str | None = None) -> list[dict]:
    connection = get_pg_connection()
    try:
        params = []
        asset_filter = ""
        if asset_id is not None:
            asset_filter = " AND av.asset_id = ?"
            params.append(asset_id)
        rows = connection.execute(
            """
            SELECT rs.*, av.asset_id, a.title
            FROM rationale_statements rs
            JOIN asset_versions av ON av.id = rs.version_id
            JOIN assets a ON a.id = av.asset_id
            WHERE rs.review_status = 'pending'
            """ + asset_filter + " ORDER BY rs.created_at, rs.id",
            params,
        ).fetchall()
        output = []
        for row in rows:
            turns = connection.execute(
                """
                SELECT ct.id, ct.speaker_role, ct.content
                FROM rationale_statement_turns rst
                JOIN conversation_turns ct ON ct.id = rst.turn_id
                WHERE rst.statement_id = ? ORDER BY ct.sequence_number
                """,
                (row["id"],),
            ).fetchall()
            item = dict(row)
            item["source_turns"] = [dict(turn) for turn in turns]
            output.append(item)
        return output
    finally:
        connection.close()


def _trusted_summary(connection, version_id: str) -> tuple[dict, dict]:
    rows = connection.execute(
        """
        SELECT statement_type, statement FROM rationale_statements
        WHERE version_id = ? AND review_status IN ('approved', 'edited')
        ORDER BY created_at, id
        """,
        (version_id,),
    ).fetchall()
    if not rows:
        raise ReviewError("version has no trusted rationale")
    primary = next((row["statement"] for row in rows if row["statement_type"] in {"problem", "intent", "outcome"}), rows[0]["statement"])
    summary = {
        "problem": primary,
        "failed_attempts": [row["statement"] for row in rows if row["statement_type"] == "failed_attempt"],
        "constraints": [row["statement"] for row in rows if row["statement_type"] == "constraint"],
    }
    context = connection.execute(
        """
        SELECT av.asset_id, av.content, a.title, a.source_tool
        FROM asset_versions av JOIN assets a ON a.id = av.asset_id
        WHERE av.id = ?
        """,
        (version_id,),
    ).fetchone()
    rationale_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"loomi-rationale:{version_id}"))
    connection.execute(
        """
        INSERT INTO rationale (id, version_id, problem, failed_attempts, constraints, confidence)
        VALUES (?, ?, ?, ?, ?, 'user_provided')
        ON CONFLICT(version_id) DO UPDATE SET
          problem=excluded.problem, failed_attempts=excluded.failed_attempts,
          constraints=excluded.constraints, confidence='user_provided'
        """,
        (rationale_id, version_id, summary["problem"], json.dumps(summary["failed_attempts"]), json.dumps(summary["constraints"])),
    )
    return summary, dict(context)


def review_statement(
    statement_id: str,
    action: str,
    reviewer_id: str,
    *,
    edited_statement: str | None = None,
    note: str | None = None,
) -> dict:
    if action not in {"approve", "edit", "reject"}:
        raise ReviewError("invalid review action")
    connection = get_pg_connection()
    try:
        row = connection.execute("SELECT * FROM rationale_statements WHERE id = ?", (statement_id,)).fetchone()
        if row is None:
            raise ReviewError("rationale statement not found")
        target = {"approve": "approved", "edit": "edited", "reject": "rejected"}[action]
        if row["review_status"] == target:
            return {"statement_id": statement_id, "review_status": target, "version_id": row["version_id"]}
        if row["review_status"] != "pending":
            raise ReviewError("rationale statement is already reviewed")
        statement = row["statement"]
        if action == "edit":
            if not isinstance(edited_statement, str) or not edited_statement.strip():
                raise ReviewError("edited statement is required")
            statement = edited_statement.strip()
        connection.execute("BEGIN")
        connection.execute(
            """
            UPDATE rationale_statements
            SET statement = ?, review_status = ?, reviewer_id = ?,
                reviewed_at = CURRENT_TIMESTAMP, review_note = ?
            WHERE id = ?
            """,
            (statement, target, reviewer_id, note, statement_id),
        )
        summary = context = None
        if target in {"approved", "edited"}:
            summary, context = _trusted_summary(connection, row["version_id"])
        connection.commit()
        if context is not None:
            get_vector_collection().upsert(
                ids=[context["asset_id"]],
                documents=[f"{context['title']}\n{context['content']}\n{summary['problem']}"],
                metadatas=[{"asset_id": context["asset_id"], "version_id": row["version_id"], "source_tool": context["source_tool"]}],
            )
        return {"statement_id": statement_id, "review_status": target, "version_id": row["version_id"]}
    except ReviewError:
        connection.rollback()
        raise
    except Exception as exc:
        connection.rollback()
        raise ReviewError("unable to review rationale") from exc
    finally:
        connection.close()
