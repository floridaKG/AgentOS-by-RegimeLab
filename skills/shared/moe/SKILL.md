---
id: moe
name: moe
trigger:
  - /moe
  - moe
  - moe 1
  - moe quick
  - fire a panel
  - run the moe family
scope: cross-workspace
status: stable
agents: any agent with shell + read access (the binary wraps all LLM calls)
description: '/moe — fire the MOE (Mixture-of-Experts) family; defaults to MOE 1 (Quick): N cheap/capped LLMs in parallel + a cheap judge synthesize a verdict + disagreements. Fast, tool-free, model-swappable via panels.toml.'
last_reviewed: 2026-06-16
---

# /moe — Mixture of Experts family dispatcher

`/moe` is the **family entry** for the Mixture-of-Experts (MOE) tiers.
With no argument it defaults to **MOE 1 (Quick)** — fan the user's task
out to N cheap/capped LLMs in parallel, then a cheap judge model synthesizes a
`verdict_with_disagreements`. No tools, no persistence, no per-member iterative
agent loop. The current default panel exercises Pi/acpx `opencode-go` pro models
(`deepseek-v4-pro`, `mimo-v2.5-pro`, `minimax-m3`) so MOE and sidecar
can test the same model surface. Same-provider different-models is
fine — diversity comes from model outputs, not provider adapters.

Backend: `team` at `~/.local/bin/team` (Python 3.11+).

Configuration lives in `~/.config/agent-workflows/panels.toml` and
`model_aliases.toml`.

## MOE Family — tiers and status

| Tier | Name | What it does | Status |
|------|------|-------------|--------|
| **1** | **Quick** | Parallel cheap/capped LLMs + cheap judge. **Default.** | **LIVE NOW** |
| **2** | **Swarm** | Parallel full agents with inline model swap. | **LIVE NOW** |
| **2r** | **Read-only Swarm** | Parallel agents clamped read-only (pre-dispatch write scan + NO-WRITE prefix); `ranked_issues` output. Audit/second-opinion tier. | **LIVE NOW** |
| **3** | **Persistent** | Iterative transcript-replay rounds: collaborate / redteam, per-round convergence judge + context guard. | **LIVE NOW** |
| **P** | **Pipeline** | Sequential role handoff (e.g. explorer→architect→reviewer), accumulated context, halt-on-failure. | **LIVE NOW** |
| **research** | **profile** | Bounded allow-listed fetch (`research_collector.py`) + injection guard, attachable to a tier. | **LIVE NOW** |

**MOE 1/2/2r/3/P all run today**, plus the `research` profile. `/moe` with no
argument fires MOE 1. Inline agent/model swap: `/moe 2 claude opus high, codex
gpt-5.5 med, droid go high`. `/moe 2r` runs a read-only audit swarm. `/moe 3
collaborate|redteam` fire the persistent panels. `team fire --pipeline <name>`
runs a sequential role pipeline.

## Activation forms

| Pattern | Backend invocation | Status |
|---------|-------------------|--------|
| `/moe` or `moe` | `team fire --tier 1 --panel quick --task "<text>"` | **Default — LIVE** |
| `/moe 1` or `moe quick` | Same as default (explicit) | **LIVE** |
| `/moe 2` or `/moe 2 swarm` | `team fire --tier 2 --panel swarm --task "<text>"` | **LIVE** |
| `/moe 2 <inline>` | `team fire --members "claude opus high, codex gpt-5.5 med, droid kimi-k2.7 low" --task "<text>"` | **LIVE — inline agent+model swap** |
| `/moe 2r` | `team fire --tier 2r --panel swarm_readonly --task "<text>"` | **LIVE — read-only audit swarm (`ranked_issues`)** |
| `/moe 2r <inline>` | `team fire --tier 2r --members "claude opus high, codex gpt-5.5 med" --task "<text>"` | **LIVE — inline read-only swarm** |
| `/moe 3` or `moe 3 collaborate` | `team fire --tier 3 --panel persistent_collaborate --task "<text>"` | **LIVE — iterative collaborate** |
| `/moe 3 <inline>` | `team fire --tier 3 --members "claude opus high, codex gpt-5.5 med" --task "<text>"` | **LIVE — inline persistent collaborate** |
| `/moe 3 redteam` | `team fire --tier 3 --panel persistent_redteam --task "<text>"` | **LIVE — adversarial proposer/attacker/adjudicator** |
| `/moe 3 redteam <inline>` | `team fire --tier 3 --mode redteam --members "claude opus high, codex gpt-5.5 med" --task "<text>"` | **LIVE — inline redteam** |
| `/moe p` (pipeline) | `team fire --pipeline spec_authoring --task "<text>"` or `--pipeline-stages explorer,architect,reviewer` | **LIVE — sequential role handoff** |
| research profile | `team fire --tier <N> --profile research --research-url <allowlisted> --task "<text>"` | **LIVE — bounded fetch + injection guard** |
| Picker / panel selector | Interactive model panel selection | Future |

