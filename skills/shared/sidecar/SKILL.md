---
id: sidecar
name: sidecar
trigger:
  - /sidecar
  - spawn a sidecar
  - spawn a sidecar to
  - use the sidecar
  - drive a sidecar
scope: cross-workspace
status: stable
agents: any reasoning-model driver with shell access
description: Pair a higher-reasoning DRIVER agent with a persistent pi execution partner (the sidecar). The driver thinks and decides; the sidecar does the work in a shared persistent session, surfaces issues, and conserves the driver's tokens.
last_reviewed: 2026-06-25
---

# Sidecar — Driver + Persistent Execution Partner

A **sidecar** is a long-lived companion agent you (the **driver**) guide through
a task. You are the reasoning model: you do the thinking, decisions, and
architecture. The sidecar does the doing — running commands, editing files,
searching, verifying — in a **persistent session** that keeps shared state
across turns. It is not a one-shot worker: it remembers prior turns, and its
mandate is to make *you* effective, not just to follow orders. It surfaces
problems, flags bad assumptions, and reports findings you can act on.

This is "two agents going about the same task together": you preserve tokens and
high-level focus; the sidecar carries the execution load and you talk back and forth.

## Prerequisites

The sidecar requires a configured pi agent session via `acpx`. Users must have:

- A pi agent installed and configured
- The `acpx` CLI on PATH
- A sidecar charter at `$AGENT_OS_HOME/.config/agent-workflows/sidecar/charter.md`

## Interface — `$AGENT_OS_HOME/bin/sidecar`

```bash
sidecar init [name]              # create/reset session, set primary model, brief it on its charter
sidecar "<instruction>"          # send an instruction, print the sidecar's reply (auto-fallback)
sidecar prompt "<instruction>"   # explicit form of the above
sidecar status [name]            # show active model + health
sidecar fallback [name]          # manually switch to the fallback model
sidecar primary [name]           # manually switch back to the primary model
sidecar model <id> [name]        # set an arbitrary model id on the session
sidecar cancel [name]            # cooperatively cancel an in-flight prompt
sidecar history [name]           # show recent session history
```

Session name defaults to `sidecar` (override with the trailing `[name]` arg or
`SIDECAR_SESSION`). Use distinct names to run more than one sidecar in parallel.

## Workflow

```bash
# 1. Brief the sidecar once (sets model, loads its charter into shared state).
sidecar init

# 2. Drive it. Each call keeps full session history — don't re-send context.
sidecar "List the failing tests and show the first traceback"
sidecar "Apply the fix we discussed to foo.py line 42, then re-run that one test"

# 3. It surfaces issues back to you; you reason, then dispatch the next step.
```

You (the driver) do NOT need to repeat earlier context — the session persists
and survives crashes.

## The sidecar's charter

On `init`, the sidecar is briefed with
`$AGENT_OS_HOME/.config/agent-workflows/sidecar/charter.md`: execute precisely,
surface issues early, report actionable findings, maintain shared state, ask when
genuinely blocked, and obey non-negotiables. Edit the charter to change standing
behavior for all future sidecars.

## When to use vs. plain ACP

- **Use the sidecar** when you want an ongoing back-and-forth execution partner
  with shared memory across many turns, while you stay in the reasoning seat and
  conserve tokens.
- **Use ACP dispatch** for a single self-contained handoff to a role or model
  where you don't need a persistent conversational loop.
- **Use agent-workflows** for parallel/adversarial multi-agent patterns
  (swarm, council, redteam).

## Sandbox Behavior

The sidecar shell needs outbound network. Inside a
**network-disabled sandbox**, the wrapper detects sandbox environment variables
and routes all commands through ACP as a fallback.

**Detection:** The wrapper checks `CODEX_SANDBOX`, `CODEX_SANDBOX_NETWORK_DISABLED`,
`ACP_SANDBOX`, or `SANDBOX_NETWORK_DISABLED` env vars. `SIDECAR_FORCE=1` overrides detection.

| Command | Sandbox behavior |
|---------|-----------------|
| `init` | Local-only readiness marker |
| `prompt` | Routes through ACP |
| `status` | Reads state file directly |
| `cancel` | Cancels the ACP task |
| `history` | Reports unavailable in sandbox |
| `fallback`/`primary`/`model` | Blocked (require native acpx) |

## Session buffer ceiling

pi keeps the entire session transcript in memory — every turn's thinking,
tool call, file read, and command output, back to session start. The buffer
has a hard ceiling. Cross it and the session aborts.

Two practical consequences:

- **`init` may not give you a clean buffer.** A session under a reused name
  can inherit old history. Before handing a sidecar a big task, check
  `sidecar history [name]` — if it carries unrelated prior turns, start
  a fresh session under a new name instead.
- **Give each substantial task its own session name.** Distinct names are not
  only for parallelism; they also start each task with an empty buffer.

## Pitfalls (learned the hard way)

### Pitfall: Claiming the sidecar has no execution tools

The pi agent that backs the sidecar DOES have execution tools natively
(bash for shell, read for file reads, edit for file writes). Non-negotiables
block destructive ops but the shell itself is fully available.

### Pitfall: Broad briefs produce broad results, not deep dives

If you give the sidecar 5 work packages with 20 sub-questions, it will
do a shallow pass across all 5 instead of a deep dive on any one.

**Rule:** One session, one tight objective.

### Pitfall: The sidecar doesn't know what the driver already knows

The sidecar starts with zero context. If you don't tell it what you've
already verified, it will re-discover it.

**Fix:** In the first prompt, explicitly state what the driver already
knows. Use a "What I already know" section at the top of the brief.

### Pitfall: Multiple WPs need explicit scope boundaries

When you must investigate several independent areas, do NOT enumerate
them all in one brief. Use sequential sessions with distinct names.

## Brief structure reference

See `references/effective-briefs.md` for a fill-in-the-blanks template
with examples of narrow vs broad briefs.
