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
    if prompt:
        print(json.dumps({
            "prompt": prompt[:4000],
            "source_env": "claude-code",
            "user_name": sys.argv[1],
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
