# Agent Mail

Agent Mail is a lightweight, file-based async messaging system for agents.
No daemon, no server, no external dependencies — messages are JSON files on
disk. Agents can send messages to each other, check their inbox, and read
specific messages.

## Why Agent Mail

ACP is for task dispatch (fire a task at a role and get a result). Agent
Mail is for async communication — leave a message for another agent to pick
up later, pass context between sessions, or notify about completed work
without blocking.

| Feature | ACP | Agent Mail |
|---|---|---|
| Model | Task dispatch with result | Async message passing |
| Blocking | Can wait for result | Fire and forget |
| Routing | Role + workspace | Named agent |
| Persistence | Run artifacts | JSON message files |
| Use case | "Run this analysis on project-a" | "Heads up: the schema migration finished" |

## Commands

```bash
agent-mail send <agent> <subject> [--summary "..."] [--body "..."]
agent-mail inbox [--agent <name>]
agent-mail read <message-id>
```

### Send a message

```bash
agent-mail send claude "Schema migration done" \
  --summary "All 12 tables migrated successfully" \
  --body "Full migration log at /tmp/migration-2026-07-01.log"
```

Supported agents: `claude`, `codex`, `opencode`, `droid`, `hermes`, `pi`.

### Check inbox

```bash
agent-mail inbox                    # all messages
agent-mail inbox --agent claude     # messages for Claude only
```

### Read a message

```bash
agent-mail read msg-20260701-001
```

## How it works

Messages are stored as JSON files in `$AGENT_OS_HOME/mail/`. Each message
is a single file:

```json
{
  "id": "msg-20260701-001",
  "from": "codex",
  "to": "claude",
  "subject": "Schema migration done",
  "summary": "All 12 tables migrated successfully",
  "body": "Full migration log at /tmp/migration-2026-07-01.log",
  "timestamp": "2026-07-01T12:00:00Z",
  "read": false
}
```

## When to use Agent Mail vs ACP

- **Use Agent Mail** when: leaving context for a future session, notifying
  about completed background work, passing non-urgent information between
  agents, building a paper trail.
- **Use ACP** when: you need a result back, the work is self-contained,
  you want role-based routing with workspace awareness, you need timeout
  and retry handling.
