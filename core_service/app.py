"""FastAPI transport that delegates to Loomi's existing domain functions."""

import json
import uuid
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, StringConstraints

from capture_pipeline.process import process_raw_event
from db.client import get_pg_connection
from onboarding.assistant import explain_asset
from recommend.engine import recommend

from core_service.events import events

app = FastAPI(title="Loomi core", docs_url=None, redoc_url=None)
NonEmpty = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class RecommendRequest(BaseModel):
    task_description: NonEmpty
    top_k: int = Field(default=5, ge=1, le=20)


class ExplainRequest(BaseModel):
    question: str | None = None


class UseRequest(BaseModel):
    user_id: NonEmpty | None = None
    task_description: NonEmpty


class CaptureRequest(BaseModel):
    commit_sha: NonEmpty


def _json(value):
    if value is None:
        return []
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return [value]
    return value


def _asset_detail(asset_id: str) -> dict | None:
    connection = get_pg_connection()
    try:
        asset = connection.execute(
            """
            SELECT a.id, a.type, a.title, a.source_tool, a.usage_count,
                   u.name AS owner_name
            FROM assets a LEFT JOIN users u ON u.id = a.owner_id
            WHERE a.id = ?
            """,
            (asset_id,),
        ).fetchone()
        if asset is None:
            return None
        versions = connection.execute(
            """
            SELECT av.version_number, av.content, av.diff_summary,
                   r.problem, r.failed_attempts, r.constraints, r.confidence
            FROM asset_versions av
            LEFT JOIN rationale r ON r.version_id = av.id
            WHERE av.asset_id = ? ORDER BY av.version_number
            """,
            (asset_id,),
        ).fetchall()
        return {
            "id": asset["id"],
            "type": asset["type"],
            "title": asset["title"],
            "source_tool": asset["source_tool"],
            "usage_count": asset["usage_count"] or 0,
            "owner_name": asset["owner_name"] or "",
            "versions": [
                {
                    "version_number": row["version_number"],
                    "content": row["content"],
                    "diff_summary": row["diff_summary"],
                    "problem": row["problem"],
                    "failed_attempts": _json(row["failed_attempts"]),
                    "constraints": _json(row["constraints"]),
                    "confidence": row["confidence"],
                }
                for row in versions
            ],
        }
    finally:
        connection.close()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/recommend")
def recommend_assets(request: RecommendRequest):
    return {"results": recommend(request.task_description, request.top_k)}


@app.get("/assets/{asset_id}")
def get_asset(asset_id: str):
    detail = _asset_detail(asset_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="asset not found")
    return detail


@app.post("/assets/{asset_id}/explain")
def explain(asset_id: str, request: ExplainRequest):
    return explain_asset(asset_id, request.question)


@app.post("/assets/{asset_id}/use", status_code=status.HTTP_201_CREATED)
def use_asset(asset_id: str, request: UseRequest):
    connection = get_pg_connection()
    try:
        row = connection.execute(
            """
            SELECT av.content FROM assets a
            JOIN asset_versions av ON av.id = a.current_version_id
            WHERE a.id = ?
            """,
            (asset_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="asset not found")
        connection.execute(
            "INSERT INTO asset_usage (id, asset_id, user_id, task_description) VALUES (?, ?, ?, ?)",
            (str(uuid.uuid4()), asset_id, request.user_id, request.task_description),
        )
        connection.execute(
            "UPDATE assets SET usage_count = usage_count + 1 WHERE id = ?", (asset_id,)
        )
        connection.commit()
        return {"recorded": True, "content": row["content"]}
    except HTTPException:
        raise
    except Exception as error:
        connection.rollback()
        raise HTTPException(status_code=503, detail="unable to record usage") from error
    finally:
        connection.close()


@app.post("/internal/capture", status_code=status.HTTP_202_ACCEPTED)
def capture(request: CaptureRequest):
    result = process_raw_event(request.commit_sha)
    if result.get("embedded") and result.get("asset_id"):
        events.publish({"type": "memory_ready", "asset_id": result["asset_id"]})
    return result


@app.get("/internal/events")
def lifecycle_events(once: bool = Query(default=False)):
    async def stream():
        queued = events.pop()
        if queued is not None:
            yield f"data: {json.dumps(queued)}\n\n"
            if once:
                return
        async for event in events.subscribe():
            yield f"data: {json.dumps(event)}\n\n"
            if once:
                return

    return StreamingResponse(stream(), media_type="text/event-stream")
