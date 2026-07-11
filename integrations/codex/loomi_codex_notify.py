#!/usr/bin/env python3
"""Loomi Intent CI — Codex CLI notify hook (experimental).

Codex CLI invokes the configured `notify` program with one JSON argument per
event. On `agent-turn-complete` the payload carries the user's input messages;
we forward them to the Loomi gateway as an intent review. Fire-and-forget:
short timeout, all errors swallowed, exit 0 always.

Install — add to ~/.codex/config.toml:
    notify = ["python3", "/path/to/Loomi/integrations/codex/loomi_codex_notify.py"]

Environment: LOOMI_API_URL (default http://localhost:3001), LOOMI_USER.
"""

import json
import os
import sys
import urllib.request


def main() -> int:
    if len(sys.argv) < 2:
        return 0
    try:
        event = json.loads(sys.argv[1])
        if event.get("type") != "agent-turn-complete":
            return 0
        messages = event.get("input-messages") or event.get("input_messages") or []
        history = [m.strip() for m in messages if isinstance(m, str) and m.strip()]
        prompt = history[-1] if history else ""
        if not prompt:
            return 0
        body = json.dumps(
            {
                "prompt": prompt[:4000],
                "source_env": "codex",
                "user_name": os.environ.get("LOOMI_USER") or os.environ.get("USER"),
                "chat_history": [m[:1000] for m in history[-20:]],
            }
        ).encode()
        base = os.environ.get("LOOMI_API_URL", "http://localhost:3001")
        request = urllib.request.Request(
            f"{base}/api/intent-review",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(request, timeout=10)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
