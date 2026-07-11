import json

import pytest

from adapters.chat_adapter import ChatExportError, capture_chat_export, normalize_chat_export
from db.client import get_pg_connection


def test_normalizes_chatgpt_mapping_in_order():
    payload = {
        "id": "chat-1",
        "title": "Router prompt",
        "mapping": {
            "u": {"id": "u", "parent": None, "message": {"author": {"role": "user"}, "content": {"parts": ["Make router"]}, "create_time": 1}},
            "a": {"id": "a", "parent": "u", "message": {"author": {"role": "assistant"}, "content": {"parts": ["Draft"]}, "create_time": 2}},
        },
    }

    result = normalize_chat_export(payload, "chatgpt")

    assert result["external_conversation_id"] == "chat-1"
    assert [turn["role"] for turn in result["turns"]] == ["user", "assistant"]
    assert result["turns"][1]["parent_external_id"] == "u"


def test_normalizes_claude_messages_and_redacts_secret():
    payload = {
        "uuid": "claude-1",
        "name": "JSON prompt",
        "chat_messages": [
            {"uuid": "m1", "sender": "human", "text": "key sk-secretvalue123456", "created_at": "2026-01-01"},
            {"uuid": "m2", "sender": "assistant", "text": "Use JSON", "created_at": "2026-01-02"},
        ],
    }

    result = normalize_chat_export(payload, "claude")

    assert result["turns"][0]["content"] == "key [REDACTED]"
    assert result["turns"][1]["role"] == "assistant"


def test_capture_is_idempotent(isolated_runtime):
    payload = {"uuid": "c1", "name": "Prompt", "chat_messages": [{"uuid": "m1", "sender": "human", "text": "hello"}]}

    first = capture_chat_export(payload, "claude")
    second = capture_chat_export(payload, "claude")

    assert first == second
    conn = get_pg_connection()
    assert conn.execute("SELECT count(*) FROM raw_events").fetchone()[0] == 1
    signal = json.loads(conn.execute("SELECT raw_signal FROM raw_events").fetchone()[0])
    assert signal["external_conversation_id"] == "c1"


@pytest.mark.parametrize("payload,source", [({}, "claude"), ({"id": "x"}, "chatgpt"), ({}, "other")])
def test_rejects_malformed_export(payload, source):
    with pytest.raises(ChatExportError):
        normalize_chat_export(payload, source)
