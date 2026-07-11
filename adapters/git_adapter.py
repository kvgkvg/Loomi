"""Capture Git commits as canonical organizational-memory events."""

from __future__ import annotations

import json
import subprocess
import uuid
from pathlib import Path

from db.client import get_pg_connection


SUPPORTED_SUFFIXES = {".md", ".txt", ".prompt", ".json", ".yaml", ".yml"}


def _git(*args: str, cwd: Path | None = None) -> str:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=cwd,
            check=True,
            text=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        message = exc.stderr.strip() if isinstance(exc, subprocess.CalledProcessError) else str(exc)
        raise ValueError(message or "Git command failed") from exc
    return completed.stdout.strip()


def _resolve_commit(commit_sha: str, repository: Path) -> str:
    if not isinstance(commit_sha, str) or not commit_sha.strip():
        raise ValueError("Unknown commit: commit SHA is empty")
    try:
        return _git("rev-parse", "--verify", f"{commit_sha}^{{commit}}", cwd=repository)
    except ValueError as exc:
        raise ValueError(f"Unknown commit: {commit_sha}") from exc


def _changed_paths(commit_sha: str, repository: Path) -> list[str]:
    output = _git(
        "diff-tree",
        "--root",
        "--no-commit-id",
        "--name-only",
        "-r",
        commit_sha,
        cwd=repository,
    )
    candidates = sorted({line for line in output.splitlines() if line})
    supported: list[str] = []
    for path in candidates:
        if Path(path).suffix.lower() not in SUPPORTED_SUFFIXES:
            continue
        try:
            _git("cat-file", "-e", f"{commit_sha}:{path}", cwd=repository)
        except ValueError:
            continue
        supported.append(path)
    return supported


def capture_commit(commit_sha: str) -> dict:
    """Capture one Git commit and persist its canonical raw event."""
    repository = Path(_git("rev-parse", "--show-toplevel")).resolve()
    resolved_sha = _resolve_commit(commit_sha, repository)
    paths = _changed_paths(resolved_sha, repository)
    if not paths:
        raise ValueError("No supported knowledge files found in commit")

    title = _git("show", "-s", "--format=%s", resolved_sha, cwd=repository)
    sections = []
    for path in paths:
        content = _git("show", f"{resolved_sha}:{path}", cwd=repository)
        sections.append(f"--- {path} ---\n{content}")
    content = "\n\n".join(sections)
    diff = _git(
        "show",
        "--format=fuller",
        "--no-ext-diff",
        "--no-renames",
        resolved_sha,
        "--",
        *paths,
        cwd=repository,
    )
    raw_signal = json.dumps(
        {
            "repository_root": str(repository),
            "commit_sha": resolved_sha,
            "paths": paths,
            "diff": diff,
        },
        ensure_ascii=False,
    )
    raw_event_id = str(uuid.uuid4())
    connection = get_pg_connection()
    try:
        connection.execute(
            """
            INSERT INTO raw_events (id, source_tool, title, content, raw_signal, processed)
            VALUES (?, 'git', ?, ?, ?, 0)
            """,
            (raw_event_id, title, content, raw_signal),
        )
        connection.commit()
    finally:
        connection.close()

    return {
        "raw_event_id": raw_event_id,
        "source_tool": "git",
        "title": title,
        "content": content,
        "raw_signal": raw_signal,
    }
