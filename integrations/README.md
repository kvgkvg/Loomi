# Loomi Intent CI — chat environment integrations

Every user prompt sent from a supported chat environment is POSTed to Loomi,
where it runs CI-style checks (`policy_secrets`, `reuse_available`,
`intent_clarity`). Results appear live in the web UI's **Intent CI — Prompt
Reviews** panel; anything not fully green waits for human approve/reject.

All integrations hit one endpoint — anything that can run `curl` can integrate:

```bash
curl -X POST http://localhost:3001/api/intent-review \
  -H 'Content-Type: application/json' \
  -d '{"prompt": "the user prompt text", "source_env": "my-tool", "user_name": "alice"}'
```

| Environment | Status | Mechanism |
|---|---|---|
| Claude Code | ✅ working | `UserPromptSubmit` hook → `claude-code/loomi-intent-hook.sh` |
| Codex CLI | 🧪 experimental | `notify` program → `codex/loomi_codex_notify.py` (payload shape varies by Codex version) |
| GitHub Copilot | ❌ skipped | no prompt-hook/extension API for intercepting chat prompts |
| Anything else | ✅ generic | POST the endpoint above from any hook/wrapper |

## Claude Code

1. Make the hook executable: `chmod +x integrations/claude-code/loomi-intent-hook.sh`
2. Merge `claude-code/settings-snippet.json` into `~/.claude/settings.json`
   (fix the script path).
3. Prompts now flow automatically. The hook is fire-and-forget (detached curl,
   10 s cap, always exits 0) — it never slows or blocks your prompt.

Environment variables: `LOOMI_API_URL` (default `http://localhost:3001`),
`LOOMI_USER` (defaults to `whoami`).

## Codex CLI (experimental)

Add to `~/.codex/config.toml`:

```toml
notify = ["python3", "/path/to/Loomi/integrations/codex/loomi_codex_notify.py"]
```

Codex only fires `notify` on `agent-turn-complete`, so prompts arrive after the
turn finishes (not at submit time), and the payload field names differ across
Codex releases — the script tolerates both `input-messages` and
`input_messages` and silently no-ops otherwise.

## Behavior guarantees

- Capture never blocks the user's chat: all integrations are async
  fire-and-forget with short timeouts and unconditional zero exit.
- Prompts are truncated to 4000 chars and secret-redacted server-side before
  storage (`sk-…` keys, `api_key=…`, passwords).
- LLM failure inside checks degrades to an `error` check result — the review
  is still recorded and gated, nothing crashes.
