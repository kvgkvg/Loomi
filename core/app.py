import logging
import os
import re
import subprocess
import asyncio
import json
import time
import threading
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
from intent_ci.engine import create_intent_review, list_intent_reviews, resolve_intent_review
from rationale.review import ReviewError, ensure_reviewer, list_pending_statements, review_statement

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

# Captured in lifespan so worker threads can broadcast onto the event loop
MAIN_LOOP: asyncio.AbstractEventLoop | None = None

def _parse_signal(raw_signal) -> dict:
    if isinstance(raw_signal, str):
        try:
            return json.loads(raw_signal or "{}")
        except Exception:
            return {}
    return raw_signal or {}

def _json_len(value) -> int:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except Exception:
            return 0
    return len(value) if isinstance(value, list) else 0

def _run_header(run_id: str, signal: dict, title, received_at=None, status: str = "running") -> dict:
    sha = signal.get("commit_sha") or ""
    return {
        "run_id": run_id,
        "sha": sha[:7],
        "full_sha": sha,
        "message": title or "",
        "author": signal.get("author_name") or "",
        "files": signal.get("paths") or [],
        "received_at": str(received_at) if received_at else None,
        "status": status,
    }

def _build_stages(header: dict, detail: dict) -> list[dict]:
    """Build the six pipeline stages with real run data.

    detail keys: asset_id, version_id, version_number, problem, confidence,
    constraints_count, failed_count, error (error marks the LLM stage failed).
    """
    sha = header["full_sha"]
    paths = header["files"]
    stages: list[dict] = []

    def add(key, status, log, result=None):
        stages.append({"key": key, "status": status, "log": log, "result": result or {}})

    add("adapter", "success", [
        f"$ git rev-parse --verify {sha[:12]}^{{commit}}",
        f"Filtered {len(paths)} supported file{'s' if len(paths) != 1 else ''}: {', '.join(paths)}",
        f"Captured author {header['author']} + diff",
        "Persisted raw_events row (processed=0)",
    ], {"source_tool": "git", "title": header["message"], "paths": ", ".join(paths)})

    error = detail.get("error")
    if error:
        add("version", "success", [
            "Computed asset_key = sha256(repository_root + sorted(paths))",
        ], {})
        add("llm", "failed", [
            "POST https://api.featherless.ai/v1/chat/completions",
            "model=zai-org/GLM-5.2 temperature=0.1",
            f"⚠ {error}",
            "Transaction rolled back — raw event left processed=0 for retry",
        ], {"error": error})
        for key in ("persist", "embed", "finalize"):
            add(key, "skipped", [], {})
        return stages

    version_label = f"v{detail['version_number']}" if detail.get("version_number") else "row"
    add("version", "success", [
        "Computed asset_key = sha256(repository_root + sorted(paths))",
        f"asset_id {detail.get('asset_id') or ''}",
        f"Inserted asset_versions {version_label}",
    ], {"asset_id": detail.get("asset_id"), "version": detail.get("version_number")})
    add("llm", "success", [
        "POST https://api.featherless.ai/v1/chat/completions",
        "model=zai-org/GLM-5.2 temperature=0.1",
        f"problem: \"{detail.get('problem') or ''}\"",
        f"constraints: {detail.get('constraints_count', 0)} · failed_attempts: {detail.get('failed_count', 0)}",
    ], {"problem": detail.get("problem"), "confidence": detail.get("confidence")})
    if detail.get("review_status") == "pending":
        add("persist", "success", [
            "INSERT INTO rationale_statements (..., review_status='pending')",
            f"pending statements: {detail.get('statement_count', 0)}",
        ], {"table": "rationale_statements", "review_status": "pending"})
        add("embed", "success", [
            "Precomputed draft embedding for fast approval",
            f"Upserted Chroma vector id={detail.get('asset_id')}",
        ], {"vector_id": detail.get("asset_id"), "version_id": detail.get("version_id")})
        add("finalize", "skipped", [
            "Waiting for human review before writing trusted rationale",
            "raw_events.processed remains 0 for retry/review visibility",
        ], {"review_status": "pending", "asset_id": detail.get("asset_id"), "version_id": detail.get("version_id")})
        return stages
    add("persist", "success", [
        "INSERT INTO rationale (problem, failed_attempts, constraints, confidence)",
        f"confidence: {detail.get('confidence')}",
    ], {"table": "rationale", "confidence": detail.get("confidence")})
    add("embed", "success", [
        "Embedding content + problem (all-MiniLM-L6-v2)",
        f"Upserted vector id={detail.get('asset_id')} into Chroma",
    ], {"vector_id": detail.get("asset_id"), "version_id": detail.get("version_id")})
    add("finalize", "success", [
        "UPDATE assets SET current_version_id = …",
        "UPDATE raw_events SET processed = 1",
        "COMMIT transaction",
        "Pipeline complete ✓",
    ], {"asset_id": detail.get("asset_id"), "version_id": detail.get("version_id"), "embedded": True})
    return stages