All tiers are dispatched by `team`. MOE 2 accepts `--members` for inline
specs: `<provider> [model_friendly] [reasoning]`, comma-separated.

## Backend flags

```bash
# MOE 1 (Quick)
team fire --tier 1 --panel quick --task "<text>" [--dry-run] [--json]
# MOE 2 (Swarm) with default panel
team fire --tier 2 --panel swarm --task "<text>" [--dry-run] [--json]
# MOE 2 with inline agent/model swap
team fire --members "claude opus high, codex gpt-5.5 med, droid go high" --task "<text>" [--dry-run] [--json]
# MOE 3 (Persistent) — iterative rounds
team fire --tier 3 --panel persistent_collaborate --task "<text>" [--dry-run] [--json]
team fire --tier 3 --panel persistent_redteam --task "<text>" [--dry-run] [--json]
# MOE 3 inline
team fire --tier 3 --members "claude opus high, codex gpt-5.5 med" --task "<text>" [--mode collaborate] [--max-turns 6] [--dry-run] [--json]
team fire --tier 3 --mode redteam --members "claude opus high, codex gpt-5.5 med" --task "<text>" [--dry-run] [--json]
# MOE 2r inline
team fire --tier 2r --members "claude opus high, codex gpt-5.5 med" --task "<text>" [--dry-run] [--json]
# Panel checks
team panels --check quick [--json]
team panels --check swarm [--json]
# Model alias operations
team aliases --refresh
```

| Flag | Required | Default | Meaning |
|------|----------|---------|---------|
| `--tier` | no | `1` | Tier number: `1` (Quick), `2` (Swarm), `2r` (Read-only Swarm), or `3` (Persistent). |
| `--panel` | no | `quick` | Panel name from `panels.toml`. |
| `--members` | no | — | Inline member specs (comma-sep). Honors `--tier`: builds a transient panel for tier 2 (default), 2r, or 3. Overrides `--panel`. |
| `--mode` | no | `collaborate` | Tier 3 mode: `collaborate` (iterative synthesis) or `redteam` (adversarial go/no-go). Requires `--tier 3`. |
| `--max-turns` | no | `6` | Max iterative turns for tier 3 (clamp 1..10). |
| `--task` | yes (live) | — | Task text sent to every panel member. |
| `--dry-run` | no | off | Resolve panel + write artifacts, no provider calls. |
| `--json` | no | off | Emit machine-readable JSON. |

### Inline member syntax (tiers 2, 2r, 3)

`--members "<provider> [model] [reasoning], <provider> [model] [reasoning], ..."`

- **Provider:** `claude`, `codex`, `droid`, `pi`, `opencode` (must be a known provider)
- **Model (optional):** friendly alias; resolved via `model_aliases.toml`
  - codex: `gpt-5.5`, `gpt-5.5 med`, `gpt-5.5 high`, `gpt-5.5 xhigh`, `4o`
  - claude: `default`, `opus`, `haiku`, `sonnet`
  - droid: `go` (deepseek-v4-pro-0), `deepseek-v4-flash`, `deepseek`, `kimi-k2.7`
  - pi: `opencode-go/deepseek-v4-pro`, `opencode-go/mimo-v2.5-pro`, `opencode-go/minimax-m3`, `opencode-go/deepseek-v4-flash`
- **Reasoning (optional):** `low`, `med`/`medium`, `high`, `xhigh`
- Unresolved aliases → error with valid options listed; never silently falls back.

`team panels --check <name> [--json]` probes each member's liveness (cheap/free ids
churn weekly — re-probe and edit `panels.toml` when results degrade).

## Output artifacts

Per-run at `~/.local/state/agent-os/moe/runs/<run_id>/`:
`request.json`, `panel.jsonl`, `judge_prompt.md`, `judge_output.json`,
`final.md` (human-readable synthesis), `manifest.json` (run-of-record:
status, success/fail counts, cost).

Retention: 30 days, then archive keeping only `final.md` + `manifest.json`.

## Cost Guard And Model Switching (MOE 1)

`panels.toml` is the source of truth for model membership. Swap models there,
then run:

```bash
team panels --check quick
```

The dispatcher supports `cost = "free"` and `cost = "cheap"`:

- `cost = "free"` is strict: every member must carry a recognized free-model marker and `max_cost_usd = 0.00`.
- `cost = "cheap"` allows known cheap providers (`opencode`, `opencode-go`, `openrouter`) but requires an explicit `max_cost_usd` ceiling no higher than `0.10`.
- The current default `quick` panel uses `opencode-go/deepseek-v4-pro`, `opencode-go/mimo-v2.5-pro`, and `opencode-go/minimax-m3` through Pi/acpx.
- For Pi/acpx models, `max_output_tokens` is a prompt-level target plus `max_turns=1`, not a provider-enforced token ceiling.

