---
id: agent-workflows
name: agent-workflows
trigger:
  - red team this
  - adversarial review
  - poke holes
  - run it overnight
  - grind on this
  - parallel explore
  - get multiple opinions
  - do a quick moe
  - do a moe2 review
  - /redteam
  - /swarm
  - /council
  - /moe1
  - /moe2
  - /moe3
scope: cross-workspace
status: stable
description: "Run a multi-agent workflow (swarm/council/dialogue/redteam/orchestrate or an overnight worktree loop) instead of dispatching a single task. Use when a job benefits from parallel agents, adversarial review, multiple opinions, or long autonomous grinding. Also covers the MOE reasoning-quality tiers: MOE1 (cheap parallel LLM panel), MOE2 (provider-diverse multi-agent panel + inline model/agent swap), MOE3 (persistent iterative collaborate/redteam rounds). The MOE family is dispatched by the `team` binary — see the `moe` skill for the canonical contract."
last_reviewed: 2026-06-15
---

# Agent Workflows -- Multi-Agent Workflow Toolbox

Use this skill when the job needs a workflow, not a single ACP dispatch. For one
agent doing one task, use the `acp` skill and `acp-task` instead.

## When to use which workflow

| Workflow | Use when |
|---|---|
| `swarm` | You need parallel explorers to inspect separate angles, then a reviewer synthesis. |
| `council` | You need independent opinions before choosing a direction or surfacing disagreements. |
| `dialogue` | You want two agents to alternate turns and refine an answer through exchange. |
| `redteam` | You need adversarial proposer / attacker / adjudicator review with PASS/FAIL gating. |
| `orchestrate` | You want an explore -> build -> review loop for a goal that spans phases. |

## Reasoning-quality escalation: MOE1 / Swarm / MOE2

When the user wants multiple models to weigh in on a question, choose the cheapest tier that can do the job. Escalate up only if the cheaper tier missed something known to be present.

| Tier | What it is | Cost | Latency | Tools | When to use |
|------|-----------|------|---------|-------|-------------|
| **MOE1 (quick moe)** | 3 free-model LLM calls in parallel, cheap paid judge, conditional rewrite. See `references/parallel-multi-model-panel.md`. | ~$0.01-0.05 | 20-30s | None | "Quick take on this idea" / "what do you think" / spec text review with no codebase context. Daily driver. |
| **Swarm (multi-agent)** | 2-4 real ACP agents in parallel, each with full tool autonomy, reviewer synthesis. | ~$0.30-2 | 60-120s | Full (grep, codegraph, memory, web) | "Review the spec against the live codebase" / "find all the places that use the old API." Each agent pulls its own context. |
| **MOE2 (provider-diverse panel)** | Swarm with a `roles.toml` profile that pre-binds 3-4 different providers (e.g. Opus + GPT-5.5 + Droid). Same engine as swarm, different slot bindings. | ~$0.50-2 | 60-120s | Full | "Have Opus, GPT-5.5, and Droid each review this refactor" / research with each panelist pulling from a different source. |

**Triage rule:** Try MOE1 first. If the user pushes back ("missed X", "didn't look at Y", "needs to read the actual code"), escalate to swarm/MOE2. Do not skip tiers unless the user explicitly names the providers they want.

**Output shape by tier:**
- MOE1: markdown report with ranked issues (must-fix / consider / nice-to-have), one-liner per panel
- Swarm: full synthesis with agent-specific findings, ~1-2 pages
- MOE2: same as swarm but with named providers per section, so the user can see who said what

## How to call

```bash
agent-workflow <name> <file> [args]
# MOE family
team fire --tier 1 --panel quick --task "<question>"
```

Examples:

```bash
agent-workflow swarm /tmp/question.md 4
agent-workflow council /tmp/problem.md
agent-workflow dialogue executor escalation /tmp/topic.md 3
agent-workflow redteam /tmp/artifact.md 2
agent-workflow orchestrate /tmp/goal.md
```

## Models

`~/.config/agent-workflows/roles.toml` is the workflow model knob.
The workflow runner reads role-to-model mappings from that file; swap models
there instead of hard-coding provider IDs in prompts or skill docs.

For a zero-metered redteam smoke test:

```bash
REDTEAM_FORCE_LOCAL=1 agent-workflow redteam /tmp/artifact.md 1
```

## Safety

Path confinement is partial today: the workflow harness rejects obvious
`allowed_paths` / `denied_paths` overlap before launch, but there is still no
OS-enforced sandbox around the worker itself. Treat loop output as untrusted
until reviewed.

There is no auto-merge. Inspect workflow output before applying changes.

## Verification And Discovery

Discovery and propagation rules:

- Agents read this skill from `$AGENT_OS_HOME/skills/shared/agent-workflows/`.
- Re-run the installer after upgrades to refresh user configuration templates.
- If the skill is missing from generated discovery surfaces, verify `registry/skills.yaml`, `render-index.py`, `INDEX.md`, and `scripts/build-skills-repo.sh` together.

## Related

- `references/sequential-multi-model-review.md` — dispatch a document to multiple models in sequence, each seeing the prior review, then synthesize. Use for high-stakes architecture decisions.
- `references/parallel-multi-model-panel.md` — the MOE1 (cheap parallel LLM panel) and MOE2 (provider-diverse swarm) patterns, including the 3-tier reasoning-quality escalation map and the activation-surface problem.

## Pitfalls

- **The activation surface is the bottleneck, not the engine.** Users forget swarm/council/redteam exist because the slash commands aren't surfaced in every entry point (Telegram, Claude Code, Codex). If the user says "I've never used X" about any workflow in this skill, the fix is wiring `/swarm`, `/council`, `/moe1`, `/moe2` into the surfaces they actually use, NOT building new architecture. The engine already works.
- **Don't skip MOE1 to swarm.** The first instinct when "multiple opinions" comes up is to spin up a multi-agent swarm. MOE1 (cheap, no tools, 30s) handles 80% of "what do you think" questions. Only escalate when the user names a provider or asks for tool-using investigation.
- **Sequential multi-model review** (see `references/sequential-multi-model-review.md`) is the right pattern when each model must see the prior model's output. MOE1/MOE2 are parallel; do not confuse them. Parallel = diversity, sequential = depth.