def _emit_stage(header: dict, stage: str, status: str, log=None, result=None):
    """Broadcast a pipeline_stage event from a worker thread."""
    if MAIN_LOOP is None:
        return
    payload = {"run": header, "stage": stage, "status": status, "log": log or [], "result": result or {}}
    try:
        asyncio.run_coroutine_threadsafe(
            event_broadcaster.broadcast("pipeline_stage", payload), MAIN_LOOP
        )
    except Exception:
        logger.warning("Failed to emit pipeline_stage event", exc_info=True)

# Resolve the repository the git poller / manual capture should target.
def resolve_repo_path() -> Path:
    repo_path_str = os.environ.get("LOOMI_REPO_PATH")
    if not repo_path_str:
        try:
            repo_path_str = run_git(["rev-parse", "--show-toplevel"], Path("."))
        except Exception:
            repo_path_str = str(Path(__file__).resolve().parent.parent)
    return Path(repo_path_str).resolve()

# Mutable repository the poller currently tracks (switchable at runtime via /track).
_tracked_repo: Path | None = None
_tracked_lock = threading.Lock()

# Directory (inside a writable bind mount) where /track clones remote repos.
_CLONE_DIR = Path("/app/.demo-repos")

# Where the host home directory is bind-mounted read-only (docker-compose).
_HOST_MOUNT = Path("/host")

def _translate_host_path(target: str) -> Path:
    """Map a host filesystem path to its /host bind-mount equivalent.

    Users paste local paths as they see them on the host (~/x or $HOME/x).
    Inside the container those live under /host. Paths already visible in the
    container are returned unchanged.
    """
    candidate = Path(target)
    if candidate.exists():
        return candidate
    host_home = (os.environ.get("LOOMI_HOST_HOME") or "").rstrip("/")
    if target.startswith("~/"):
        translated = _HOST_MOUNT / target[2:]
    elif host_home and (target == host_home or target.startswith(host_home + "/")):
        translated = _HOST_MOUNT / target[len(host_home) :].lstrip("/")
    else:
        return candidate
    return translated if translated.exists() else candidate

def get_tracked_repo() -> Path:
    global _tracked_repo
    with _tracked_lock:
        if _tracked_repo is None:
            _tracked_repo = resolve_repo_path()
        return _tracked_repo

