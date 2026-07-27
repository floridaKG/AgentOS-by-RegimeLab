---
title: Agent OS Boot — Intent Router
last_updated: 2026-06-25
status: active
source_of_truth: $AGENT_OS_HOME/BOOT.md
---

**Purpose:** translate a user request into the right workspace + skill in one read.
Read this after `$AGENT_OS_HOME/AGENTS.md` and `bash $AGENT_OS_HOME/scripts/agent-os-boot.sh`
when a task needs the runtime intent router.

---

## Intent Match Table

Match the user's request against the **Trigger** column (top-down, first match wins).
Then run the listed **Boot** sequence and **Skill/Tool** entry.

| Trigger phrase / intent | Workspace | Boot | Skill / Tool entry |
|---|---|---|---|
| "remember this", "capture lesson", friction signal | cockpit | none | `lesson` skill |
| "recall X", "find lessons about X", "what do we know about X" | cockpit | none | `recall` skill |
| "show me what was learned", "summary of recent lessons" | cockpit | none | `digest` skill |
| "audit docs", "check doc quality" | cockpit | none | `doc-audit` skill |
| "dispatch task to agent", "delegate to" | cockpit | none | `acp` skill |
| "hand off to higher model" | cockpit | none | `upward-handoff` skill |
| "audit changes", "trace fixes" | cockpit | none | `changes-review` skill |

**No match?** Ask one clarifying question — do not guess across workspaces.

---

## Workspace Routing

Workspaces are user-created directories that agents can work in. Each workspace
has its own `AGENTS.md` entrypoint and configuration.

To add a workspace:
1. Create a directory under `$AGENT_OS_HOME/projects/`
2. Add an `AGENTS.md` file as the entrypoint
3. Register it in `registry/workspaces.yaml`

---

## Reading Order

When you boot into a workspace, read in this order:

```
1. AGENTS.md              # what the project is + rules
2. docs/MEMORY.md          # last session — what was done, decisions
3. docs/LESSONS.md         # gotchas + corrections (always-active rules)
```

---

## Token Budget Discipline

- Each skill load costs tokens. Use `skill-rank` and `skill-pack` to load
  only what you need.
- If you must boot a workspace, read in the order above and stop reading
  after the answer is in hand.
