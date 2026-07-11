"""Streamlit review and role-aware discovery UI."""

from __future__ import annotations

import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

from adapters.chat_adapter import capture_chat_export
from capture_pipeline.chat_process import process_chat_event
from onboarding.assistant import explain_asset
from rationale.review import ensure_reviewer, list_pending_statements, review_statement
from recommend.engine import recommend


def _load_runtime_env(path: str | Path | None = None) -> None:
    env_path = Path(path) if path is not None else PROJECT_ROOT / ".env"
    load_dotenv(env_path, override=False)


def main() -> None:
    _load_runtime_env()
    import streamlit as st

    st.set_page_config(page_title="Loomi", page_icon="🧠", layout="wide")
    st.title("Loomi · Organizational AI Memory")
    role = st.sidebar.selectbox("Role", ["Intern", "Developer", "Tech Lead", "Manager"])
    reviewer_name = st.sidebar.text_input("Reviewer name")

    discover, review, import_tab = st.tabs(["Discover", "Review rationale", "Import history"])
    with discover:
        task = st.text_input("What are you working on?")
        if task:
            for item in recommend(task, role=role):
                with st.expander(f"{item['title']} · {item['score']:.3f}"):
                    st.write(item.get("role_reason", ""))
                    question = st.text_input("Ask why", key=f"q-{item['asset_id']}")
                    if st.button("Explain", key=f"e-{item['asset_id']}"):
                        st.json(explain_asset(item["asset_id"], question or None, role=role))

    with review:
        for item in list_pending_statements():
            st.subheader(item["title"])
            st.caption(f"{item['evidence_kind']} · confidence {item['confidence']}")
            edited = st.text_area("Rationale", item["statement"], key=f"s-{item['id']}")
            for turn in item["source_turns"]:
                st.code(f"{turn['speaker_role']}: {turn['content']}")
            approve, edit, reject = st.columns(3)
            if approve.button("Approve", key=f"a-{item['id']}"):
                review_statement(item["id"], "approve", ensure_reviewer(reviewer_name))
                st.rerun()
            if edit.button("Edit & approve", key=f"x-{item['id']}"):
                review_statement(item["id"], "edit", ensure_reviewer(reviewer_name), edited_statement=edited)
                st.rerun()
            if reject.button("Reject", key=f"r-{item['id']}"):
                review_statement(item["id"], "reject", ensure_reviewer(reviewer_name))
                st.rerun()

    with import_tab:
        source = st.selectbox("Export source", ["claude", "chatgpt"])
        upload = st.file_uploader("Conversation export JSON", type="json")
        if upload and st.button("Import and infer rationale"):
            payload = json.load(upload)
            captured = capture_chat_export(payload, source)
            st.json(process_chat_event(captured["raw_event_id"]))


if __name__ == "__main__":
    main()