def set_tracked_repo(repo: Path) -> None:
    global _tracked_repo
    with _tracked_lock:
        _tracked_repo = repo

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
        "SELECT id FROM raw_events WHERE source_tool = 'git' AND CAST(raw_signal AS TEXT) LIKE ?",
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
                capture_res = capture_commit(sha, repo_path)
                raw_event_id = capture_res["raw_event_id"]

                signal = _parse_signal(capture_res["raw_signal"])
                header = _run_header(sha, signal, capture_res["title"])
                adapter_stage = _build_stages(header, {})[0]
                _emit_stage(header, "adapter", "success", adapter_stage["log"], adapter_stage["result"])
                _emit_stage(header, "version", "running", ["Computing asset_key = sha256(repository_root + sorted(paths))"])
                _emit_stage(header, "llm", "running", [
                    "POST https://api.featherless.ai/v1/chat/completions",
                    "model=zai-org/GLM-5.2 temperature=0.1",
                    "Waiting for completion…",
                ])

                logger.info(f"Git poller processing raw event: {raw_event_id}")
                process_res = process_raw_event(raw_event_id)

                if process_res.get("error"):
                    for stage in _build_stages(header, {"error": process_res["error"]})[1:]:
                        _emit_stage(header, stage["key"], stage["status"], stage["log"], stage["result"])
                        time.sleep(0.2)
                else:
                    rationale = process_res.get("rationale") or {}
                    version_row = connection.execute(
                        "SELECT version_number FROM asset_versions WHERE id = ?",
                        (process_res["version_id"],)
                    ).fetchone()
                    detail = {
                        "asset_id": process_res["asset_id"],
                        "version_id": process_res["version_id"],
                        "version_number": version_row["version_number"] if version_row else None,
                        "problem": rationale.get("problem"),
                        "confidence": rationale.get("confidence"),
                        "constraints_count": _json_len(rationale.get("constraints")),
                        "failed_count": _json_len(rationale.get("failed_attempts")),
                        "review_status": process_res.get("review_status"),
                        "statement_count": len(process_res.get("statement_ids") or []),
                        "draft_embedded": process_res.get("draft_embedded"),
                    }
                    for stage in _build_stages(header, detail)[1:]:
                        if stage["key"] in {"persist", "embed", "finalize"}:
                            _emit_stage(header, stage["key"], "running", ["Processing…"], {})
                            # ponytail: brief demo pacing; remove when real stage callbacks exist.
                            time.sleep(0.65)
                        _emit_stage(header, stage["key"], stage["status"], stage["log"], stage["result"])
                        time.sleep(0.35)

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
    logger.info(f"Git poller monitoring repository at: {get_tracked_repo()}")

    while True:
        try:
            repo_path = get_tracked_repo()
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
    global MAIN_LOOP
    MAIN_LOOP = asyncio.get_running_loop()
    # Trust the workspace directory for Git command line running under different ownership inside container
    try:
        subprocess.run(["git", "config", "--global", "--add", "safe.directory", "*"], check=True)
        logger.info("Configured Git safe.directory to '*'")
    except Exception as e:
        logger.warning(f"Failed to configure Git safe.directory: {e}")

    # Pre-warm the client-side embedding model so the first user request does not
    # pay the one-time model load/download (which otherwise looks like a UI freeze).
    async def _warm_embeddings():
        def _warm():
            try:
                get_vector_collection().query(query_texts=["warmup"], n_results=1)
                logger.info("Embedding model warmed.")
            except Exception as e:
                logger.warning(f"Embedding warmup skipped: {e}")
        await anyio.to_thread.run_sync(_warm)

    poller = None
    warmup = None
    if os.environ.get("LOOMI_TESTING") != "1":
        poller = asyncio.create_task(git_poller_task())
        warmup = asyncio.create_task(_warm_embeddings())
    yield
    # Stop background tasks
    if warmup:
        warmup.cancel()
        try:
            await warmup
        except asyncio.CancelledError:
            pass
    if poller:
        poller.cancel()
        try:
            await poller
        except asyncio.CancelledError:
            pass
    MAIN_LOOP = None

app = FastAPI(title="Loomi Core Service", lifespan=lifespan)

# Request Models
class RecommendRequest(BaseModel):
    task_description: str
    top_k: int = Field(default=5, ge=1)
    role: str | None = None

class ExplainRequest(BaseModel):
    asset_id: str
    question: str | None = None
    role: str | None = None

class CaptureRequest(BaseModel):
    commit_sha: str

class RationaleReviewRequest(BaseModel):
    reviewer: str = "Reviewer"

class AdoptRequest(BaseModel):
    asset_id: str
    user_id: str | None = None
    task_description: str

class TrackRequest(BaseModel):
    # A git URL (https/git@) to clone, or a path already visible inside the container.
    repo: str

class IntentReviewRequest(BaseModel):
    prompt: str
    source_env: str = "unknown"
    user_name: str | None = None
    chat_history: list[str] | None = None

class IntentResolveRequest(BaseModel):
    action: str  # approve | reject
    reviewer: str | None = None

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

