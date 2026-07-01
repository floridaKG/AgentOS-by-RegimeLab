# pi Tool Model — Native Capabilities

## Evidence

The pi agent has three native execution tools:

- `bash` — intercepts shell commands. Blocks destructive ops, git writes, and sensitive path access.
- `read` — intercepts file reads. Same pattern: checks for sensitive paths, blocks or allows.
- `edit` — intercepts file edits. Same pattern.

The agent-os-bridge extension registers additional custom tools:
agent_os_status, workspace_context, memory_recall, memory_write,
memory_promote, acp_dispatch, acp_status, read_handoff.

## The sidecar vs delegate_task distinction

| Dispatch mechanism | Tool behavior |
|---|---|
| **sidecar** (bash wrapper around `acpx pi exec`) | pi has full bash/read/edit. The bridge only blocks destructive/sensitive operations. The sidecar IS an execution partner. |
| **delegate_task** (Hermes native subagent) | Tools ARE filtered by the `toolsets` parameter. |
| **ACP roles** (via `acp-task executor ...`) | Routes through roles.toml. Tool availability depends on the target agent/role. |

## sidecar-heavy

The heavy variant runs the same pi agent with the same technical toolset.
Its charter explicitly instructs "You have no tools. No execution. No
commands. No code." — this is a behavioral instruction, not a technical
limitation.

## Verifying live

```bash
acpx pi status -s <session-name>
```

To probe tool availability directly, spawn a sidecar and ask it to list
its tools, then ask it to run a simple command like `which python3`.
