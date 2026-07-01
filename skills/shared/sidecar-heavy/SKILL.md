---
id: sidecar-heavy
name: sidecar-heavy
trigger:
  - /sidecar-heavy
  - consult the heavy
  - spawn sidecar heavy
  - get deep reasoning
  - heavy thinking
  - think through this
  - deep dive
  - need a plan
scope: os-shared
status: stable
description: "Spawn a pure-reasoning advisor (heavy model) that you and the regular sidecar consult for deep thinking, plans, and guidance. The heavy sidecar never executes — it only reasons."
version: "1.0"
user-invocable: true
allowed-tools: Read, Bash
last_reviewed: 2026-07-01
---

## Purpose

The **sidecar heavy** is a pure-reasoning companion that does nothing but
think. You (the cheap agent) and the human do the implementation;
the heavy sidecar provides deep reasoning, plans, risk analysis, and
guidance. Think of it as a persistent advisory council you consult on
demand — a cheaper, lower-friction alternative to upward handoff.

This is the inverse of the regular sidecar pattern:
- **sidecar** (cheap) = the execution partner. You reason, it does.
- **sidecar-heavy** (expensive) = the reasoning partner. It thinks, you do.

## Workflow

```
You + Human  ←→  sidecar-heavy (configured heavy model)
   ↓                          ↑
   └── implement ──→ report results ──→ get refined guidance
```

1. **You and the human** are working on a task (chatting cheaply).
2. When you get stuck, need a plan, or want deep reasoning, you consult:
   ```
   sidecar-heavy "We're working on X. Current state: Y. We need a plan for Z."
   ```
3. The heavy sidecar returns reasoning, guidance, and actionable steps.
4. **You and the human** discuss the guidance, then implement it.
5. Report back to the heavy for refinement if needed.

### Feed-Execute-Report loop

The heavy sidecar is most effective when you **feed it real findings, not
assumptions**. Don't ask it to speculate about code it can't read. Instead:

1. **Probe first.** Use your tools (terminal, curl, docker exec, codegraph)
   to gather actual live evidence: API responses, scheduler logs, DB file
   mtimes, env vars, code paths.
2. **Feed the findings.** Build a structured brief around what you actually
   found, including surprises and contradictions with prior beliefs.
3. **Get the plan.** The heavy reasons from real evidence and gives you a
   priority-ordered action plan with specific risks flagged.
4. **Execute.** Implement the changes in priority order.
5. **Report back.** Share the diff, test results, and any observations that
   challenge the plan for a refinement pass.

This loop avoids the common trap of the heavy making recommendations based
on stale or incorrect assumptions about the system state.

## Interface — `$AGENT_OS_HOME/bin/sidecar-heavy`

```bash
sidecar-heavy init              # create/reset session, brief it on its charter
sidecar-heavy init --resume     # reuse existing session (keep history)
sidecar-heavy "<instruction>"   # send a reasoning prompt, print reply
sidecar-heavy status            # show active model + health
sidecar-heavy cancel            # cancel an in-flight prompt
sidecar-heavy history           # show recent session history
```

Session name defaults to `sidecar-heavy`. Use the trailing `[name]` arg or
`SIDECAR_HEAVY_SESSION` env var for multiple sessions.

## When to consult the heavy sidecar

- **Stuck on a hard problem** — you've tried a few approaches, none work.
- **Need a plan** — a task has 5+ steps, subtle ordering dependencies, or
  risk of cascading failures.
- **Architecture decision** — choosing between approaches with trade-offs.
- **Risk analysis** — you're about to run something destructive and want a
  second set of eyes.
- **Debugging a subtle bug** — error traces make no sense, non-deterministic
  failures, race conditions.

## When NOT to use the heavy sidecar

- **Simple lookups** — just grep or read the file.
- **Rote implementation** — you know exactly what to do, just do it.
- **Error handling you understand** — parse the error, fix, move on.
- **Anything the human can decide in 2 seconds** — don't burn heavy tokens
  on trivial yes/no choices.

