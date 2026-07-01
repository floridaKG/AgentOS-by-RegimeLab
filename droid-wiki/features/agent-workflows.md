# Agent workflows

## Purpose

The agent workflow system provides multi-agent coordination patterns for tasks that benefit from parallel exploration, independent opinions, adversarial review, iterative refinement, or sequential phase-based execution. Instead of dispatching a single ACP task, these workflows route work across multiple agents with different roles, models, and tools.

## How it works

The `agent-workflow` CLI dispatches workflow types defined in `~/.config/agent-workflows/`. Each workflow type has a dedicated script (`swarm.sh`, `council.sh`, `dialogue.sh`, `redteam.sh`, `orchestrate.sh`, `escalate.sh`) and shared library scripts in `lib/`.

### Workflow types

| Workflow | Use case | Mechanics |
|----------|----------|-----------|
| Swarm | Parallel explorers inspecting separate angles | 2-4 agents run in parallel with full tool autonomy, followed by reviewer synthesis |
| Council | Independent opinions before choosing direction | Each agent produces an independent assessment; disagreements are surfaced |
| Dialogue | Two agents refining through exchange | Alternating turns on a shared transcript with configurable turn count |
| Red-team | Adversarial proposer/attacker/adjudicator review | Proposer and attacker alternate; adjudicator gates with PASS/FAIL verdict |
| Orchestrate | Explore -> build -> review loop for multi-phase goals | Sequential phases with accumulated context |
| Escalate | Hard tasks that cheaper models can't finish | Higher-capability model with selective use |

### Invocation

```bash
agent-workflow swarm /tmp/question.md 4          # 4-agent swarm
agent-workflow council /tmp/problem.md            # Independent opinions
agent-workflow dialogue executor escalation /tmp/topic.md 3  # Dialogue, 3 turns
agent-workflow redteam /tmp/artifact.md 2          # Adversarial review
agent-workflow orchestrate /tmp/goal.md            # Multi-phase loop
```

### Reasoning-quality escalation

When multiple model opinions are needed, the system provides a three-tier escalation ladder:

| Tier | What it is | Cost | Latency | Tools | When to use |
|------|-----------|------|---------|-------|-------------|
| MOE1 (Quick) | 3 cheap LLM calls in parallel + judge | ~$0.01-0.05 | 20-30s | None | Quick review, spec text, daily driver |
| Swarm | 2-4 real ACP agents in parallel | ~$0.30-2 | 60-120s | Full | Live codebase review, API audit |
| MOE2 | Swarm with provider-diverse panel | ~$0.50-2 | 60-120s | Full | Cross-provider analysis |

### Packet mode

Workflows can also be invoked via packet contract (a JSON file with fields like `workflow_name`, `run_id`, `workspace`, `goal_file`, `objective`, `scope`, `boundaries`, `success_criteria`, `ownership`, `prompt_hash`). This is used for programmatic dispatch where the workflow configuration is serialized and passed between systems.

### Role model bindings

Role-to-model mappings are defined in `~/.config/agent-workflows/roles.toml`:

| Role | Default provider | Purpose |
|------|-----------------|---------|
| explorer | opencode | Research and codebase discovery |
| architect | claude | Design and specification writing |
| executor | codex | Implementation and focused changes |
| reviewer | claude | Quality gates and skeptical review |
| escalation | (varies) | Hard tasks cheaper models can't finish |

### Safety

Path confinement is partial: the workflow harness rejects obvious `allowed_paths` / `denied_paths` overlap before launch, but there is no OS-enforced sandbox around the worker. Loop output should be treated as untrusted until reviewed. There is no auto-merge.

## Integration points

The `agent-workflow` CLI reads workflow scripts from `~/.config/agent-workflows/` and role mappings from `roles.toml`. Library scripts in `lib/` handle ACP dispatch (`acpx-dispatch.sh`), safety validation (`safety.sh`), packet contract parsing (`packet.sh`), workspace detection (`workspace.sh`), and process orchestration (`run.sh`). The MOE tiers share the same `team` binary described in the MOE panels feature.

## Key source files

| File | Purpose |
|------|---------|
| `bin/agent-workflow` | Unified entry point for all agent workflows (shell script) |
| `skills/shared/agent-workflows/SKILL.md` | Skill definition with workflow selection guide |
| `.config/agent-workflows/swarm.sh` | Parallel swarm workflow implementation |
| `.config/agent-workflows/council.sh` | Independent council workflow implementation |
| `.config/agent-workflows/dialogue.sh` | Alternating dialogue workflow implementation |
| `.config/agent-workflows/redteam.sh` | Adversarial red-team workflow implementation |
