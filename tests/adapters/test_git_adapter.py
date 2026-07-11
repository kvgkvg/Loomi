from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass

import pytest

from adapters.git_adapter import capture_commit
from db.client import get_pg_connection


@dataclass
class GitRepo:
    path: object
    sha: str


def _git(path, *args):
    return subprocess.run(
        ["git", *args], cwd=path, check=True, text=True, capture_output=True
    ).stdout.strip()


@pytest.fixture
def git_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.name", "Test User")
    _git(repo, "config", "user.email", "test@example.com")
    prompt = repo / "prompts" / "support.md"
    prompt.parent.mkdir()
    prompt.write_text("Classify support tickets by queue.\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "add support prompt")
    return GitRepo(path=repo, sha=_git(repo, "rev-parse", "HEAD"))


def test_capture_commit_persists_canonical_event(
    git_repo, isolated_runtime, monkeypatch
):
    monkeypatch.chdir(git_repo.path)

    result = capture_commit(git_repo.sha)

    assert result["source_tool"] == "git"
    assert result["title"] == "add support prompt"
    assert "prompts/support.md" in result["content"]
    assert "Classify support tickets" in result["content"]
    row = get_pg_connection().execute(
        "SELECT processed, raw_signal FROM raw_events WHERE id = ?",
        (result["raw_event_id"],),
    ).fetchone()
    signal = json.loads(row["raw_signal"])
    assert row["processed"] == 0
    assert signal["commit_sha"] == git_repo.sha
    assert signal["paths"] == ["prompts/support.md"]


def test_capture_commit_rejects_unknown_sha(git_repo, isolated_runtime, monkeypatch):
    monkeypatch.chdir(git_repo.path)

    with pytest.raises(ValueError, match="Unknown commit"):
        capture_commit("deadbeef")


def test_capture_commit_rejects_commit_without_supported_files(
    tmp_path, isolated_runtime, monkeypatch
):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.name", "Test User")
    _git(repo, "config", "user.email", "test@example.com")
    (repo / "image.bin").write_bytes(b"\x00\x01")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "add binary")
    monkeypatch.chdir(repo)

    with pytest.raises(ValueError, match="No supported knowledge files"):
        capture_commit(_git(repo, "rev-parse", "HEAD"))
