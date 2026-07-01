# Pi Agent Integration (ACP Target)

Pi (v0.78.0) is a minimal terminal coding harness by Mario Zechner.
Installed globally at `$AGENT_OS_HOME/.npm-global/bin/pi` (WSL side).
Node.js v22.22.2 required (npm package).

## Current Status

Installed, configured, and wired into ACP dispatch. Role `pi` added to
`roles.toml` and `acp_to_run_agent.sh` maps `pi` provider to `acpx pi exec`.

Verified 2026-05-31: `acp-task pi scratch "..." --wait` dispatched via
`acpx pi exec`, exit_code=0, stderr confirms `calling acpx pi exec`.

Extensions installed:
- `agent-os-bridge.ts` (full Agent OS integration: memory, ACP, workspaces,
  non-negotiables enforcement, RTK guidance)
- `npm:pi-dynamic-workflows` (adds `workflow` tool with `agent()`/`parallel()`/`pipeline()`)
- `git:github.com/badlogic/pi-skills` (browser tools, google calendar, gmail, etc.)

`pi list` shows all three installed.

## Install

```bash
npm install -g --ignore-scripts @earendil-works/pi-coding-agent
```

## Provider Mapping (env vars -> Pi)

| Env var | Pi provider name | Notes |
|---|---|---|
| GOOGLE_API_KEY | `google` | Gemini models |
| GEMINI_API_KEY | `google` | (redundant, use GOOGLE_API_KEY) |
| OPENROUTER_API_KEY | `openrouter` | Routes many models |
| CEREBRAS_API_KEY | `cerebras` | Fast inference |
| OPENCODE_GO_API_KEY | `opencode`, `opencode-go` | DeepSeek etc. |
| NVIDIA_API_KEY | `nvidia` | NV models (Pi has no native nvidia provider — route via openrouter) |
| (ChatGPT Plus OAuth) | `openai-codex` | Via `/login`, not API key |

## Default Provider/Model

Set in `~/.pi/agent/settings.json`. Can override at launch:
```bash
pi --provider openai-codex      # ChatGPT Plus subscription
pi --provider google             # Gemini
pi --provider cerebras           # Cerebras fast models
pi --provider openrouter --model "stepfun/step-3.5-flash"  # Step 3.5 Flash via OpenRouter
pi --provider openrouter --model "stepfun/step-3.7-flash"  # Step 3.7 Flash (needs paid credits)
```

## ACP Dispatch

Added to `roles.toml` and `acp_to_run_agent.sh`. Call via:

```bash
acp-task pi <workspace> "<objective>" [--wait]
```

Provider mapping in `acp_to_run_agent.sh`:
```
pi)       ACPX_AGENT="pi" ;;
```

Triggers `acpx pi exec -f <prompt_file>` with NDJSON output parsing, same
as opencode/codex/claude. Full ACP lifecycle: message_sent → dispatch_started
→ adapter_completed → dispatch_completed.

## Common Pitfall: ChatGPT Plus Login But Pi Fails

You sign into ChatGPT Plus via `/login` (creates `openai-codex` OAuth entry),
but Pi defaults to `openai` provider (API key mode) which has no credentials.

Fix: `pi --provider openai-codex` or change `defaultProvider` in settings.json
to `openai-codex`.

## Step 3.7 Flash

`stepfun/step-3.7-flash` (256K ctx, thinking + vision) is available via
OpenRouter but requires paid credits. The free variant
`stepfun/step-3.7-flash:free` does not exist. `stepfun/step-3.5-flash`
is free and confirmed working.

## RPC Mode (Future ACP Integration)

Pi has a JSONL stdin/stdout RPC mode suitable for ACP bridging:
```bash
pi --mode rpc [options]
```

Key commands: `prompt`, `bash`, `steer`, `abort`, `get_state`, `compact`,
`fork`, `clone`. See https://pi.dev/docs/latest/rpc for full protocol.

Pi's SDK (`@earendil-works/pi-agent-core`) provides programmatic embedding
for Node.js without subprocess overhead.

## Tree Sessions (Unique Value)

Pi supports tree-based sessions with `/fork` (branch) and `/clone`.
Branch off for side-quests, summarize, fold back into main session.
No other agent in the stack (Claude Code, Codex, OpenCode) has this.

## Workflow Extension

`npm:pi-dynamic-workflows` adds a `workflow` tool for fan-out subagent
scripts using `agent()`, `parallel()`, `pipeline()`. Installed via
`pi install npm:pi-dynamic-workflows` and activated on `/reload` or
next session start. The handoff doc is at
See the pi-dynamic-workflows extension documentation.

## RTK Guidance

Pi's `agent-os-bridge.ts` extension injects RTK usage into every session's
system prompt via context block. Pi can use `rtk ls`, `rtk read`, `rtk grep`,
`rtk find`, `rtk git` for token-efficient inspection.

## Commands

| What | Command |
|---|---|
| Start in project | `cd /project && pi` |
| Continue last session | `pi -c` |
| Browse sessions | `pi -r` |
| One-shot prompt | `pi -p "summarize this"` |
| Reference files | `pi @src/app.ts "review this"` |
| Fork/branch session | `/fork` (inside TUI) |
| Switch model | `/model` or Ctrl+L |
| Run shell cmd inline | `!npm run lint` |
| Run & mute shell cmd | `!!command` |
