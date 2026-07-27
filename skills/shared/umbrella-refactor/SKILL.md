---
name: umbrella-refactor
description: Manage large refactors via an umbrella doc (master index) that links to individual spec files along a timeline. Each workstream gets its own self-contained spec; the umbrella tracks state, dependencies, and critical path.
trigger:
  - umbrella refactor
  - master plan
  - multi-spec refactor
  - wave-based work
  - refactor umbrella
  - create umbrella
  - new workstream
  - add spec
  - update umbrella
scope: workspace
status: stable
version: "1.0"
user-invocable: true
last_reviewed: 2026-06-15
---

# umbrella-refactor

Manage large refactors via one umbrella doc (master index) that links to individual spec files. Each workstream gets its own self-contained spec; the umbrella tracks state, dependencies, and critical path.

---

## When to use

Run this skill when starting or continuing a multi-wave refactor with 3+ workstreams.

**Do NOT use for:**
- Single-task work (use standard task-completion flow)
- Simple bug fixes (no umbrella needed)
- Pure research/audit (use `upward-handoff` instead)

---

## Step 1 — Create or locate the umbrella

**If no umbrella exists for this project:**

```
1. Create docs/plans/pending/<PROJECT>_UMBRELLA.md
2. Use the Umbrella Template (below)
3. Fill in: Current State, Architecture (if known), initial Status Board
4. Create placeholder spec files for each planned workstream
```

**If an umbrella already exists:**

```
1. Read the Current State section first
2. Read the Status Board to understand where things stand
3. Read the active spec (the one marked IN_PROGRESS or the next one in dependency order)
4. Do NOT re-derive what's already decided — execute from the spec
```

---

## Step 2 — Add a new spec

When a new workstream is identified:

```
1. Create spec file at docs/plans/pending/WS-<N>_<slug>.md
2. Use the Spec Template (below)
3. Add row to umbrella Status Board
4. Add entry to umbrella Timeline
```

---

## Step 3 — Install specs from an external architect

When an external agent produces a batch of execution specs independently:

```
1. Create wave directories: docs/specs/post-beta/wave-0/ through wave-N/
2. Copy spec files into their wave directories (one spec per file, one wave per directory)
3. Copy the program index (if one exists) to the spec root
4. Rewrite the umbrella as a thin control plane:
   - Keep: owner decisions, wave index pointing to spec files, quick-reference API contracts
   - Remove: duplicated contracts, implementation detail, full models
   - Add: archive index for superseded material
5. Classify every existing document in the spec area
6. Archive superseded material (move to archive/ — never delete)
```

---

## Step 4 — Update after a wave

```
1. Update spec status: IN_PROGRESS → DONE (or BLOCKED)
2. Update umbrella Current State snapshot
3. Add one-liner to Handoff Log
4. Update Status Board row
5. If pivot happened: mark old spec SUPERSEDED, create new version, update Timeline
```

---

## Step 5 — Pivot a spec

```
1. Mark current spec as SUPERSEDED with explanation
2. Create new spec version
3. Update umbrella Timeline with the pivot
4. Update Status Board to point to the new spec
```

---

## Step 6 — Close out the refactor

```
1. Mark all specs DONE in Status Board
2. Archive individual spec files to docs/plans/archive/<YYYY-MM>/
3. Archive umbrella doc to same archive dir
4. Keep the Architecture doc as design record
5. Run doc-audit if needed
```

---

## Umbrella Template

```markdown
# <Project Name> — Umbrella

> Single source of truth for this refactor.

Last updated: YYYY-MM-DD

---

## Current State

| What | Status | Evidence |
|---|---|---|
| <key asset> | <current state> | <how you know> |

## Architecture

<End-state design, rationale, key decisions.>

## Status Board

| WS | Objective | Status | Depends on | Spec | Verified |
|---|---|---|---|---|---|
| WS-1 | <goal> | DONE | — | `WS-1_slug.md` | ✅ |
| WS-2 | <goal> | IN_PROGRESS | WS-1 | `WS-2_slug.md` | — |
| WS-3 | <goal> | NOT_STARTED | WS-2 | `WS-3_slug.md` | — |

## Timeline

| Date | Event |
|---|---|
| YYYY-MM-DD | Project started, umbrella created |

## Open Questions

| # | Question | Status | Blocks |
|---|----------|--------|--------|
| Q1 | `[blocking question]` | OPEN / ANSWERED / REJECTED(reason) | `[which subspecs]` |

All OPEN blocking questions must be resolved before any implementation dispatches.

## Findings Inbox

| Date | Explorer | Finding | Decision | Rationale |
|------|----------|---------|----------|-----------|
| YYYY-MM-DD | `[explorer name]` | `[one-line finding]` | ACCEPT / REJECT / DEFER | `[why]` |

## Handoff Log

| Date | Agent | What happened |
|---|---|---|
| YYYY-MM-DD | <agent> | <one sentence> |

## Incident History

<Append-only. Chronological log of problems, misdiagnoses, and fixes.>
```

