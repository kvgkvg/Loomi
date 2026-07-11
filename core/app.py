import logging
import os
import subprocess
import asyncio
import json
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Set

import anyio
from fastapi import FastAPI, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

# Core modules
from db.client import get_pg_connection, get_vector_collection
from recommend.engine import recommend
from onboarding.assistant import explain_asset
from adapters.git_adapter import capture_commit
from capture_pipeline.process import process_raw_event

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("core.app")

# SSE Broadcaster
class EventBroadcaster:
    def __init__(self):
        self.listeners: Set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        queue = asyncio.Queue()
        self.listeners.add(queue)
        logger.info(f"New event subscriber. Total active listeners: {len(self.listeners)}")
        return queue

    def unsubscribe(self, queue: asyncio.Queue):
        self.listeners.discard(queue)
        logger.info(f"Subscriber removed. Total active listeners: {len(self.listeners)}")

    async def broadcast(self, event_type: str, data: dict):
        event = {
            "event": event_type,
            "data": data
        }
        if self.listeners:
            logger.info(f"Broadcasting '{event_type}' to {len(self.listeners)} listeners: {data}")
            # Put in all queues
            for queue in list(self.listeners):
                await queue.put(event)

event_broadcaster = EventBroadcaster()

# Helper Git command runner
def run_git(args: list[str], cwd: Path) -> str:
    completed = subprocess.run(
        ["git"] + args,
        cwd=cwd,
        check=True,
        text=True,
        capture_output=True,
    )
    return completed.stdout.strip()

# Helper to check if a commit has already been captured
def is_commit_captured(connection, commit_sha: str) -> bool:
    pattern = f'%"commit_sha": "{commit_sha}"%'
    row = connection.execute(
        "SELECT id FROM raw_events WHERE source_tool = 'git' AND raw_signal LIKE ?",
        (pattern,)
    ).fetchone()
    return row is not None

# Helper to fetch asset details for the ready event
def get_asset_details(connection, asset_id: str) -> dict:
    row = connection.execute(
        """
        SELECT a.id AS asset_id, a.title AS title, u.name AS owner, r.problem AS problem
        FROM assets a
        LEFT JOIN users u ON a.owner_id = u.id
        LEFT JOIN asset_versions av ON a.current_version_id = av.id
        LEFT JOIN rationale r ON r.version_id = av.id
        WHERE a.id = ?
        """,
        (asset_id,)
    ).fetchone()
    if row:
        return {
            "asset_id": row["asset_id"],
            "title": row["title"],
            "owner": row["owner"] or "",
            "problem": row["problem"] or ""
        }
    return {}

# Polling function run in a worker thread
def poll_git_repo(repo_path: Path) -> list[dict]:
    connection = get_pg_connection()
    try:
        # Check git_poll_state
        row = connection.execute(
            "SELECT last_polled_sha FROM git_poll_state WHERE repo_path = ?",
            (str(repo_path),)
        ).fetchone()

        if row is None:
            # Initialize with HEAD SHA
            try:
                head_sha = run_git(["rev-parse", "HEAD"], repo_path)
            except Exception as e:
                logger.error(f"Failed to get HEAD SHA for initialization: {e}")
                return []
            
            connection.execute(
                "INSERT INTO git_poll_state (repo_path, last_polled_sha) VALUES (?, ?)",
                (str(repo_path), head_sha)
            )
            connection.commit()
            logger.info(f"Initialized git_poll_state for {repo_path} at HEAD={head_sha}")
            return []

        last_sha = row["last_polled_sha"]
        # Get current HEAD SHA
        try:
            head_sha = run_git(["rev-parse", "HEAD"], repo_path)
        except Exception as e:
            logger.error(f"Failed to get HEAD SHA: {e}")
            return []

        if last_sha == head_sha:
            return []

        # Get commits between last_sha and HEAD
        try:
            output = run_git(["log", "--reverse", "--format=%H", f"{last_sha}..HEAD"], repo_path)
            commits = [line.strip() for line in output.splitlines() if line.strip()]
        except Exception as e:
            logger.warning(f"Failed to get git log from {last_sha}..HEAD: {e}. Resetting last_polled_sha to HEAD={head_sha}")
            connection.execute(
                "UPDATE git_poll_state SET last_polled_sha = ?, updated_at = CURRENT_TIMESTAMP WHERE repo_path = ?",
                (head_sha, str(repo_path))
            )
            connection.commit()
            return []

        new_events = []
        for sha in commits:
            if is_commit_captured(connection, sha):
                # Update poll state so we don't look at it again
                connection.execute(
                    "UPDATE git_poll_state SET last_polled_sha = ?, updated_at = CURRENT_TIMESTAMP WHERE repo_path = ?",
                    (sha, str(repo_path))
                )
                connection.commit()
                continue

            try:
                logger.info(f"Git poller capturing new commit: {sha}")
                capture_res = capture_commit(sha)
                raw_event_id = capture_res["raw_event_id"]
                
                logger.info(f"Git poller processing raw event: {raw_event_id}")
                process_res = process_raw_event(raw_event_id)

                if process_res.get("embedded"):
                    details = get_asset_details(connection, process_res["asset_id"])
                    if details:
                        new_events.append(details)
            except ValueError as e:
                logger.info(f"Skipping commit {sha}: {e}")
            except Exception as e:
                logger.error(f"Failed to capture/process commit {sha}: {e}", exc_info=True)

            # Advance last_polled_sha to the processed commit
            connection.execute(
                "UPDATE git_poll_state SET last_polled_sha = ?, updated_at = CURRENT_TIMESTAMP WHERE repo_path = ?",
                (sha, str(repo_path))
            )
            connection.commit()

        return new_events
    finally:
        connection.close()

