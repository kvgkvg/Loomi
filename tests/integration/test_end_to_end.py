from __future__ import annotations

import subprocess

from adapters.git_adapter import capture_commit
from capture_pipeline.process import process_raw_event
import capture_pipeline.process as process_module
from db.client import get_vector_collection


class FakeEmbedder:
    def encode(self, text):
        return [0.11, 0.22, 0.33]


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
    monkeypatch.setattr(process_module, "_get_embedding_model", lambda: FakeEmbedder())

    event = capture_commit(sha)
    result = process_raw_event(event["raw_event_id"])

    assert result["embedded"] is True
    assert get_vector_collection().get(ids=[result["version_id"]])["ids"] == [
        result["version_id"]
    ]