---

## Spec Template

```markdown
# WS-N: <Title>

**Status:** NOT_STARTED | IN_PROGRESS | DONE | BLOCKED | SUPERSEDED
**Depends on:** WS-N-1 (or "none")
**Blocks:** WS-N+1
**Owner:** <agent or human>

## Goal

One sentence. What this spec delivers.

## Files

- `path/to/file.py` — what to change

## Steps

1. **Step name.** What to do. Include exact commands/queries.

## Verification Gate

Concrete pass/fail criteria.

```bash
# Verify command here
# Expect: <specific output>
```

**DONE when:** <one-line acceptance condition>

## Rollback

How to undo if it breaks.
```

---

## Quality Rules

- **One umbrella per refactor.** Don't create multiple umbrellas for the same project.
- **Specs are self-contained.** An agent reads ONE spec and executes it without reading the entire umbrella.
- **Umbrella is the routing table.** It links to specs, it doesn't duplicate their content.
- **Current State is always current.** Updated after every deploy/verification.
- **Timeline is append-only.** Never edit past entries.
- **Handoff Log is one-liners.** No verbose explanations.
- **No time estimates.** Work proceeds by wave + verification gate, not by clock.
- **Verification gates are concrete.** "Panel has >=1242 columns" not "panel looks good."

---

## Gate Checklist

Before any implementation begins, the orchestrator must pass these checks.

- [ ] **Bridge expiry enforced.** Every bridge/compat layer entry has an ISO expiration date, a caller count that must reach zero before deletion, and a CI circuit-breaker.
- [ ] **Source-of-Truth map verified at runtime.** The SOT map is a hypothesis, not truth. Every entry is verified at runtime.
- [ ] **Research subagents are narrow.** Every research subagent receives a specific YES/NO or countable question, a hard stop condition, and produces findings only.
- [ ] **Orchestrator does not edit refactor scope.** The orchestrator may not implement anything. Only edits the umbrella doc itself.
- [ ] **One owner per file.** Every file in the refactor scope is owned by exactly one subspec.

For the full 12-section gate mapping, see `references/refactor-heavyweight.md`.

---

## Phase 0 — Discover Current State

Before filling any umbrella section, dispatch three read-only explorer subagents to map the system from independent angles.

### Explorer 1: Runtime Discovery

| Field | Value |
|-------|-------|
| **Mission** | Discover what the system actually does, not what the source code says. |
| **Allowed tools** | Read, Bash (read-only: ls, grep, wc, cat, curl), Grep, Glob |
| **Forbidden** | Any write, delete, migration. May not propose changes. |
| **Research question** | Specific YES/NO or countable question. |
| **Stop condition** | Stops as soon as the question is answered. |

### Explorer 2: Source-of-Truth Mapping

| Field | Value |
|-------|-------|
| **Mission** | Identify every concept with dual implementations and determine which is canonical. |
| **Allowed tools** | Read, Bash (read-only), Grep, Glob |
| **Forbidden** | Any write, delete, bridge creation. |
| **Research question** | Specific YES/NO or countable question. |
| **Stop condition** | Stops when question answered; flags 3+ implementations as design smell. |

### Explorer 3: Dependency & Risk Audit

| Field | Value |
|-------|-------|
| **Mission** | Map every external dependency, scheduled job, and known pain point. |
| **Allowed tools** | Read, Bash (read-only), Grep, Glob |
| **Forbidden** | Any write, lockfile changes, package manager runs. |
| **Research question** | Specific YES/NO or countable question. |
| **Stop condition** | Stops when question answered; every package categorized. |

### Orchestrator Integration

The orchestrator reviews findings, populates Current State and Open Questions,
resolves blocking questions, then gates the first implementation dispatch.

**Constraint:** The orchestrator may not implement anything. It may not edit
any file in the refactor scope. It only edits the umbrella doc itself.

---

## Integration with existing skills

- **upward-handoff**: Use before creating a spec when you have findings but aren't sure about the design
- **changes-review**: Use after implementing a spec to produce traceable audit
- **doc-audit**: Use periodically to catch stale specs or umbrella drift
- **lesson**: Capture lessons from pivots or failures
