# Model Selection in ACP Dispatch

## Current public behavior

The public distribution supports the providers listed in
`.config/agent-workflows/roles.toml`:

| Provider | Model selection |
|---|---|
| claude | Passed through to ACPx when the model is advertised |
| opencode | Uses the provider's own configuration |
| codex | Uses the provider's own configuration |

The role names accepted by `acp-task` are public workflow roles, not provider
names. Use a role such as `executor`, `reviewer`, or `escalation`, then change
the provider/model mapping in `roles.toml` if needed.

## How model flows from roles.toml

roles.toml defines per-role: `chain[0] = "provider:model"` (e.g. `opencode:opencode/deepseek-v4-flash-free`).

The adapter splits the configured provider/model, then:
- For claude: passes `--model "$MODEL"` to acpx. Works.
- For opencode/codex: the flag is suppressed. The MODEL value is logged but ignored.

## The bug that was fixed

`acp_to_run_agent.sh` originally passed `--model` to ALL non-pi providers. opencode and codex ACP adapters rejected it with a JSON-RPC error:

```
Cannot apply --model "opencode/deepseek-v4-flash-free": the ACP agent did not advertise model support.
```

This caused the agent session to initialize (handshake, model listing) but never receive the prompt. No `agent_message_chunk` events appeared in output. Fixed 2026-06-02 by extending the skip list to include opencode and codex alongside pi.

## To select a model for opencode/codex

These providers ignore the ACP `--model` flag. To run a specific model:

1. **opencode**: Set the model in opencode.json, or use the CLI directly: `opencode exec "prompt" --model <model>`
2. **codex**: Set via `codex config`
Or modify the agent's config before dispatching via ACP, then restore after.
