# Multi-Agent Review Pattern

Three-phase review workflow that produces higher-quality results than any single review pass.

## The Three Phases

### Phase 1: Self-Diagnosis
The agent that has the problem examines its own system and produces findings.
Framing matters: give the agent its own rollout files, its own logs, its own
state databases.

**Why it works:** The agent has context we don't — it lived through the
failures. It knows what it tried, what hung, what returned nothing.

**Dispatch example:**
```
acp-task <agent> <workspace> "Read your own run artifacts. Identify
the root causes of [specific failures]. Write findings to [path]."
```

### Phase 2: Adversarial Review
A second agent critiques the proposed fixes from Phase 1. Assumes the
proposal is wrong. Hunts for the strongest disconfirming evidence.

**Key framing:** "You are doing an adversarial review of a PROPOSED FIX.
Your job is to find flaws, edge cases, and risks — NOT to approve it."

### Phase 3: Second Opinion
A third agent (different model recommended) does an independent review of ALL
changes. Not adversarial — thorough. Checks correctness, edge cases,
integration risks.

**Value:** Catches bugs that both the original author and the adversarial
reviewer missed.

## When to Use

- Infrastructure changes (sidecar, ACP, dispatch systems)
- Architecture decisions with multiple valid approaches
- Any change where "does this actually work?" matters more than "is this clever?"

## When NOT to Use

- Simple bug fixes (one agent is enough)
- Documentation-only changes
- Tasks with clear, testable success criteria (just run the tests)

## Key Lesson

Self-diagnosis forces the agent to articulate WHY the failure happened, not
just WHAT happened. The adversarial phase finds the flaws in the proposed fix.
The second opinion catches bugs that both previous phases missed.