The heavy sidecar is a reasoning multiplier, not a crutch. Use it to break
impasses, not to avoid thinking.

## How to write good prompts for the heavy

The heavy model is expensive. Make every consultation count:

1. **State the situation clearly.** What are you doing, what have you tried,
   what's the specific question.
2. **Provide minimal context.** Include error output, plan excerpts, or key
   code snippets — not the whole file.
3. **Ask an explicit question.** "What should we do?" is weak. "Should we use
   approach A or B for problem X, given constraints Y and Z?" is strong.
4. **Tell it what you already know.** Saves the heavy from rediscovering
   things you've already figured out.
5. **Specify output format.** Tell the heavy exactly how to structure its
   response (executive summary, ranked options, per-item analysis, etc.).
   This makes its output immediately actionable rather than narrative.

### Brief structure

For complex multi-pipeline analysis, use this structure. See
`references/brief-template.md` for a fill-in-the-blanks copy.

```
You are a pure-reasoning advisor...

## Context
<3-5 paragraphs giving the driver's perspective: what we're doing, key
architecture constraints, what the user cares about>

## Key constraints
- Bullet list of non-negotiables (e.g. "DuckDB is cold store only")

## What we need from you
<numbered list of specific questions to answer, organized by topic>

## Format for your response
<explicit format instruction, e.g.:
1. Executive summary (3-4 sentences)
2. Priority ranking (1-N, with rationale)
3. Per-item deep dives
4. Open questions>
```

### After receiving the analysis: embed it

The heavy's analysis is an *input to the working doc*, not a chat artifact.
After receiving it:

1. **Distill** the key decisions into the driver document.
   Usually this means creating a "deep-dive context" section under the
   relevant phase heading with the priority ranking, key risks, and
   open questions.
2. **Save** the analysis transcript reference in the session so it's
   traceable, but don't treat the raw reply as the permanent record.
3. **Act on the ranking.** The heavy's priority order directly informs
   the execution ordering for you and the regular sidecar.

## Configuration

| Env var | Default | Description |
|---|---|---|
| `SIDECAR_HEAVY_SESSION` | `sidecar-heavy` | Session name |
| `SIDECAR_HEAVY_MODEL` | (provider-configured) | Model ID for the heavy reasoning model |
| `SIDECAR_HEAVY_TIMEOUT` | `300` | Timeout in seconds |

## Alternative dispatch: Codex MCP

When the sidecar-heavy CLI's model isn't available or the user requests a
model outside the configured catalog (e.g. GPT-5.x via Codex), use the
Codex MCP tool as an alternative dispatch:

```python
# Use mcp_codex_codex with model="gpt-5.5" for heavy reasoning
# The prompt follows the same structure as the sidecar-heavy CLI brief
```

Codex limitations:
- The Codex MCP server does NOT have terminal/file access — it's a
  sandboxed reasoning environment only (which matches the heavy's
  "think only, don't execute" mandate).
- Model availability depends on the Codex subscription tier. Test with
  a short probe before committing a long prompt.
- Codex sessions persist via `mcp_codex_codex_reply` with the thread ID.
  Track the thread ID from the first response for follow-up refinement.

**When to use CLI vs Codex:**
- CLI: default path, model set via SIDECAR_HEAVY_MODEL env var.
- Codex MCP: when user asks for a specific model not in the configured
  catalog, or when you want to run the heavy reasoning alongside a sidecar
  without managing two sessions.

## Relationship to other patterns

- **Upward handoff** — one-shot document pass to a higher-reasoning model.
  Use when the heavy *session* is too big or you need a
  fresh set of eyes with no context bias.
- **Regular sidecar** — execution partner. Cheap model does the work.
  Compatible: run both in parallel with different session names.
- **ACP dispatch** — one-shot task to a role. Use when the work is
  self-contained and doesn't need back-and-forth.
