---
id: adversarial-review
name: adversarial-review
trigger:
  - adversarial review
  - critique this
  - poke holes in this
  - what's wrong with this
  - challenge my reasoning
  - find the flaws
  - red-flag this
  - /adversarial-review
scope: cross-workspace
status: active
description: >
  Adversarial critique of the current ask or work product via an ACP-dispatched
  reviewer agent with context prefill. The reviewer assumes the work is wrong and
  hunts for the strongest disconfirming evidence. Produces severity-ranked findings
  and a verdict. One-shot, free-tier.
last_reviewed: 2026-06-15
---

# Adversarial Review — Single-Shot Adversarial Critique via ACP

## What This Is

A one-shot adversarial critique of whatever you're working on: a spec, a decision,
a plan, a reasoning chain, a code change. You provide the **target** (what to
critique) and a **topic** (the domain context). The skill gathers relevant context
from memory tiers via `context-pack`, dispatches a single adversarial reviewer via
ACP on the free tier, and returns a structured verdict with severity-ranked
findings.

## What This Is NOT

| Pattern | Skill | How it differs |
|---|---|---|
| Sequential debate with proposer/attacker/adjudicator | `agent-workflows` redteam | Multi-turn, multi-role, produces Go/No-Go gate |
| **This skill** | `adversarial-review` | **Single dispatch, adversarial rubric, context-prefilled, free-tier** |

## When To Use

- You've written a spec, plan, or design and want a sharp critic before committing
- You're about to make a decision and want the strongest counterarguments surfaced
- You've been reasoning about a problem and want someone to stress-test your logic
- You need a "red team in a box" — fast, free, no orchestration overhead

**Use `agent-workflows redteam` when:** you want a multi-turn adversarial debate with
a formal PASS/FAIL gate on a specific artifact.

## Inputs

| Input | Required | Description |
|---|---|---|
| **target** | yes | The text, spec, code, decision, or reasoning to critique. Can be inline text or a file path. |
| **topic** | yes | The domain context topic. Used to pull relevant context from memory tiers via `context-pack.sh`. |
| **workspace** | no | Target workspace for ACP dispatch. Default: home. |
| **budget** | no | Context-pack byte budget. Default: 8000. |

## Mechanism

### Step 1: Gather Context

```bash
$AGENT_OS_HOME/scripts/context-pack.sh "<topic>" --budget=8000
```

Pulls relevant context from configured memory tiers.

### Step 2: Dispatch Adversarial Reviewer

```bash
acp-task reviewer <workspace> "<objective>" \
  --context "<topic>" \
  --body "<adversarial rubric + target>" \
  --wait
```

### Step 3: Parse and Present

The reviewer output follows the Output Contract below. Parse the verdict and
findings from the returned text.

## The Adversarial Rubric

The reviewer receives this rubric embedded in the `--body` of the dispatch.
It is the core of the skill — it shapes how the reviewer thinks.

```
ADVERSARIAL REVIEW RUBRIC

You are an adversarial reviewer. Your job is NOT to be helpful or agreeable.
Your job is to find the strongest case AGAINST the work presented below.

RULES:
1. ASSUME THE WORK IS WRONG. Start from the position that there are serious
   flaws. Your job is to find them, not to confirm the work is good.
2. HUNT FOR THE STRONGEST DISCONFIRMING EVIDENCE. Don't settle for minor
   nitpicks. Find the thing that would actually break the reasoning, invalidate
   the spec, or cause the decision to fail.
3. BE SPECIFIC. "This might have edge cases" is worthless. Name the edge case.
   "This assumption about X is wrong because Y" is what we need.
4. RANK BY SEVERITY. Not all flaws are equal. Use:
   - BLOCKER: Fundamentally breaks the work. Must be fixed before proceeding.
   - MAJOR: Significantly weakens the work. Should be fixed.
   - MINOR: Worth knowing but not blocking.
5. STATE WHAT WOULD CHANGE THE VERDICT. For each finding, note what evidence
   or fix would neutralize it. This prevents infinite adversarial spirals.

OUTPUT FORMAT:
## Verdict
<BLOCKED | PROCEED WITH FIXES | CLEAR> + one-paragraph rationale

## Findings
| # | Severity | Finding | What would neutralize it |
|---|----------|---------|--------------------------|
| 1 | BLOCKER/MAJOR/MINOR | ... | ... |

## Strongest Counter-Argument
The single most compelling case against this work, stated as forcefully as possible.

## What Would Make This Airtight
The 2-3 changes that would most strengthen the work against adversarial critique.
```