## MOE 3 (Persistent) — iterative rounds

Two named panels in `panels.toml`, **no default** (pick one explicitly):

- **`persistent_collaborate`** (`output_shape = iterative_synthesis`): N members
  alternate turns building on a shared transcript; a cheap reviewer synthesises
  the converged answer. Default pair: `claude sonnet med` + `codex gpt-5.5 med`.
- **`persistent_redteam`** (`output_shape = go_no_go_verdict`): proposer ↔ attacker
  alternate, adjudicator gates with a strict Holes / PASS|PASS-WITH-FIXES|FAIL
  verdict. **proposer-provider ≠ attacker-provider is ENFORCED** (exit 4 otherwise).
  Panel defaults: `claude opus high` (proposer/adjudicator) vs `codex gpt-5.5 high` (attacker).
  **Inline injection:** when `--members` provides exactly 2 participants, the dispatcher auto-injects a 3rd participant as adjudicator.
  **Resolved 2026-06-18:** the default adjudicator is now `pi opencode-go/minimax-m3` (line 750 of `team`), which stays in the
  opencode-go pool and is alias-resolvable. NOTE: the `convergence_judge`/`reviewer` defaults
  (`opencode/mimo-v2.5-free`) are a SEPARATE concern and are NOT broken — those roles dispatch via `parse_model_id` (no alias
  resolution), not the participant path. See the "Two dispatch paths" pitfall below before treating them as the same defect.

Mechanics (all swappable per-panel in `panels.toml`):
- **Persistence = transcript-replay (v1).** Round state lives in the transcript
  replayed each turn — no `pi` tree-session dependency. Native sessions are a v2
  upgrade tracked in the pi-fix sibling spec.
- **Convergence judge** (`convergence_judge`, cheap) runs after each round and
  early-stops on `CONVERGED`; otherwise the loop runs to `max_turns` (1..10).
- **Context-growth guard** (`context_guard_chars`): older turns are summarised
  once the transcript exceeds the threshold, keeping the last K turns verbatim.
  The **full** transcript is always saved to `transcript.txt`.
- **Honest dispatch:** turns go through `run_member_cli` → `_validate` (the same
  path that counts MOE 2 success), so a provider error is a **failed turn**, never
  laundered into fabricated agreement. `status` needs a real final synthesis +
  ≥2 successful turns to be `ok`.
- A free/cheap `persistent_smoke` panel exists to exercise the full loop without
  spending paid calls.

## Memory boundary

MOE outputs are **analyses** in `~/.local/state/agent-os/moe/` — never
auto-written to factual memory. Promoting a verdict is an explicit user
action.

## Pitfalls

### Members time out (ACP startup overhead)

ACP session startup (Pi/Droid adapters) is slower than raw LLM calls.
All panels and inline dispatch have generous timeouts to account for this,
but if you're adding a new panel or provider, the defaults may bite you.

**Current timeouts by dispatch path:**

| Path | Timeout | Config location |
|------|---------|-----------------|
| MOE 1 Quick panel | 180s | `panels.toml` `[panel.quick]` `per_model_timeout_s` |
| MOE 2 Swarm panel | 300s | `panels.toml` `[panel.swarm]` `per_model_timeout_s` |
| MOE 2 `--members` inline | 300s | `team` `_run_inline_members` hardcoded |
| MOE 2r Read-only swarm | 300s | `panels.toml` `[panel.swarm_readonly]` `per_model_timeout_s` |
| MOE 3 Persistent | 120s | Per-panel in `panels.toml` |
| Pipeline (MOE-P) | 90s | `panels.toml` `[panel.spec_authoring]` `per_model_timeout_s` |

**Fix for MOE 2 inline:** Edit `~/.local/bin/team` at `_run_inline_members`:
```python
"per_model_timeout_s": 300,  # ACP startup needs room
```

For `opencode-go` model IDs (Pi/acpx path), 180s is usually sufficient.
For droid (acp-to-droid), the adapter negotiates model catalog + session
before the prompt — 300s is safer.

### Diversity check was removed (2026-06-16)

The `team` dispatcher previously blocked panels where all 3+ members resolved
to the same provider. This was over-strict — three different opencode-go models
(deepseek-v4-pro, mimo-v2.5-pro, minimax-m3) through the same provider produce
genuinely different outputs.

The check was removed from both `_run_tier_1` (MOE 1) and `_run_tier_2`
(MOE 2). `diversity_not_met` is always `False` now in those two runners.
**Not global:** tier 2r (`_run_tier_2r`, the ranker) and tier 3 redteam
(`_run_tier_3`, proposer-vs-attacker) still enforce real provider diversity
(2r: all-3-same-provider blocks; redteam: proposer provider != attacker
provider, exit 4). The removal is scoped to the parallel-mixture tiers whose
diversity lives in model outputs; the ranker and adversarial tiers genuinely
need provider separation.