# Background poller loop
async def git_poller_task():
    logger.info("Git poller background task started.")
    repo_path_str = os.environ.get("LOOMI_REPO_PATH")
    if not repo_path_str:
        try:
            repo_path_str = run_git(["rev-parse", "--show-toplevel"], Path("."))
        except Exception:
            repo_path_str = str(Path(__file__).resolve().parent.parent)

    repo_path = Path(repo_path_str).resolve()
    logger.info(f"Git poller monitoring repository at: {repo_path}")

    while True:
        try:
            new_events = await anyio.to_thread.run_sync(poll_git_repo, repo_path)
            for event_details in new_events:
                await event_broadcaster.broadcast("memory_ready", event_details)
        except asyncio.CancelledError:
            logger.info("Git poller cancelled.")
            break
        except Exception as e:
            logger.error(f"Error in git_poller_task: {e}", exc_info=True)
        
        await asyncio.sleep(3.0)

# Lifespan manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Trust the workspace directory for Git command line running under different ownership inside container
    try:
        subprocess.run(["git", "config", "--global", "--add", "safe.directory", "*"], check=True)
        logger.info("Configured Git safe.directory to '*'")
    except Exception as e:
        logger.warning(f"Failed to configure Git safe.directory: {e}")

    # Start poller loop if not in testing mode
    poller = None
    if os.environ.get("LOOMI_TESTING") != "1":
        poller = asyncio.create_task(git_poller_task())
    yield
    # Stop poller loop
    if poller:
        poller.cancel()
        try:
            await poller
        except asyncio.CancelledError:
            pass

app = FastAPI(title="Loomi Core Service", lifespan=lifespan)

# Request Models
class RecommendRequest(BaseModel):
    task_description: str
    top_k: int = Field(default=5, ge=1)

class ExplainRequest(BaseModel):
    asset_id: str
    question: str | None = None

class CaptureRequest(BaseModel):
    commit_sha: str

class AdoptRequest(BaseModel):
    asset_id: str
    user_id: str | None = None
    task_description: str

# Endpoints
@app.get("/health")
def health_check():
    try:
        conn = get_pg_connection()
        conn.execute("SELECT 1").fetchone()
        conn.close()
    except Exception as e:
        logger.error(f"Health check: database error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database connection failed: {e}"
        )

    try:
        col = get_vector_collection()
        col.count()
    except Exception as e:
        logger.error(f"Health check: vector store error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Vector store connection failed: {e}"
        )

    return {
        "status": "ok",
        "database": "ok",
        "vector_store": "ok"
    }

@app.post("/recommend")
async def recommend_endpoint(req: RecommendRequest):
    # Run the recommend call in a thread pool to avoid blocking the event loop
    results = await anyio.to_thread.run_sync(recommend, req.task_description, req.top_k)
    return results

@app.post("/explain")
async def explain_endpoint(req: ExplainRequest):
    # Run explain_asset in a thread pool
    result = await anyio.to_thread.run_sync(explain_asset, req.asset_id, req.question)
    return result

@app.post("/capture")
async def capture_endpoint(req: CaptureRequest):
    try:
        # Run capture and processing in thread pool
        capture_res = await anyio.to_thread.run_sync(capture_commit, req.commit_sha)
        raw_event_id = capture_res["raw_event_id"]
        process_res = await anyio.to_thread.run_sync(process_raw_event, raw_event_id)

        if process_res.get("error"):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=process_res["error"]
            )

        if process_res.get("embedded"):
            # Fetch details to broadcast
            def fetch_details():
                conn = get_pg_connection()
                try:
                    return get_asset_details(conn, process_res["asset_id"])
                finally:
                    conn.close()

            details = await anyio.to_thread.run_sync(fetch_details)
            if details:
                await event_broadcaster.broadcast("memory_ready", details)

        return {
            "status": "success",
            "raw_event_id": raw_event_id,
            "asset_id": process_res.get("asset_id"),
            "version_id": process_res.get("version_id"),
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in manual capture for {req.commit_sha}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@app.post("/adopt")
async def adopt_endpoint(req: AdoptRequest):
    try:
        import uuid
        def record():
            conn = get_pg_connection()
            try:
                usage_id = str(uuid.uuid4())
                user_id = req.user_id
                if not user_id:
                    row = conn.execute("SELECT id FROM users LIMIT 1").fetchone()
                    user_id = row["id"] if row else None

                conn.execute(
                    """
                    INSERT INTO asset_usage (id, asset_id, user_id, task_description)
                    VALUES (?, ?, ?, ?)
                    """,
                    (usage_id, req.asset_id, user_id, req.task_description)
                )
                conn.execute(
                    "UPDATE assets SET usage_count = usage_count + 1 WHERE id = ?",
                    (req.asset_id,)
                )
                conn.commit()
                return usage_id
            finally:
                conn.close()

        usage_id = await anyio.to_thread.run_sync(record)
        return {"status": "success", "usage_id": usage_id}
    except Exception as e:
        logger.error(f"Error recording asset usage: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@app.get("/events")
async def events_endpoint():
    async def event_generator():
        queue = event_broadcaster.subscribe()
        try:
            # Initial connection notification for the client
            yield "data: {\"status\": \"connected\"}\n\n"
            if os.environ.get("LOOMI_TESTING") == "1":
                return
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"event: {event['event']}\ndata: {json.dumps(event['data'])}\n\n"
                except asyncio.TimeoutError:
                    # Keep-alive comment
                    yield ": ping\n\n"
        except asyncio.CancelledError:
            logger.info("SSE event generator connection closed.")
        finally:
            event_broadcaster.unsubscribe(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "text/event-stream",
        }
    )
