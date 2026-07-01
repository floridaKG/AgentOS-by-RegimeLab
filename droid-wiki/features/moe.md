# MOE panels

## Purpose

The Mixture-of-Experts (MOE) system provides multi-provider parallel model panels that fan a task out to several LLMs simultaneously, then synthesize a unified verdict. It allows agents to get diverse opinions, adversarial review, or iterative refinement from multiple models without manual orchestration. The backend is the `team` binary at `~/.local/bin/team`.

## How it works

MOE uses configurable panels defined in `panels.toml`. Each panel specifies members (model/providers), a judge model, cost limits, timeouts, and output shape. The dispatcher fans the task out to all members in parallel, collects responses, then asks a judge model to synthesize a `verdict_with_disagreements`.

### MOE tiers

| Tier | Name | What it does | Status |
|------|------|-------------|--------|
| **1** | Quick | Parallel cheap/capped LLMs + cheap judge. Default. | LIVE |
| **2** | Swarm | Parallel full agents with inline model swap | LIVE |
| **2r** | Read-only Swarm | Parallel agents clamped read-only; `ranked_issues` output | LIVE |
| **3** | Persistent | Iterative transcript-replay rounds: collaborate / redteam | LIVE |
| **P** | Pipeline | Sequential role handoff (explorer -> architect -> reviewer) | LIVE |
| **research** | Profile | Bounded allow-listed fetch + injection guard | LIVE |

### Invocation

```bash
# MOE 1 (Quick) — default
team fire --tier 1 --panel quick --task "Evaluate this approach"
# MOE 2 (Swarm) with inline agent/model swap
team fire --members "claude opus high, codex gpt-5.5 med, droid go high" --task "..."
# MOE 2r (Read-only audit swarm)
team fire --tier 2r --panel swarm_readonly --task "..."
# MOE 3 (Persistent collaborate)
team fire --tier 3 --panel persistent_collaborate --task "..."
# MOE 3 (Persistent redteam)
team fire --tier 3 --mode redteam --members "claude opus high, codex gpt-5.5 med" --task "..."
```

### Configuration files

| File | Purpose |
|------|---------|
| `panels.toml` | Panel definitions with members, judge, cost, timeout, output shape |
| `model_aliases.toml` | Friendly model aliases for inline member specs (e.g., `opus`, `sonnet`, `gpt-5.5`) |
| `roles.toml` | Workflow role-to-model mappings (explorer, architect, executor, reviewer, escalation) |

### Output artifacts

Per-run artifacts are stored at `~/.local/state/agent-os/moe/runs/<run_id>/`:
`request.json`, `panel.jsonl`, `judge_prompt.md`, `judge_output.json`, `final.md` (human-readable synthesis), `manifest.json` (run-of-record). Retention is 30 days, then archive keeping only `final.md` + `manifest.json`.

### Cost guards

Panels support `cost = "free"` (strict: every member must carry a recognized free-model marker with `max_cost_usd = 0.00`) and `cost = "cheap"` (known cheap providers with `max_cost_usd` ceiling at $0.10).

## Integration points

The `team` binary is the sole dispatcher for all MOE tiers. It reads panel and alias configuration from `~/.config/agent-workflows/`. The MOE output directory is independent of the memory system — MOE outputs are analyses, never auto-written to factual memory. The `/moe` skill provides agent-facing invocation triggers.

## Key source files

| File | Purpose |
|------|---------|
| `bin/team` | MOE dispatcher binary (Python, ~3200 lines) |
| `skills/shared/moe/SKILL.md` | The `/moe` skill definition with tier documentation and invocation patterns |
| `.config/agent-workflows/panels.toml` | Panel member definitions and configuration |
| `.config/agent-workflows/model_aliases.toml` | Friendly model alias resolution |
| `.config/agent-workflows/roles.toml` | Workflow role-to-model mappings |
