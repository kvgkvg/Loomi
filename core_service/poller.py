"""Retry-safe Git HEAD polling owned by the core service."""

import subprocess
import threading
from pathlib import Path

from adapters.git_adapter import capture_commit
from capture_pipeline.process import process_raw_event
from db.client import get_git_poll_state, save_git_poll_state


class GitPoller:
    def __init__(
        self,
        repository: str | Path,
        *,
        interval: float = 3,
        max_backoff: float = 30,
        resolve_head=None,
        capture=capture_commit,
        process=process_raw_event,
        publish=lambda event: None,
    ):
        self.repository = Path(repository).resolve()
        self.interval = interval
        self.max_backoff = max_backoff
        self._resolve_head = resolve_head or self._git_head
        self._capture = capture
        self._process = process
        self._publish = publish
        self._state_id = str(self.repository)
        self._raw_event_id = None
        self._captured = None
        self._pending_sha = None
        self._failures = 0
        self._stop_event = threading.Event()
        self._thread = None

    @property
    def retry_delay(self) -> float:
        if not self._failures:
            return 0
        return min(
            self.interval * 2 ** max(0, self._failures - 1), self.max_backoff
        )

    def _git_head(self) -> str:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repository,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def poll_once(self) -> None:
        state = get_git_poll_state(self._state_id)
        processed = state["last_processed_sha"] if state else None
        sha = self._pending_sha
        try:
            sha = sha or self._resolve_head()
            if sha == processed:
                return
            if self._raw_event_id is None:
                save_git_poll_state(self._state_id, sha, processed)
                self._publish({"type": "capture_started", "commit_sha": sha})
                self._captured = self._capture(sha)
                self._raw_event_id = self._captured["raw_event_id"]
                self._pending_sha = sha

            result = self._process(self._raw_event_id)
            ready = result.get("embedded") and result.get("asset_id") and result.get("version_id")
            if not ready:
                raise RuntimeError("capture incomplete")

            save_git_poll_state(self._state_id, sha, sha)
            self._publish(
                {
                    "type": "memory_ready",
                    "asset_id": result["asset_id"],
                    "title": self._captured["title"],
                    "source": self._captured["source_tool"],
                    "version": result["version_id"],
                }
            )
            self._raw_event_id = self._captured = self._pending_sha = None
            self._failures = 0
        except Exception:
            self._failures += 1
            self._publish(
                {"type": "capture_retrying", "commit_sha": sha, "error": "capture failed"}
            )

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self.poll_once()
            self._stop_event.wait(self.retry_delay or self.interval)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="git-poller", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join()