@app.get("/runs")
async def runs_endpoint(limit: int = 20):
    def fetch():
        conn = get_pg_connection()
        try:
            rows = conn.execute(
                """
                SELECT re.id, re.title, re.received_at, re.processed, re.raw_signal,
                       av.id AS version_id, av.version_number, av.asset_id,
                       r.problem, r.confidence, r.failed_attempts, r.constraints
                FROM raw_events re
                LEFT JOIN asset_versions av ON av.id = re.processed_asset_version_id
                LEFT JOIN rationale r ON r.version_id = av.id
                WHERE re.source_tool = 'git'
                ORDER BY re.received_at DESC
                LIMIT ?
                """,
                (limit,)
            ).fetchall()
            runs = []
            for row in rows:
                signal = _parse_signal(row["raw_signal"])
                run_id = signal.get("commit_sha") or row["id"]
                processed = bool(row["processed"])
                pending_review = (not processed) and bool(row["version_id"])
                header = _run_header(
                    run_id, signal, row["title"], row["received_at"],
                    "success" if processed else ("running" if pending_review else "failed"),
                )
                if processed:
                    detail = {
                        "asset_id": row["asset_id"],
                        "version_id": row["version_id"],
                        "version_number": row["version_number"],
                        "problem": row["problem"],
                        "confidence": row["confidence"],
                        "constraints_count": _json_len(row["constraints"]),
                        "failed_count": _json_len(row["failed_attempts"]),
                    }
                elif pending_review:
                    statement_rows = conn.execute(
                        """
                        SELECT statement_type, statement
                        FROM rationale_statements
                        WHERE version_id = ?
                        """,
                        (row["version_id"],),
                    ).fetchall()
                    detail = {
                        "asset_id": row["asset_id"],
                        "version_id": row["version_id"],
                        "version_number": row["version_number"],
                        "problem": next((s["statement"] for s in statement_rows if s["statement_type"] == "problem"), ""),
                        "confidence": "auto",
                        "constraints_count": len([s for s in statement_rows if s["statement_type"] == "constraint"]),
                        "failed_count": len([s for s in statement_rows if s["statement_type"] == "failed_attempt"]),
                        "review_status": "pending",
                        "statement_count": len(statement_rows),
                    }
                else:
                    detail = {"error": "Pipeline did not complete — raw event left processed=0 for retry"}
                runs.append({**header, "stages": _build_stages(header, detail)})
            return runs
        finally:
            conn.close()

    return {"runs": await anyio.to_thread.run_sync(fetch)}

@app.get("/repo-info")
def repo_info():
    """Report which repository the git poller is currently tracking."""
    repo = get_tracked_repo()

    def _g(args: list[str]) -> str | None:
        try:
            return run_git(args, repo)
        except Exception:
            return None

    head = _g(["rev-parse", "HEAD"])
    return {
        "repo_path": str(repo),
        "remote_url": _g(["config", "--get", "remote.origin.url"]),
        "branch": _g(["rev-parse", "--abbrev-ref", "HEAD"]),
        "head_sha": head,
        "head_short": head[:7] if head else None,
    }

@app.post("/track")
async def track_endpoint(req: TrackRequest):
    """Switch the repository the poller tracks at runtime.

    Accepts a git URL (cloned into a writable mount) or a path already visible
    inside the container. Note: arbitrary host paths must be bind-mounted first.
    """
    target = (req.repo or "").strip()
    if not target:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "repo is required")

    def _resolve_and_set() -> Path:
        if re.match(r"^(https?://|git@)", target):
            name = re.sub(r"[^A-Za-z0-9._-]+", "-", target.rstrip("/").split("/")[-1])
            name = re.sub(r"-?\.git$", "", name) or "repo"
            dest = _CLONE_DIR / name
            if not (dest / ".git").exists():
                _CLONE_DIR.mkdir(parents=True, exist_ok=True)
                subprocess.run(
                    ["git", "clone", "--depth", "80", target, str(dest)],
                    check=True, text=True, capture_output=True,
                )
            candidate = dest
        else:
            candidate = _translate_host_path(target)
        if not candidate.exists():
            raise ValueError(f"path not found in container: {candidate}")
        root = run_git(["rev-parse", "--show-toplevel"], candidate)
        repo = Path(root).resolve()
        set_tracked_repo(repo)
        logger.info(f"Now tracking repository: {repo}")
        return repo

    try:
        await anyio.to_thread.run_sync(_resolve_and_set)
    except subprocess.CalledProcessError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"git clone failed: {e.stderr or e}")
    except Exception as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Cannot track repo: {e}")
    return repo_info()

@app.post("/recommend")
async def recommend_endpoint(req: RecommendRequest):
    # Run the recommend call in a thread pool to avoid blocking the event loop
    results = await anyio.to_thread.run_sync(recommend, req.task_description, req.top_k, req.role)
    return results

@app.post("/explain")
async def explain_endpoint(req: ExplainRequest):
    # Run explain_asset in a thread pool
    result = await anyio.to_thread.run_sync(explain_asset, req.asset_id, req.question, req.role)
    return result

