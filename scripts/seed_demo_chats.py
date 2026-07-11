"""Seed demo knowledge from chat exports of different AI providers.

Ingests every JSON export in demo/chats/ through the real chat pipeline:
adapter normalization -> raw event -> conversation/asset/statement extraction
(Featherless LLM) -> statement approval -> vector upsert. After this runs,
chat-derived assets are recommendable and explainable exactly like git ones.

Run inside the docker stack (needs DATABASE_URL/CHROMA_HOST/FEATHERLESS_API_KEY):
    docker compose exec core python scripts/seed_demo_chats.py
Idempotent: re-running skips already-processed conversations.

Fixture format: a genuine ChatGPT export (top-level "mapping") or Claude
export ("chat_messages"), plus an optional "_loomi_owner" key naming the
teammate the asset is attributed to.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from adapters.chat_adapter import capture_chat_export
from capture_pipeline.chat_process import process_chat_event
from db.client import get_pg_connection
from rationale.review import ensure_reviewer, list_pending_statements, review_statement

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "demo" / "chats"
DEMO_REVIEWER = "Demo Reviewer"


def detect_source(payload: dict) -> str:
    if "mapping" in payload:
        return "chatgpt"
    if "chat_messages" in payload or "messages" in payload:
        return "claude"
    raise ValueError("cannot detect chat provider (no 'mapping' or 'chat_messages')")


def set_owner(asset_id: str, owner_name: str) -> None:
    owner_id = ensure_reviewer(owner_name)  # inserts the user row if missing
    connection = get_pg_connection()
    try:
        connection.execute(
            "UPDATE assets SET owner_id = ? WHERE id = ?", (owner_id, asset_id)
        )
        connection.commit()
    finally:
        connection.close()


def seed_fixture(path: Path, approve: bool) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    owner = payload.pop("_loomi_owner", None)
    source = detect_source(payload)

    captured = capture_chat_export(payload, source)
    result = process_chat_event(captured["raw_event_id"])
    if result["error"]:
        return {"file": path.name, "source": source, "error": result["error"]}

    if owner:
        set_owner(result["asset_id"], owner)

    approved = 0
    if approve:
        reviewer_id = ensure_reviewer(DEMO_REVIEWER)
        for statement in list_pending_statements(result["asset_id"]):
            review_statement(statement["id"], "approve", reviewer_id)
            approved += 1

    return {
        "file": path.name,
        "source": source,
        "asset_id": result["asset_id"],
        "owner": owner,
        "statements_approved": approved,
        "error": None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--no-approve",
        action="store_true",
        help="leave rationale statements pending (asset stays out of vector search)",
    )
    args = parser.parse_args()

    fixtures = sorted(FIXTURES_DIR.glob("*.json"))
    if not fixtures:
        print(f"No fixtures found in {FIXTURES_DIR}", file=sys.stderr)
        return 1

    failures = 0
    for path in fixtures:
        try:
            outcome = seed_fixture(path, approve=not args.no_approve)
        except Exception as exc:  # keep seeding the rest
            outcome = {"file": path.name, "error": str(exc)}
        if outcome.get("error"):
            failures += 1
            print(f"FAIL  {outcome['file']}: {outcome['error']}")
        else:
            print(
                f"OK    {outcome['file']} [{outcome['source']}] -> asset {outcome['asset_id']}"
                f" (owner={outcome['owner']}, statements approved={outcome['statements_approved']})"
            )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
