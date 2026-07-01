---
id: digest
name: digest
trigger:
  - /digest
  - /digest <window>
  - show recent activity
  - what was learned
scope: cockpit
status: stable
description: Print a clean human-readable summary of recent memory across all tiers. The user-facing "what has the agent OS learned lately" view. Triggers on "/digest", "/digest <window>", "show me what was learned", "summary of recent lessons".
version: "1.0"
user-invocable: true
allowed-tools: Read, Bash
last_reviewed: 2026-06-15
---

## Purpose

The user's window into the memory system. Run `/digest` and see a clean
markdown summary of:
- Recent lessons (cross-cutting + per-workspace)
- Recent memory entries (cockpit decisions, workspace memory)
- Last session log lines from the vault
- Pending TODOs / decisions

No Claude conversation required for the basics — `digest` is also a shell
command (`~/.local/bin/digest` symlink) so the user can run it from any
terminal.

---

## Execute

### `/digest` (default — last 7 days)

```bash
memory-st query --limit 20
```

### `/digest <window>`

Window: `1d`, `7d`, `30d`, `90d`, or `all`.

```bash
memory-st query --limit 50
```

### `/digest <topic>`

Filter to entries matching a keyword (case-insensitive).

```bash
memory-st query --text "<topic>" --limit 20
```

---

## Output Format

```
═══════════════════════════════════════════════════════════════
DIGEST — last 7 days (2026-04-25 → 2026-05-02)
═══════════════════════════════════════════════════════════════

▸ Cockpit Lessons (3)
  - 2026-05-01 [claude] Use the cockpit `lesson` skill, not raw memory writes
  - 2026-04-30 [claude] ...

▸ Workspace Lessons
  Project B (1) — drop_warmup default conflict resolved
  Project A (2) — apiFetch double-stringify fixed; TV timeframe normalization

▸ Cockpit Memory (2)
  - 2026-05-01 Cockpit OS scaffolding shipped
  - 2026-05-02 Memory system unification — single doc + recall + digest

▸ Last 5 vault sessions
  | 2026-05-01 | claude  | cockpit | Built $AGENT_OS_HOME/ layer       |
  | ...

▸ Pending decisions / TODOs (from cockpit memory.md)
  - Project A API endpoint schema — awaiting confirm (now resolved 2026-05-02)
  - Pinecone API key — still needed for live vault index
═══════════════════════════════════════════════════════════════
```

---

## Why This Exists

The user said: "I just need a way for you, the other agents, and myself to
remember everything." `/digest` is the **user's** read interface. `/recall`
is the **agent's** search interface. Both surface the same underlying tiers
documented in `memory/README.md` (five tiers, three backends).

If you're an agent: run `/recall` to find specific things. If you're the
user: run `/digest` to see the rolling state.
