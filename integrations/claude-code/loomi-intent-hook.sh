#!/usr/bin/env bash
# Loomi Intent CI — Claude Code UserPromptSubmit hook.
# Reads the hook JSON from stdin, extracts the prompt, and fire-and-forgets it
# to the Loomi gateway. Never blocks or fails the user's prompt: total budget
# is a detached curl with a short timeout, and the hook always exits 0.
#
# Install: see integrations/claude-code/settings-snippet.json

LOOMI_API_URL="${LOOMI_API_URL:-http://localhost:3001}"
LOOMI_USER="${LOOMI_USER:-$(whoami)}"

payload=$(python3 -c '
import json, sys
try:
    hook = json.load(sys.stdin)
    prompt = (hook.get("prompt") or "").strip()
  history = []
  candidates = [
    hook.get("history"),
    hook.get("messages"),
    hook.get("input_messages"),
    hook.get("input-messages"),
    (hook.get("conversation") or {}).get("messages") if isinstance(hook.get("conversation"), dict) else None,
  ]
  for candidate in candidates:
    if not isinstance(candidate, list):
      continue
    for item in candidate:
      if isinstance(item, str) and item.strip():
        history.append(item.strip())
      elif isinstance(item, dict):
        text = item.get("content") or item.get("text") or ""
        if isinstance(text, str) and text.strip():
          history.append(text.strip())
    if prompt:
        print(json.dumps({
            "prompt": prompt[:4000],
            "source_env": "claude-code",
            "user_name": sys.argv[1],
      "chat_history": [m[:1000] for m in history[-20:]],
        }))
except Exception:
    pass
' "$LOOMI_USER" 2>/dev/null)

if [ -n "$payload" ]; then
  curl -s -m 10 -X POST "$LOOMI_API_URL/api/intent-review" \
    -H 'Content-Type: application/json' \
    -d "$payload" >/dev/null 2>&1 &
  disown 2>/dev/null || true
fi

exit 0
