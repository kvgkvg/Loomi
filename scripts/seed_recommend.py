"""Seed 6 sample assets (SQL rows + Chroma vectors) for local recommend tests.

Includes An's support-ticket chatbot, deliberately worded WITHOUT the words
'lead', 'classification', or 'sales' so semantic (not keyword) match is proven.
Idempotent: clears its own rows/vectors first.
"""
from db import client_stub
from recommend.embedding import embed

USERS = [
    ("u-an", "An", "an@co.com", "support"),
    ("u-mai", "Mai", "mai@co.com", "marketing"),
    ("u-tan", "Tan", "tan@co.com", "eng"),
]

# (asset_id, type, title, source_tool, owner_id, usage_count,
#  version content, rationale problem, confidence)
ASSETS = [
    ("a-support-bot", "prompt",
     "Support ticket triage assistant", "git", "u-an", 12,
     "Reads each incoming customer support ticket and sorts it into the "
     "correct category, then routes it to the matching team queue "
     "automatically — turning unstructured inbound messages into labeled "
     "buckets.",
     "Support agents were drowning in manually triaging inbound tickets; "
     "they needed to automatically categorize free-text customer messages "
     "into a fixed set of predefined buckets and route them without human "
     "sorting.",
     "user_provided"),
    ("a-email-writer", "prompt",
     "Marketing email drafter", "git", "u-mai", 3,
     "Generates promotional email copy from a product brief.",
     "Marketing spent hours writing repetitive campaign emails by hand.",
     "auto"),
    ("a-meeting-notes", "prompt",
     "Meeting notes summarizer", "git", "u-tan", 7,
     "Condenses a raw meeting transcript into action items.",
     "Long meeting transcripts were never read; key decisions got lost.",
     "auto"),
    ("a-code-review", "agent_config",
     "PR review bot", "git", "u-tan", 5,
     "Reviews pull requests and leaves comments flagging style problems and "
     "likely bugs.",
     "Human reviewers kept missing repetitive style issues on every PR.",
     "user_provided"),
    ("a-invoice-parse", "workflow",
     "Invoice field extractor", "n8n", "u-mai", 2,
     "Workflow extracting totals and dates from uploaded invoice PDFs.",
     "Finance manually retyped numbers off scanned invoices.",
     "auto"),
    ("a-faq-bot", "prompt",
     "Internal FAQ answerer", "git", "u-an", 9,
     "Answers employee questions using the internal handbook.",
     "New hires kept asking HR the same policy questions.",
     "auto"),
]


def seed() -> int:
    conn = client_stub.get_pg_connection()
    cur = conn.cursor()
    # idempotent reset of the tables this script owns
    for tbl in ("rationale", "asset_versions", "assets", "users"):
        cur.execute(f"DELETE FROM {tbl}")

    for uid, name, email, team in USERS:
        cur.execute(
            "INSERT INTO users(id, name, email, team) VALUES (?,?,?,?)",
            (uid, name, email, team),
        )

    docs, ids, metas = [], [], []
    for (aid, atype, title, tool, owner, usage,
         content, problem, conf) in ASSETS:
        vid = f"v-{aid}"
        cur.execute(
            "INSERT INTO assets(id,type,title,source_tool,owner_id,"
            "current_version_id,usage_count) VALUES (?,?,?,?,?,?,?)",
            (aid, atype, title, tool, owner, vid, usage),
        )
        cur.execute(
            "INSERT INTO asset_versions(id,asset_id,version_number,content) "
            "VALUES (?,?,?,?)",
            (vid, aid, 1, content),
        )
        cur.execute(
            "INSERT INTO rationale(id,version_id,problem,confidence) "
            "VALUES (?,?,?,?)",
            (f"r-{aid}", vid, problem, conf),
        )
        docs.append(f"{content} {problem}")
        ids.append(aid)
        metas.append({"asset_id": aid})

    conn.commit()

    col = client_stub.get_vector_collection()
    existing = col.get()["ids"]
    if existing:
        col.delete(ids=existing)
    col.add(ids=ids, embeddings=embed(docs), metadatas=metas)
    return len(ASSETS)


if __name__ == "__main__":
    n = seed()
    print(f"seeded {n} assets")
