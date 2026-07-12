"""Seed script — inserts sample users/assets/versions/rationale + Chroma vectors.

Run from repo root:
    python -m db.seed

Idempotent: wipes previous seed data first (rows + collection), then reinserts,
so re-running never duplicates.
"""

import json
import shutil
import subprocess
import uuid

from db.client import get_pg_connection, get_vector_collection


def _uid() -> str:
    return str(uuid.uuid4())


def _docker_chroma_running() -> bool:
    """True if a 'loomi-chroma' container is currently up (would divert seeds away from host Chroma)."""
    if not shutil.which("docker"):
        return False
    try:
        out = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", "loomi-chroma"],
            capture_output=True, text=True, timeout=3,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    return out.returncode == 0 and out.stdout.strip().lower() == "true"


USERS = [
    # (name, email, team)
    ("An", "an@company.vn", "support"),
    ("Hồng", "hong@company.vn", "sales-ops"),
    ("Trí", "tri@company.vn", "product"),
    ("Khang", "khang@company.vn", "data"),
]

# (type, title, source_tool, owner_name, tags, versions) —
# versions = list of (content, diff_summary, rationale dict)
ASSETS = [
    (
        "prompt",
        "Support ticket triage chatbot prompt",
        "claude_chat",
        "An",
        ["support", "chatbot", "classification"],
        [
            (
                "You are a support triage assistant. Classify each incoming ticket into "
                "billing, technical, or account categories and draft a first reply.",
                "initial version",
                {
                    "problem": "Support team drowning in unsorted tickets; needed automatic "
                               "classification of incoming tickets into billing/technical/account "
                               "plus a drafted first response.",
                    "failed_attempts": ["Zero-shot classification mislabeled ~30% of billing tickets as technical."],
                    "constraints": ["Must answer in Vietnamese when the customer writes in Vietnamese."],
                },
            ),
            (
                "You are a support triage assistant. Classify each incoming ticket into "
                "billing, technical, or account categories. Use the 5 few-shot examples below. "
                "If confidence is low, route to a human. Draft a first reply in the customer's language.",
                "added few-shot examples + low-confidence human fallback",
                {
                    "problem": "Zero-shot version misclassified ambiguous tickets; needed few-shot "
                               "examples and a human-fallback rule for low-confidence cases.",
                    "failed_attempts": ["Raising temperature made classifications inconsistent.",
                                        "Long system prompt with 20 examples hit context limits."],
                    "constraints": ["Max 5 few-shot examples to stay under token budget.",
                                    "Low-confidence tickets must go to a human, never auto-replied."],
                },
            ),
        ],
    ),
    (
        "agent_config",
        "Lead qualification agent for inbound sales",
        "claude_chat",
        "An",
        ["sales", "classification", "leads"],
        [
            (
                "Agent: lead-qualifier. Reads inbound lead form + email thread, scores lead 1-5 "
                "on budget, authority, need, timeline. Outputs JSON {score, reasons, next_action}.",
                "initial version",
                {
                    "problem": "Sales wasted hours manually reading inbound leads; needed an agent "
                               "that scores leads by BANT criteria and suggests the next action.",
                    "failed_attempts": ["Free-text output was unparseable downstream — switched to strict JSON."],
                    "constraints": ["Output must be valid JSON, schema {score, reasons, next_action}.",
                                    "Never contact the lead directly; suggestion only."],
                },
            ),
        ],
    ),
    (
        "workflow",
        "n8n workflow: weekly customer feedback digest",
        "n8n",
        "Trí",
        ["feedback", "automation", "reporting"],
        [
            (
                "n8n workflow: pull NPS survey responses every Friday, cluster comments by theme "
                "with an LLM node, post digest to #product-feedback Slack channel.",
                "initial version",
                {
                    "problem": "Product team never read raw NPS comments; needed an automatic weekly "
                               "digest clustered by theme delivered where the team already looks.",
                    "failed_attempts": ["Daily digest was too noisy — nobody read it; weekly worked."],
                    "constraints": ["Must run under n8n free-tier execution limits.",
                                    "No customer PII may appear in the Slack digest."],
                },
            ),
        ],
    ),
    (
        "prompt",
        "SQL query generator for revenue dashboards",
        "git",
        "Khang",
        ["sql", "analytics", "reporting"],
        [
            (
                "Generate PostgreSQL queries for the finance mart. Always filter soft-deleted rows "
                "(deleted_at IS NULL), use UTC dates, and limit results to 1000 rows.",
                "initial version",
                {
                    "problem": "Analysts kept writing SQL that forgot soft-delete filters, producing "
                               "inflated revenue numbers in dashboards.",
                    "failed_attempts": ["Relying on a comment in the schema doc — nobody read it."],
                    "constraints": ["Every query must include deleted_at IS NULL.",
                                    "All timestamps compared in UTC."],
                },
            ),
        ],
    ),
    (
        "prompt",
        "Meeting notes summarizer with action items",
        "claude_chat",
        "Hồng",
        ["meetings", "summarization", "productivity"],
        [
            (
                "Summarize the meeting transcript into: decisions made, action items with owner "
                "and deadline, open questions. Keep under 200 words.",
                "initial version",
                {
                    "problem": "Meeting notes were unstructured walls of text; action items got lost. "
                               "Needed fixed sections: decisions, action items with owners, open questions.",
                    "failed_attempts": ["Unstructured 'summarize this' prompt buried the action items mid-paragraph."],
                    "constraints": ["Under 200 words so it fits in one Slack message.",
                                    "Every action item must have an owner or be flagged 'unassigned'."],
                },
            ),
        ],
    ),
    (
        "agent_config",
        "Onboarding FAQ agent for new hires",
        "claude_chat",
        "Trí",
        ["onboarding", "hr", "faq"],
        [
            (
                "Agent: onboarding-faq. Answers new-hire questions grounded ONLY on the HR handbook "
                "and IT setup guide. If the answer is not in the docs, say so and link the HR contact.",
                "initial version",
                {
                    "problem": "New hires asked the same 20 questions every month; HR spent hours "
                               "repeating answers that already lived in the handbook.",
                    "failed_attempts": ["Ungrounded agent hallucinated a leave policy that did not exist — "
                                        "had to restrict it to retrieved handbook passages only."],
                    "constraints": ["Answers must cite the handbook section.",
                                    "Out-of-scope questions route to HR contact, never guessed."],
                },
            ),
        ],
    ),
]