If you want multi-backend diversity anyway, use MOE 2 with mixed providers:
```
team fire --tier 2 --members \
  "droid deepseek-v4-flash low, pi opencode-go/mimo-v2.5-pro low, pi opencode-go/minimax-m3 low"
```
`droid` routes via acp-to-droid (OpenCode Go backend), `pi` routes via acpx.
Two providers = guaranteed platform diversity regardless of check state.

### Default members jump across providers (2026-06-16)

When `--members` provides exactly 2 participants for MOE 3 redteam, the
dispatcher injects `claude haiku` as the default adjudicator. This routes
through a different provider (Anthropic/Claude Code) than the rest of the MOE
panel, adding a provider dependency and a different pricing tier for no benefit.

**Rule:** injected defaults should prefer the opencode-go pool
(`opencode-go/minimax-m3`, `opencode-go/deepseek-v4-flash`) over
cross-provider models. If an alias isn't resolving, pick a working
opencode-go model from the pool — don't jump providers.

### Two dispatch paths — do not confuse alias-resolution with model-id parsing (verified 2026-06-17)

A prior review claimed the `convergence_judge`/`reviewer` defaults
(`opencode/mimo-v2.5-free`) "may not be alias-resolvable as a participant" and
treated that as the same defect as the adjudicator. It is not. The `team`
binary has two distinct dispatch paths, and "alias-resolvable" only applies to
one of them:

- **Participants** (proposer / attacker / adjudicator) go through
  `resolve_inline_spec` — space-separated `<provider> <model> [reasoning]`,
  looked up in `model_aliases.toml`. Strict: an unknown alias or a provider
  with no alias group raises `ValueError`. This is why `opencode mimo-v2.5-free`
  fails as a participant (there is no `opencode` alias group; the `pi` group
  keys are full `opencode-go/<model>` strings, no `-free` variants).
- **convergence_judge / reviewer** go through `parse_model_id` — a direct
  `<provider>/<model>` split with no alias lookup, then `call_model` dispatches
  by provider (`opencode` -> opencode CLI, `opencode-go` -> Pi/acpx). So
  `opencode/mimo-v2.5-free` parses fine and dispatches via the `opencode` CLI,
  which lists it as a real model. It is NOT subject to participant
  alias-resolution.

**Verified:** `team fire --tier 3 --mode redteam --members "claude opus,codex gpt-5.5 med" --dry-run --json` resolves the `claude haiku` adjudicator AND parses `opencode/mimo-v2.5-free` for the judge/reviewer cleanly. The same `opencode/mimo-v2.5-free` judge/reviewer id is used consistently across the inline defaults and all three named tier-3 panels (`persistent_collaborate`, `persistent_redteam`, `persistent_smoke`) — it is consistent, not an anomaly.

**Diagnostic rule:** if a model id fails for one role, confirm which dispatch
path that role uses before claiming it's broken for the others. "Unresolvable
as a participant" does not imply "unusable as a judge." The cheap pool
(`opencode-go/*`) routes through Pi/acpx; the inline `opencode/*` judge ids
route through the opencode CLI — two different live surfaces, both green.

## Other mixture-of-agents tools

Some agent hosts provide their own mixture-of-agents features. Those are
separate from the portable `team` dispatcher documented here. Configure Agent
OS panels through `panels.toml` and `model_aliases.toml`.

## What this skill is NOT

- **Note:** MOE 1/2/2r/3/P + the research profile are all LIVE. MOE-2r's
  read-only enforcement is **prompt-level + a pre-dispatch write scan** (NO-WRITE
  prefix + `_scan_for_writes`), not OS-sandboxing — fine for a cooperative audit
  tier, but a determined agent is not hard-blocked.
- **Not** a replacement for `agent-workflow` subcommands (`swarm`,
  `council`, `dialogue`, `redteam`, `orchestrate`). MOE 3 reuses the iterative
  transcript-replay *pattern* of `dialogue.sh`/`redteam.sh` but dispatches via
  the honest `run_member_cli` path, not those scripts' canned-text fallbacks.
- The `research` profile fetches **only** through `research_collector.py`
  (fail-closed allow-list + injection guard) — never ad-hoc agent web access.

## Backed by

- `~/.local/bin/team` — dispatcher binary
- `~/.config/agent-workflows/panels.toml` — `[panel.quick]` member list
- `~/.config/agent-workflows/topologies.toml` — concurrency + retry
- `~/.local/state/agent-os/moe/runs/` — per-run artifacts
- Umbrella spec (path above)
