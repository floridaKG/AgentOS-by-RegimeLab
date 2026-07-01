# Model Selection in ACP Dispatch

## Current behavior (verified 2026-06-02)

| Provider | ACP --model support | Where model is actually set |
|---|---|---|
| claude | Yes | `--model` flag passed through acpx to claude-agent-acp |
| opencode | No | opencode.json (opencode's own config) |
| codex | No | codex config (OAuth-dependent) |
| pi | No | Pi session state / `~/.pi/agent/settings.json` |

> Note (2026-06-14): the rows above describe **providers**. The ACP **role** `pi`
> in `roles.toml` now sets `provider = pi`, so `acp-task pi …` dispatches through
> the native pi adapter. Pi still manages its own session model state.

## How model flows from roles.toml

roles.toml defines per-role: `chain[0] = "provider:model"` (e.g. `opencode:opencode/deepseek-v4-flash-free`).

The adapter splits on `:` into PROVIDER and MODEL, then:
- For claude: passes `--model "$MODEL"` to acpx. Works.
- For opencode/codex: the flag is suppressed. The MODEL value is logged but ignored.
- For pi: the session is created under native pi and model changes are handled by Pi session state.

## The bug that was fixed

`acp_to_run_agent.sh` originally passed `--model` to ALL non-pi providers. opencode and codex ACP adapters rejected it with a JSON-RPC error:

```
Cannot apply --model "opencode/deepseek-v4-flash-free": the ACP agent did not advertise model support.
```

This caused the agent session to initialize (handshake, model listing) but never receive the prompt. No `agent_message_chunk` events appeared in output. Fixed 2026-06-02 by extending the skip list to include opencode and codex alongside pi.

## To select a model for opencode/codex/pi

These providers ignore the ACP `--model` flag. To run a specific model:

1. **opencode**: Set the model in opencode.json, or use the CLI directly: `opencode exec "prompt" --model <model>`
2. **codex**: Set via `codex config`
3. **pi**: Set via `acpx pi set model <provider/model> -s <session>` or Pi's settings/session UI

Or modify the agent's config before dispatching via ACP, then restore after.

## Open question (surfaced to Opus via upward handoff)

Should we centralize model selection in roles.toml and fix the adapters, or decentralize to agent configs and simplify roles.toml to just provider type?