USAGE = [
    # (asset_title, user_name, task_description)
    ("Support ticket triage chatbot prompt", "Trí", "reuse triage prompt for product bug reports"),
    ("Support ticket triage chatbot prompt", "Khang", "classify data-request tickets"),
    ("SQL query generator for revenue dashboards", "Hồng", "monthly sales revenue report"),
]


def seed() -> None:
    if _docker_chroma_running():
        print(
            "WARNING: 'loomi-chroma' container is running. The backend reads from\n"
            "         that HTTP-backed Chroma (chroma:8000), NOT the host Chroma.\n"
            "         Run `make seed-in-docker` (== `docker exec loomi-core python -m db.seed`)\n"
            "         instead, or this seed will write to a Chroma no service reads.",
            flush=True,
        )
    conn = get_pg_connection()
    cur = conn.cursor()

    # wipe previous seed (order respects FKs; cascades handle children)
    for table in ["asset_usage", "asset_tags", "tags", "rationale",
                  "asset_versions", "assets", "raw_events", "users"]:
        cur.execute(f"DELETE FROM {table}")

    user_ids = {}
    for name, email, team in USERS:
        uid = _uid()
        user_ids[name] = uid
        cur.execute("INSERT INTO users (id, name, email, team) VALUES (?,?,?,?)",
                    (uid, name, email, team))

    tag_ids = {}
    asset_ids = {}
    chroma_docs = []  # (id, document, metadata)

    for a_type, title, source_tool, owner, tags, versions in ASSETS:
        asset_id = _uid()
        asset_ids[title] = asset_id
        cur.execute(
            "INSERT INTO assets (id, type, title, source_tool, owner_id, usage_count) "
            "VALUES (?,?,?,?,?,0)",
            (asset_id, a_type, title, source_tool, user_ids[owner]),
        )

        for tag in tags:
            if tag not in tag_ids:
                tag_ids[tag] = _uid()
                cur.execute("INSERT INTO tags (id, name) VALUES (?,?)", (tag_ids[tag], tag))
            cur.execute("INSERT INTO asset_tags (asset_id, tag_id) VALUES (?,?)",
                        (asset_id, tag_ids[tag]))

        last_version_id = None
        for i, (content, diff_summary, rat) in enumerate(versions, start=1):
            version_id = _uid()
            last_version_id = version_id
            cur.execute(
                "INSERT INTO asset_versions (id, asset_id, version_number, content, "
                "diff_summary, editor_id) VALUES (?,?,?,?,?,?)",
                (version_id, asset_id, i, content, diff_summary, user_ids[owner]),
            )
            cur.execute(
                "INSERT INTO rationale (id, version_id, problem, failed_attempts, "
                "constraints, confidence) VALUES (?,?,?,?,?,?)",
                (_uid(), version_id, rat["problem"],
                 json.dumps(rat["failed_attempts"], ensure_ascii=False),
                 json.dumps(rat["constraints"], ensure_ascii=False),
                 "auto"),
            )

        cur.execute("UPDATE assets SET current_version_id = ? WHERE id = ?",
                    (last_version_id, asset_id))

        # embed title + latest content + latest problem (same doc recipe the
        # capture pipeline should use: content + rationale.problem)
        latest_content, _, latest_rat = versions[-1]
        chroma_docs.append((
            asset_id,
            f"{title}\n{latest_content}\n{latest_rat['problem']}",
            {"asset_id": asset_id, "title": title, "type": a_type, "owner": owner},
        ))

    for title, user, task in USAGE:
        cur.execute(
            "INSERT INTO asset_usage (id, asset_id, user_id, task_description) VALUES (?,?,?,?)",
            (_uid(), asset_ids[title], user_ids[user], task),
        )
        cur.execute("UPDATE assets SET usage_count = usage_count + 1 WHERE id = ?",
                    (asset_ids[title],))

    conn.commit()
    conn.close()

    collection = get_vector_collection()
    existing = collection.get()["ids"]
    if existing:
        collection.delete(ids=existing)
    collection.add(
        ids=[d[0] for d in chroma_docs],
        documents=[d[1] for d in chroma_docs],
        metadatas=[d[2] for d in chroma_docs],
    )

    print(f"Seeded {len(ASSETS)} assets, {len(USERS)} users, "
          f"{collection.count()} vectors in Chroma.")


if __name__ == "__main__":
    seed()
