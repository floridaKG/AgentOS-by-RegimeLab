# Lesson capture

## Purpose

The lesson capture system allows agents to record operational learnings — friction points, methodology corrections, effective patterns, and architectural decisions — and persist them in short-term memory for cross-session recall. The `/lesson` skill provides a natural-language trigger for agents to log observations without leaving their workflow.

## How it works

Lesson capture flows through four main steps:

1. **Trigger** — an agent invokes `/lesson [observation text]` or describes something worth remembering.
2. **Scope classification** — the lesson is classified by scope using a routing table: cockpit-level (applies to 2+ workspaces or Agent OS itself), workspace-specific (project-a, project-b), vault-specific, or user-specific.
3. **Type classification** — the observation is tagged as `friction` (slowed workflow), `correction` (methodology change), `pattern` (worked unexpectedly well), or `architecture` (structural change).
4. **Write to short-term memory** — the lesson is written to SQLite short-term memory via the `memory-st write --intent LESSON` command, which auto-generates a projection to `$AGENT_OS_HOME/lessons.md`.

The supported intents for lesson capture are:

| Intent | Purpose |
|--------|---------|
| `LESSON` | Reusable operational learning |
| `STUMBLE` | Something that went wrong or caused friction |
| `DECISION` | A recorded decision with rationale |
| `CONFIRMED` | A hypothesis that was verified |

### Scope routing

| Scope | Destination | When |
|-------|-------------|------|
| Cockpit / cross-workspace | Agent OS ST (`memory-st write --intent LESSON`) | Applies to 2+ workspaces or Agent OS itself |
| Project A | `<project-a>/docs/LESSONS.md` | Strictly project-specific |
| Project B | `<project-b>/docs/LESSONS.md` | Strictly project-specific |
| Vault | `<vault>/docs/vault-os/LESSONS.md` | Strictly vault-specific |
| User (role, preference) | `$AGENT_OS_HOME/state/memory/` | Personal settings |

### Promotion pipeline

Lessons stored in short-term memory can be promoted to long-term storage:

- **Recurring decision pattern** → entry in `$AGENT_OS_HOME/BOOT.md`
- **Recurring procedure** → new skill in `$AGENT_OS_HOME/skills/`
- **Recurring friction with the OS** → upgrade `~/AGENT_OS.md` or `~/AGENT_OS_INDEX.md`
- **Auto-promote** to Pinecone (if configured)
- **Graph-promote** to Neo4j (if configured)

## Integration points

Memory promotion (`memory/core/promote.py`) reads from short-term SQLite and writes to Neo4j graph memory and Pinecone vector memory. The `recall_hook.py` injects relevant prior lessons into agent sessions automatically. The `memory-st` CLI is the canonical write path used by both the `/lesson` skill and direct agent scripts.

## Key source files

| File | Purpose |
|------|---------|
| `skills/shared/lesson/SKILL.md` | The `/lesson` skill definition and execution instructions |
| `bin/memory-st` | Short-term memory CLI wrapper (delegates to `memory/core/short_term.py`) |
| `memory/core/short_term.py` | SQLite short-term memory backend with write, query, and FTS5 search |
| `memory/core/promote.py` | Promotion pipeline from short-term to long-term memory (graph + vector) |
| `memory/core/schema_short_term.sql` | SQLite schema for short-term memory records and FTS5 virtual table |
