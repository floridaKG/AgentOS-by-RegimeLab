---
name: changes-review
description: After applying fixes from stumble reports or closure findings, produce a traceable audit document — every change mapped to its source finding, every deferred decision surfaced with full context — and place it in the handoffs directory ready for upward review by a higher-reasoning model.
trigger:
  - /changes-review
  - review changes
  - audit what we changed
  - prepare for upward review
  - trace changes back
  - surface remaining decisions
  - changes review
scope: agent-os
status: stable
version: "1.0"
user-invocable: true
allowed-tools: Read, Write, Bash
best-with: any model — produces a document for Opus to review, so the producing model does not need to be Opus itself
companion-docs:
  - $AGENT_OS_HOME/docs/HANDOFF_AUTHORING_STANDARD.md
  - $AGENT_OS_HOME/docs/AGENT_REPORT_CONVENTIONS.md
  - $AGENT_OS_HOME/DOC_TAXONOMY.md
last_reviewed: 2026-06-15
---

# changes-review

Produce a traceable audit document after a batch of fixes has been applied from stumble reports, closure summaries, or audit findings. The document maps every applied change to the specific finding that drove it, surfaces remaining/deferred decisions with full context for a higher-reasoning reviewer, and includes the session trace ID so the work can be fully replayed.

This skill is safe to run from any agent (Claude, Hermes, opencode). It reads and writes — no destructive operations.

---

## When to run this

Run after any session where:
- Fixes were applied from a multi-packet closure brief or stumble report
- Some issues were deferred or require architectural judgment
- The owner or orchestrator needs to hand the work to a higher-reasoning model for sign-off

Do NOT use as a replacement for `AGENT_REPORT_CONVENTIONS.md` end-of-task blocks — those are task-completion reports. This skill produces a *review-ready brief*, not a task report.

---

## Step 1 — Identify the source documents

Locate the parent documents that drove the changes. These are typically:

- A closure summary: `$AGENT_OS_HOME/handoffs/archive/<date>/...-platform-closure-summary-....md`
- Individual packet reports: `$AGENT_OS_HOME/handoffs/archive/<date>/architect__to__owner__*.md`
- The stumble store: short-term memory (`memory-st query --intent STUMBLE`), or a triage report under `~/.local/state/agent-os/stumble-reports/`

Read the STUMBLES sections from each. These are the findings. Every change made this session must trace to one of them.

If no parent doc exists, reconstruct the finding list from the git diff or from your session context before proceeding.

---

## Step 2 — Reconstruct the change list

For each change applied this session, collect:

| Field | What it means |
|---|---|
| Finding | Exact quote or ID from the source doc that triggered this change |
| File changed | Absolute path |
| What changed | One sentence — the old behaviour vs the new behaviour |
| Evidence | A literal command or diff that proves the change is correct (not a paraphrase) |
| Residual risk | Anything a reviewer should know about edge cases or side-effects |

If you applied a change without a traceable source finding, flag it as `UNDOCUMENTED` — the reviewer needs to know.

---

## Step 3 — Reconstruct the deferred list

For each issue that was NOT fixed this session:

| Field | What it means |
|---|---|
| Finding | Source stumble / audit finding |
| Current state | What exists on disk right now (verified, not assumed) |
| What would need to happen | Concrete steps, not vague intentions |
| Reviewer must decide | The specific question that needs judgment — failure modes, scope, side-effects |
| Risk if done wrong | Why this was deferred rather than executed |

---

## Step 4 — Find the session trace ID

```bash
# Claude Code session ID is available in the environment
echo $CLAUDE_CODE_SESSION_ID

# If not set, find the most recent transcript
ls -t ~/.config/agent-os/projects/*/*.jsonl 2>/dev/null | head -1
```

Record both the session ID and the transcript path. This lets the reviewer or any future agent replay the full session if needed.

---

## Step 5 — Write the review document

**Filename convention:**
```
$AGENT_OS_HOME/handoffs/<from>__to__opus__<topic>-upward-review__<YYYY-MM-DD>.md
```

Examples:
- `claude__to__opus__platform-fixes-upward-review__2026-05-16.md`
- `<agent>__to__opus__acp-fixes-upward-review__2026-05-17.md`

**Document structure** (required sections in order):

