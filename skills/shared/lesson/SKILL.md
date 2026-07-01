---
id: lesson
name: lesson
trigger:
  - /lesson
  - /lesson [text]
  - remember this for next time
  - capture this lesson
scope: cockpit
status: stable
description: Capture a cross-workspace or cockpit-level lesson. Routes to the right destination by scope. Use when you hit friction, get a methodology correction, or notice a pattern that future sessions should know. Triggers on "/lesson", "/lesson [text]", "remember this for next time", "capture this lesson".
version: "1.0"
user-invocable: true
allowed-tools: Read, Write, Edit, Bash
last_reviewed: 2026-06-15
---

## Purpose

Capture operational learnings at the cockpit level and route them to the
correct destination. Mirrors the vault's `remember` skill but operates at the
WSL global tier where insights might span workspaces or apply to the agent OS
itself.

This is for **operational intelligence** — friction, corrections, patterns.
Domain knowledge belongs in the vault (`/extract`).

---

## Routing Decision

Before writing, classify the lesson by scope:

| Question | If yes → Destination |
|---|---|
| Does it apply in 2+ workspaces, or to the agent OS / cockpit itself? | Agent OS ST (`memory-st write --intent LESSON`) → auto-generates `$AGENT_OS_HOME/lessons.md` |
| Is it strictly Project B? | `<project-b>/docs/LESSONS.md` |
| Is it strictly Project A? | `<project-a>/docs/LESSONS.md` |
| Is it strictly the vault? | `<vault>/docs/vault-os/LESSONS.md` |
| Is it about the user (role, preference)? | `$AGENT_OS_HOME/state/memory/` (NOT this skill — use auto-memory) |

**Note:** All cockpit-level lessons now flow through Agent OS ST as the canonical
write path. The `$AGENT_OS_HOME/lessons.md` file is a generated projection from ST
records (weekly cron + immediate regeneration after write). Do NOT edit
lessons.md directly.

Workspace paths (resolved from `config.env`):
- project-a, project-b, and vault: user-configured via `config.env`
Run `cat $AGENT_OS_HOME/config.env` to see all configured workspace paths.

---

## Execute

### `/lesson [observation text]`

1. **Classify the scope** using the table above. If ambiguous, default to
   cockpit scope (broader is safer than narrower).

2. **Classify the type:**
   - `friction` — slowed down or frustrated the workflow
   - `correction` — methodology behavior that needs changing
   - `pattern` — worked unexpectedly well, should be repeated
   - `architecture` — structural change to OS, workspace, or skill registry

3. **Write to Agent OS short-term memory (canonical write path):**
   ```bash
   # Write content to temp file
   CONTENT_FILE=$(mktemp /tmp/lesson-XXXXXX.txt)
   cat > "$CONTENT_FILE" << 'LESSON_EOF'
   **Why:** [what failure or constraint caused this]
   **How to apply:** [when this kicks in, where to check]
   LESSON_EOF

   $AGENT_OS_HOME/bin/memory-st write \
     --run-id "${RUN_ID:-lesson-$(date +%Y%m%d-%H%M%S)}" \
     --agent-id "${AGENT_ID:-claude}" \
     --workspace home \
     --intent LESSON \
     --kind observation \
     --summary "[one-line rule]" \
     --content-file "$CONTENT_FILE" \
     --source-ref "cli:lesson" \
     --boundary-kind brain \
     --evidence-ref "cli:lesson"
   ```
   This writes the lesson to Agent OS ST (the canonical store). All agents
   can read it via `memory-st query`.

4. **Verify the lesson is stored** (check it's queryable):
   ```bash
   memory-st query --text "<lesson summary>" --limit 1
   ```
   The lesson is now in short-term memory and available for recall.

5. **If type is `correction` and urgent** (rule violation in active code,
   not a future-triage item), apply the fix immediately to the relevant file
   in addition to logging.

6. **If type is `architecture`,** also append a line to `$AGENT_OS_HOME/memory.md`
   noting the structural change.

7. **Confirm:** reply with one line — `Logged [type] lesson to Agent OS ST. lessons.md updated.`

### `/lesson` with no argument

Show the 5 most recent entries from Agent OS ST LESSON records:

```bash
$AGENT_OS_HOME/bin/memory-st query --text "lesson" --intent LESSON --limit 5
```

---

## Quality Gates

- Lesson is **specific** — not "this could be better" but "X behavior in Y
  context caused Z".
- **Why is mandatory.** A lesson without a Why is unmaintainable; future
  agents can't judge edge cases.
- **How to apply is mandatory.** A lesson without an action surface is just
  trivia.
- **Verify before theorizing.** Before proposing a root cause, check existing
  handoffs and session history. If the issue was already
  diagnosed, reference the existing analysis instead of re-investigating.
- One lesson per `/lesson` invocation. Multiple observations → multiple calls.

---

## Promotion to Skill or Rule

If the same lesson recurs in 2+ sessions, follow the promotion ladder in
`$AGENT_OS_HOME/self-learning.md`:

- Recurring decision pattern → entry in `$AGENT_OS_HOME/BOOT.md`
- Recurring procedure → new skill in `$AGENT_OS_HOME/skills/`
- Recurring friction with the OS itself → upgrade `~/AGENT_OS.md` or
  `~/AGENT_OS_INDEX.md`

## Architecture Note

 Lessons are stored in short-term SQLite memory via `memory-st write`.
 The write path is: Agent → Agent OS ST (`memory-st write --intent LESSON`).

 Lessons can be queried with `memory-st query` or `memory-recall`.
 The `/lesson` skill writes directly to ST for immediate availability.

 All lessons must flow through ST. Do not edit memory files directly.