@app.get("/asset/{asset_id}")
async def asset_endpoint(asset_id: str):
    """Full asset detail: current content plus version history with rationale."""

    def fetch():
        conn = get_pg_connection()
        try:
            asset_row = conn.execute(
                """
                SELECT a.id AS asset_id, a.title AS title, a.type AS type,
                       a.usage_count AS usage_count, u.name AS owner_name,
                       av.content AS content
                FROM assets a
                LEFT JOIN users u ON a.owner_id = u.id
                LEFT JOIN asset_versions av ON a.current_version_id = av.id
                WHERE a.id = ?
                """,
                (asset_id,),
            ).fetchone()
            if asset_row is None:
                return None

            version_rows = conn.execute(
                """
                SELECT av.version_number AS version_number, av.created_at AS created_at,
                       av.diff_summary AS diff_summary, r.problem AS problem,
                       r.constraints AS constraints
                FROM asset_versions av
                LEFT JOIN rationale r ON r.version_id = av.id
                WHERE av.asset_id = ?
                ORDER BY av.version_number
                """,
                (asset_id,),
            ).fetchall()

            versions = []
            for row in version_rows:
                constraints = row["constraints"]
                if isinstance(constraints, str):
                    try:
                        constraints = json.loads(constraints)
                    except (TypeError, json.JSONDecodeError):
                        constraints = []
                versions.append(
                    {
                        "version_number": row["version_number"],
                        "created_at": str(row["created_at"]) if row["created_at"] else None,
                        "diff_summary": row["diff_summary"],
                        "problem": row["problem"],
                        "constraints": constraints or [],
                    }
                )

            return {
                "asset_id": asset_row["asset_id"],
                "title": asset_row["title"],
                "type": asset_row["type"],
                "usage_count": asset_row["usage_count"],
                "owner_name": asset_row["owner_name"] or "",
                "content": asset_row["content"] or "",
                "versions": versions,
            }
        finally:
            conn.close()

    result = await anyio.to_thread.run_sync(fetch)
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Asset not found")
    return result

@app.post("/capture")
async def capture_endpoint(req: CaptureRequest):
    try:
        # Run capture and processing in thread pool (target the monitored repo)
        repo_path = get_tracked_repo()
        capture_res = await anyio.to_thread.run_sync(capture_commit, req.commit_sha, repo_path)
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

@app.post("/rationale-review/version/{version_id}/approve")
async def rationale_review_version_endpoint(version_id: str, req: RationaleReviewRequest):
    def approve_all():
        reviewer_id = ensure_reviewer(req.reviewer)
        pending = [item for item in list_pending_statements() if item["version_id"] == version_id]
        if not pending:
            raise ReviewError("version has no pending rationale")
        for item in pending:
            review_statement(item["id"], "approve", reviewer_id)
        return {"status": "approved", "version_id": version_id, "reviewed": len(pending)}

    try:
        result = await anyio.to_thread.run_sync(approve_all)
        await event_broadcaster.broadcast("rationale_review_resolved", result)
        return result
    except ReviewError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    except Exception as e:
        logger.error("Error approving rationale for version %s: %s", version_id, e, exc_info=True)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, str(e))

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

@app.post("/intent-review")
async def intent_review_endpoint(req: IntentReviewRequest):
    try:
        review = await anyio.to_thread.run_sync(
            create_intent_review, req.prompt, req.source_env, req.user_name, req.chat_history
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    await event_broadcaster.broadcast("intent_review", review)
    await event_broadcaster.broadcast(
        "intent_review_required",
        {
            "id": review["id"],
            "intent": review.get("intent"),
            "status": review["status"],
            "source_env": review["source_env"],
            "user_name": review.get("user_name"),
            "chat_history_count": len(review.get("chat_history") or []),
        },
    )
    return review

@app.get("/intent-reviews")
async def intent_reviews_endpoint(limit: int = 20):
    return await anyio.to_thread.run_sync(list_intent_reviews, min(max(limit, 1), 100))

@app.post("/intent-review/{review_id}/resolve")
async def intent_resolve_endpoint(review_id: str, req: IntentResolveRequest):
    try:
        result = await anyio.to_thread.run_sync(
            resolve_intent_review, review_id, req.action, req.reviewer
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    await event_broadcaster.broadcast("intent_review_resolved", result)
    return result

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
