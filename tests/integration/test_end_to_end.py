from __future__ import annotations

import subprocess

from adapters.git_adapter import capture_commit
from capture_pipeline.process import process_raw_event
import capture_pipeline.process as process_module
from db.client import get_pg_connection, get_vector_collection
from rationale.review import ensure_reviewer, review_statement


def _git(path, *args):
    return subprocess.run(
        ["git", *args], cwd=path, check=True, text=True, capture_output=True
    ).stdout.strip()


def test_commit_to_vector_flow(tmp_path, isolated_runtime, monkeypatch):
    repository = tmp_path / "demo-repo"
    repository.mkdir()
    _git(repository, "init")
    _git(repository, "config", "user.name", "An")
    _git(repository, "config", "user.email", "an@example.com")
    prompt = repository / "prompts" / "ticket-router.md"
    prompt.parent.mkdir()
    prompt.write_text("Route billing and technical tickets.\n", encoding="utf-8")
    _git(repository, "add", ".")
    _git(repository, "commit", "-m", "add ticket router")
    sha = _git(repository, "rev-parse", "HEAD")
    monkeypatch.chdir(repository)
    monkeypatch.setattr(
        process_module,
        "extract_rationale",
        lambda content, signal: {
            "problem": "Route tickets consistently",
            "failed_attempts": [],
            "constraints": ["Use one queue"],
            "confidence": "auto",
        },
    )
    event = capture_commit(sha)
    result = process_raw_event(event["raw_event_id"])

    assert result["embedded"] is False
    assert result["review_status"] == "pending"
    reviewer = ensure_reviewer("Reviewer")
    for statement_id in result["statement_ids"]:
        review_statement(statement_id, "approve", reviewer)
    # Vector is indexed by asset_id (Chroma-managed embedding of the document).
    assert get_vector_collection().get(ids=[result["asset_id"]])["ids"] == [
        result["asset_id"]
    ]
    # Git author is mapped to a users row and set as the asset owner.
    owner = get_pg_connection().execute(
        "SELECT u.name AS name, u.email AS email FROM assets a "
        "JOIN users u ON u.id = a.owner_id WHERE a.id = ?",
        (result["asset_id"],),
    ).fetchone()
    assert owner["name"] == "An"
    assert owner["email"] == "an@example.com"
