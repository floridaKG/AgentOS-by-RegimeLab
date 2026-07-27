# Refactor Heavyweight Reference

## Source-of-Truth Map (SOT)

For every important concept, data type, workflow, or contract in the system, identify the canonical source.

| Concept | Canonical Source | Legacy Source | Bridge/Compat Layer | Status |
|---------|-----------------|---------------|--------------------|--------|
| `[concept]` | `[path]` | `[path]` | `[path]` | `[STATUS]` |

**Status values:** MIGRATING, PENDING, LEGACY, DEPRECATED, UNKNOWN

### Source-of-Truth Rules

1. **Writes flow to canonical source.** Legacy sources may be read-only during migration.
2. **Bridges exist only to translate.** No business logic in bridge code.
3. **A DEPRECATED status means the next edit deletes the file.**
4. **UNKNOWN status is blocking.** No implementation task may depend on an UNKNOWN source of truth.

### SOT Runtime Verification Requirement

**The SOT map is a hypothesis, not truth.** Every entry must include a runtime verification step.

---

## Decision Log (ADR Format)

### ADR-001: `[Title]`

| Field | Value |
|-------|-------|
| **Date** | `YYYY-MM-DD` |
| **Owner** | `[name]` |
| **Context** | `[what prompted the decision]` |
| **Decision** | `[the choice made]` |
| **Options Considered** | `[option A, option B, option C]` |
| **Rejected Alternatives** | `[rejected options with reasons]` |
| **Reason** | `[why this was chosen]` |
| **Evidence** | `[evidence that supported the decision]` |
| **Consequences** | `[positive and negative]` |
| **Reversal Cost** | `[HIGH/MED/LOW: explanation]` |
| **Status** | `[PROPOSED / ACCEPTED / DEPRECATED / SUPERSEDED by ADR-N]` |

---

## Anti-Pattern Quick Reference

| Anti-Pattern | Signal | Correction |
|-------------|--------|-----------|
| Parallel editing of same file | Two subspecs list the same file | Orchestrator must serialize or split into layers |
| "Cleanup" task in execution queue | Status PENDING, no legacy handling | Reject or reclassify |
| Bridge with conditional logic | `if legacy else new` in bridge code | Bridge is not a router; split into two handlers |
| Agent finding not integrated | Finding sits in Inbox with no orchestrator decision | Block execution until resolved |
| Untestable goal | Goal section has no checks | Rewrite until every criterion is a command |
| Implementation before blocking Q answered | Task references UNANSWERED Q | Move dependent tasks to BLOCKED |
| Legacy test still passing | Test verifies behavior of a deleted path | Delete test, don't update |
| "We'll fix it later" | ADR with no reversal cost or date | ADR must have a date and trigger condition |

---

## File Ownership Rules

1. **Every file in the refactor scope is owned by exactly one subspec.**
2. **A file with LEGACY status may be read by any agent but edited only by its owning subspec.**
3. **A bridge/compat layer file must have an expiration date.**
4. **The umbrella doc is owned by the orchestrator. No agent edits it directly.**
5. **If a file needs changes from two subspecs, the orchestrator creates a layer task that sequences them.**

### Bridge Expiry Enforcement

Every bridge entry MUST have:
- An ISO expiration date
- A count of callers that must be migrated before deletion
- A circuit-breaker: if the bridge hasn't been deleted by the expiration date, CI fails

---

## Full Gate Checklist (12 Sections)

### Gate 1: Pre-Implementation Review

- [ ] Blocking questions resolved
- [ ] Current State has evidence for every claim
- [ ] Non-goals are specific
- [ ] SOT entries have runtime verification
- [ ] Research assignments are narrow with stop conditions
- [ ] Bridge expiry dates set
- [ ] Goal is testable
- [ ] File ownership declared
- [ ] Orchestrator constraints clear
- [ ] Parallel vs. serial sequencing declared

### Gate 2: Per-Subspec Review

Before any implementation task is committed, the adversarial reviewer must ask:

1. Does this work directly advance the stated end state?
2. Is it optimizing a path that should be removed?
3. Does it preserve a legacy dependency?
4. Is there a simpler or more correct path?
5. What assumptions are unproven?
6. What could fail in production?
7. What tests would prove this is correct?

### Gate 3: Pre-Completion Review

- [ ] Run all verification commands from Goal sections
- [ ] Search for remaining imports from legacy modules
- [ ] Check that no bridge/compat layer still has non-zero lines of business logic
- [ ] Verify every legacy inventory entry has a disposition
- [ ] Run the test suite
- [ ] Check that no tasks remain open