## Output Contract

```
## Verdict
<BLOCKED | PROCEED WITH FIXES | CLEAR>

## Findings
| # | Severity | Finding | What would neutralize it |
|---|----------|---------|--------------------------|

## Strongest Counter-Argument
<one paragraph>

## What Would Make This Airtight
<2-3 bullet points>
```

**Verdict semantics:**
- `BLOCKED` — at least one BLOCKER finding stands. Do not proceed until fixed.
- `PROCEED WITH FIXES` — MAJOR findings exist but no BLOCKERS. Fix before committing.
- `CLEAR` — no BLOCKER or MAJOR findings. Proceed, noting MINOR items.

## Usage

### CLI (driver script)

```bash
# Critique a spec with domain context
$AGENT_OS_HOME/skills/shared/adversarial-review/adversarial-review.sh \
  /path/to/spec.md "backtest methodology"

# Critique inline text
echo "We should use MAE instead of Sharpe for the optimization objective." | \
  $AGENT_OS_HOME/skills/shared/adversarial-review/adversarial-review.sh \
  - "strategy optimization"

# Critique with explicit workspace
$AGENT_OS_HOME/skills/shared/adversarial-review/adversarial-review.sh \
  /tmp/plan.md "data pipeline" --workspace <workspace>
```

### Manual (from any agent)

1. Read the target material
2. Run `$AGENT_OS_HOME/scripts/context-pack.sh "<topic>"` to gather context
3. Construct the adversarial rubric (copy from above)
4. Dispatch: `acp-task reviewer <ws> "Adversarial review" --context "<topic>" --body "<rubric>\n\nTARGET:\n<material>" --wait`
5. Parse the verdict and findings from the output

### Self-Administered Adversarial Review (No ACP)

When you have the reasoning capacity to act as the adversarial reviewer yourself,
use this variant. It's faster (no dispatch latency) and keeps the critique inside
your context window.

| Factor | ACP Dispatch | Self-Administered |
|--------|-------------|-------------------|
| Latency | ~130s (free tier) | Instant |
| Objectivity | External reviewer, no context bias | Risk of defending your own work |
| Iteration | Must re-dispatch for each round | Inline — refine and re-test in same turn |
| Best for | Formal gating before commit decisions | Exploratory, multi-pass idea development |

**The Pattern:**

1. **Build the full case first** — extrapolate implications systematically.
2. **Then switch to adversarial mode.** Apply the adversarial rubric to your own work.
3. **Separate narrative from substance.** Mark which claims are STRONG, WEAK, or OPEN.
4. **Deliver the refined thesis** — what survived, what didn't, and what the
   unresolved tensions are.

## Safety

- Free-tier dispatch only — no paid models burned for critique
- Single-shot — no loops, no multi-turn, no cost escalation
- Read-only reviewer — the reviewer critiques but does not modify files

## Relationship to Other Skills

| Skill | When to use instead |
|---|---|
| `agent-workflows` redteam | Need multi-turn debate with formal PASS/FAIL gate |
| `upward-handoff` | Need to prepare findings for a higher-reasoning model to analyze |
| `changes-review` | Need to trace applied changes back to their source findings (audit, not critique) |

## Pitfalls

- **Reviewer is free-tier.** The adversarial rubric is sharp, but the model is
  smaller than escalation-tier. For high-stakes decisions, follow up with an
  escalation dispatch for a second opinion.
- **Context-pack may return sparse results.** If the topic is new or niche, memory
  tiers may have nothing. The review still works — it just lacks memory context.
- **One-shot means no follow-up within this skill.** If you need to push back on
  the reviewer's findings, dispatch again with the revised target.
- **The free-tier reviewer can stall.** Do NOT block indefinitely waiting for it.
  If no output by ~150s, kill it and synthesize from your own empirical tests
  instead.
