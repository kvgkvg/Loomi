"""End-to-end demo: the "Hồng discovers An's prior work" story, wired across
all four components.

Flow:
  0. Khang  — seed the org's AI memory (past assets from An, Trí, Khang).
  1. Hồng   — a new hire types a task; recommend() surfaces related assets
              by MEANING, not keywords (the core loop).
  2. Trí    — onboarding assistant explains WHY the top asset was built
              (grounded in stored rationale; uses Gemini if GEMINI_API_KEY set,
              otherwise prints the stored rationale directly — still grounded).
  3. Ấn     — (optional, --capture) commit a brand-new prompt to a throwaway
              git repo, run the capture pipeline, then recommend() again to
              show the fresh knowledge is instantly discoverable.

Usage:
  python3 demo.py                       # stages 0-2 (no API keys needed)
  python3 demo.py --query "..."         # custom task description
  python3 demo.py --capture             # also run Ấn's capture magic (needs FEATHERLESS_API_KEY)
  python3 demo.py --fresh               # wipe the demo DB and reseed

Isolated demo store lives under .data/demo/ (gitignored) so it never touches
a real DB and is safe to re-run.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

_REPO = Path(__file__).resolve().parent
_DEMO_DIR = _REPO / ".data" / "demo"


def _bootstrap_env(fresh: bool) -> None:
    """Point the shared DB client at an isolated demo store; load .env keys."""
    try:
        from dotenv import load_dotenv

        load_dotenv(_REPO / ".env")
    except Exception:
        pass  # dotenv optional; env vars may already be set

    if fresh and _DEMO_DIR.exists():
        shutil.rmtree(_DEMO_DIR)
    _DEMO_DIR.mkdir(parents=True, exist_ok=True)
    os.environ["LOOMI_DB_PATH"] = str(_DEMO_DIR / "loomi.sqlite3")
    os.environ["LOOMI_CHROMA_PATH"] = str(_DEMO_DIR / "chroma")


def _rule(title: str) -> None:
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def stage_seed() -> None:
    from db.client import get_vector_collection
    from db.seed import seed

    _rule("STAGE 0 — Khang: seed the organizational AI memory")
    if get_vector_collection().count() == 0:
        seed()
    else:
        print("Memory already populated (use --fresh to reseed).")


def stage_recommend(query: str) -> list[dict]:
    from recommend.engine import recommend

    _rule("STAGE 1 — Hồng: new task → proactive recommendations (by meaning)")
    print(f'Hồng was just assigned: "{query}"')
    print("She never searched — the system surfaces related prior work:\n")
    results = recommend(query, top_k=5)
    if not results:
        print("(no related assets found)")
        return results
    for i, r in enumerate(results, 1):
        print(f"  {i}. [{r['score']:.3f}] {r['title']}  — {r['owner_name']}")
        print(f"       why: {r['problem']}")
        print(f"       reused {r['usage_count']}x  (id={r['asset_id']})")
    return results


def _fallback_rationale(asset_id: str) -> dict:
    """No-LLM grounded explanation: read the stored rationale straight from DB."""
    from db.client import get_pg_connection

    conn = get_pg_connection()
    row = conn.execute(
        """
        SELECT a.title AS title, v.version_number AS vn,
               r.problem AS problem, r.constraints AS constraints,
               r.failed_attempts AS failed_attempts
        FROM assets a
        JOIN asset_versions v ON v.id = a.current_version_id
        LEFT JOIN rationale r ON r.version_id = v.id
        WHERE a.id = ?
        """,
        (asset_id,),
    ).fetchone()
    conn.close()
    if row is None:
        return {"explanation": "Asset not found.", "cited_versions": [], "cited_constraints": []}

    def _load(js):
        try:
            return json.loads(js) if js else []
        except Exception:
            return []

    constraints = _load(row["constraints"])
    failed = _load(row["failed_attempts"])
    parts = [f'"{row["title"]}" was built because: {row["problem"] or "n/a"}']
    if failed:
        parts.append("Failed attempts along the way: " + "; ".join(failed))
    if constraints:
        parts.append("Hard constraints: " + "; ".join(constraints))
    return {
        "explanation": " ".join(parts),
        "cited_versions": [row["vn"]] if row["vn"] else [],
        "cited_constraints": constraints,
    }


def stage_onboard(asset_id: str) -> None:
    _rule("STAGE 2 — Trí: onboarding assistant explains WHY it was built")
    if os.getenv("GEMINI_API_KEY"):
        try:
            from onboarding.assistant import explain_asset

            result = explain_asset(asset_id)
            source = "Gemini (grounded on stored rationale)"
        except Exception as exc:  # live call failed — degrade gracefully
            print(f"(Gemini call failed: {exc} — falling back to stored rationale)\n")
            result = _fallback_rationale(asset_id)
            source = "stored rationale (no LLM)"
    else:
        print("(GEMINI_API_KEY not set — showing stored rationale directly)\n")
        result = _fallback_rationale(asset_id)
        source = "stored rationale (no LLM)"

    print(f"[source: {source}]\n")
    print(result["explanation"])
    if result["cited_versions"]:
        print(f"\ncited versions: {result['cited_versions']}")
    if result["cited_constraints"]:
        print(f"cited constraints: {result['cited_constraints']}")


def stage_capture(query: str) -> None:
    _rule("STAGE 3 — Ấn: capture a brand-new commit → instantly discoverable")
    if not os.getenv("FEATHERLESS_API_KEY"):
        print("(FEATHERLESS_API_KEY not set — skipping live capture stage)")
        return

    from adapters.git_adapter import capture_commit
    from capture_pipeline.process import process_raw_event
    from recommend.engine import recommend

    tmp = Path(tempfile.mkdtemp(prefix="loomi-demo-repo-"))
    try:
        def git(*args):
            subprocess.run(["git", *args], cwd=tmp, check=True,
                           text=True, capture_output=True)

        git("init"); git("config", "user.name", "An"); git("config", "user.email", "an@co.vn")
        prompt = tmp / "prompts" / "lead_scorer.md"
        prompt.parent.mkdir(parents=True)
        prompt.write_text(
            "You are a lead-scoring agent. Read an inbound sales lead and rate it "
            "1-5 on fit and intent, then recommend the next action.\n",
            encoding="utf-8",
        )
        git("add", "."); git("commit", "-m", "add lead scoring prompt")
        sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp,
                             text=True, capture_output=True).stdout.strip()

        cwd = os.getcwd()
        os.chdir(tmp)
        try:
            event = capture_commit(sha)
            result = process_raw_event(event["raw_event_id"])
        finally:
            os.chdir(cwd)

        if not result.get("embedded"):
            print(f"Capture pipeline did not embed (error: {result.get('error')}).")
            return
        print(f"New asset captured + embedded: asset_id={result['asset_id']}")
        print(f"LLM rationale.problem: {result['rationale']['problem']}\n")
        print(f'Re-running recommend("{query}") — the fresh asset now surfaces:\n')
        for i, r in enumerate(recommend(query, top_k=3), 1):
            print(f"  {i}. [{r['score']:.3f}] {r['title']}  — {r['owner_name']}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="Loomi end-to-end demo")
    ap.add_argument("--query", default="build a lead-classification agent for sales")
    ap.add_argument("--capture", action="store_true", help="run Ấn's live capture stage")
    ap.add_argument("--fresh", action="store_true", help="wipe demo DB and reseed")
    args = ap.parse_args()

    _bootstrap_env(args.fresh)

    stage_seed()
    results = stage_recommend(args.query)
    if results:
        stage_onboard(results[0]["asset_id"])
    if args.capture:
        stage_capture(args.query)

    _rule("Demo complete")
    print("Core loop (seed → recommend → onboard) ran without any API key.")
    if not args.capture:
        print("Add --capture (with FEATHERLESS_API_KEY) to see live commit capture.")


if __name__ == "__main__":
    sys.exit(main())