```markdown
---
title: <Topic> — Upward Review (changes + N open decisions)
from: <agent-id> · session <SESSION_ID> · <date>
to: Higher-reasoning model (Opus) — review and decide
status: READY_FOR_REVIEW
sentinel: <topic>-upward-review-<YYYY-MM-DD>-v1
read_time_min: <estimate>
origin_brief: <absolute path to parent doc>
---

# <Title>

## Purpose
[2–3 sentences: what this session did and what the reviewer needs to decide]

## Traceability: Parent Chain
[ASCII tree showing the parent docs that drove the changes]

## Section 1 — Changes Applied (N of M issues)
[One subsection per fix — see Step 2 fields]

## Section 2 — Open Decisions (M-N issues, deferred)
[One subsection per deferred item — see Step 3 fields]

## Section 3 — Residual Audit Items (optional)
[Observations that are neither fixes nor decisions — things the reviewer should know]

## ARTIFACTS
[Per AGENT_REPORT_CONVENTIONS.md — every file created or modified, grouped by repo]

## STUMBLES
[Per AGENT_REPORT_CONVENTIONS.md — anything blocked, worked-around, or uncertain]

## CONFIRMED
[Per AGENT_REPORT_CONVENTIONS.md — surfaces touched without stumbling]

## Reviewer Checklist
[Checkbox list of what the reviewer must sign off on or decide]

**Session trace:** <SESSION_ID>
**Transcript location:** `$AGENT_OS_HOME/state/projects/<workspace-slug>/<SESSION_ID>.jsonl`
```

---

## Step 6 — Register the document

After writing, tell the user (or orchestrator) the file path and the two key things they need to hand to the reviewer:

1. The document path
2. The session ID (for traceability)

Do NOT dispatch to the reviewer yourself — this skill produces the document. Dispatch is the owner's decision.

---

## Quality rules

- **Every change must have a traceable source finding.** If you cannot find the finding, write `UNDOCUMENTED` — do not invent one.
- **Evidence must be literal output**, not a paraphrase. Quote the exact line changed, the exact grep result, or the exact command output.
- **Deferred items must state what the reviewer must decide**, not just describe the problem. The reviewer is reading to make a call, not to re-investigate.
- **No prescriptions in the deferred section.** Present options and trade-offs; let the reviewer choose.
- **Session ID is mandatory.** If `$CLAUDE_CODE_SESSION_ID` is not set and no recent transcript can be found, note it explicitly rather than omitting the field.

## Commit boundary audit (when reviewing a dirty working tree)

When you run this skill after a multi-agent session, the working tree will almost always contain files that the current session did NOT touch — pre-existing dirty files from a previous workstream (e.g. W8 hardening, prior feature). `git add .` will sweep all of them into the same commit. The review document must surface this.

**Add a "Commit Boundary" section listing:**

| Group | Files | Touched this session? | Risk if committed together |
|---|---|---|---|
| This session's claimed work | `<list>` | Yes | None — they're the deliverable |
| Pre-existing dirty files in same tree | `<list from git status>` | No | Reverts become atomic; can't back out one without the other |

The risk column matters. A user_regimes fix landing alongside W8 hardening means reverting the user_regimes fix requires reverting W8 too. The right answer is usually two commits; the review should recommend the split explicitly, not just note it.

**Source command:** `git status --porcelain` lists every modified/untracked file. Diff against the current `HEAD` with `git diff --name-only HEAD` to see only what THIS branch has dirty.

**When the review produces a "go commit" recommendation, the recommendation must specify the file list** (`git add AGENTS.md docs/superdocs/ tests/api/routers/ src/api/routers/user_regimes.py`), not the action (`git add .`).

**Confirmed 2026-06-20:** A 25-file W8 dirty list was bundled with a 14-file agent-session deliverable in a single `git status` view. Without the commit-boundary section, the user would have done `git add .` and lost the ability to revert the user_regimes fix in isolation.

---

## Example invocation

After a batch of fixes from a closure report:

```
/changes-review
```

Or with explicit context:

```
/changes-review
Source docs: $AGENT_OS_HOME/handoffs/archive/2026-05/architect__to__owner__platform-closure-summary__2026-05-15.md
Topic: platform-fixes
```
