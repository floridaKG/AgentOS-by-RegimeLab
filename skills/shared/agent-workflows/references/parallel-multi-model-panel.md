# Parallel Multi-Model Panel (MOE1 + MOE2)

The "MOE" patterns: run multiple models in parallel on the same question, then synthesize. The cheapest daily-driver tier of reasoning-quality escalation. Distinct from sequential review (each model sees the prior's output) and from full multi-agent workflows (real agents with tools).

## The 3-tier escalation map

| Tier | Engine | Cost | Latency | Tools | Activation phrase |
|------|--------|------|---------|-------|-------------------|
| **MOE1** | 3 free LLM calls + 1 cheap paid judge (parallel) | ~$0.01-0.05 | 20-30s | None | "do a quick moe", "what do you think", "/moe1" |
| **Swarm** | 2-4 real ACP agents in parallel, reviewer synthesizes | ~$0.30-2 | 60-120s | Full | "/swarm", "get multiple opinions" |
| **MOE2** | Swarm with `roles.toml` profile binding 3-4 different providers | ~$0.50-2 | 60-120s | Full | "do a moe2 review", "have Opus and GPT-5.5 each look at this" |

**Triage rule:** Try MOE1 first. If the user pushes back with "missed X" or "needs to read the actual code," escalate to swarm/MOE2. Do not skip tiers.

## MOE1 — Quick MOE (the daily driver)

**Shape:** Pattern P3 — parallel panel + adversarial judge + conditional rewrite.

```
Q -> [M1, M2, M3 in parallel, no tools]
   -> cheap paid judge reads all 3, writes structured critique
   -> IF judge flagged real flaws:
        rewrite with strongest panelist, given judge's critique
   -> judge synthesizes final answer
```

**Panel size:** 3 (Nemotron + gemma-4 + minimax-m3-free via openrouter, with zen and nvidia as backup providers). Adding a 4th burns an extra free request per run for marginal diversity; openrouter's 50/day cap matters more than theoretical coverage.

**Provider diversity:** Different providers, not all the same. To start: all openrouter. Backup rotation: zen, nvidia. Tunable per-session.

**Adversarial trigger:** Conditional, not always-on. The judge only triggers a rewrite if it found real flaws. Common case (panel already aligned) skips step 3: ~25s, 4 calls. Worst case: ~45s, 5 calls.

**Output shape:** Markdown report sorted must-fix / consider / nice-to-have, with one-liner per panel so the user can see who said what. ~1-2 pages for a typical spec review.

**Activation surface:** `/moe1` slash command, ideally available in every entry point the user touches. This is the gap. If the user has to remember to type it, they won't.

## MOE2 — Provider-Diverse Multi-Agent Panel

**The thesis:** the existing swarm/council engine works. The missing piece is pre-binding workflow slots to *different providers* (not all opencode-zen) so the panel has real model diversity.

**Implementation is roles.toml config, not new architecture:**

```toml
# ~/.config/agent-workflows/roles.toml
# Add profile-style bindings (future) OR just edit existing slots:

[explorer]
model = "opus"
provider = "claude"
cost = "paid"

[architect]
model = "gpt-5.5[high]"
provider = "codex"
cost = "paid"

[reviewer]
model = "custom:OpenCode-Zen-deepseek-v4-flash-free-0"
provider = "droid"
cost = "free"
```

That single edit turns `agent-workflow swarm` into a 3-provider panel (Opus + GPT-5.5 + Droid) without changing the engine.

**Use cases for MOE2:**
- Code refactor review: "Have Opus, GPT-5.5, and Droid each review this diff"
- Research: each panelist pulls from a different source (GitHub, arXiv, internal docs)
- Architecture decision: Opus designs, GPT-5.5 stress-tests, Droid verifies
- Spec review: same shape, but reviewers are bound to the same providers the user trusts for code

**Activation:** `/moe2` slash command that pre-sets a roles.toml profile before calling `agent-workflow swarm` or `agent-workflow council`. Or: a `moe-research` profile that uses `team` as the orchestrator with research-specific role bindings.

## When NOT to use either

- **Don't use MOE1 for tool-using investigation.** "Find all the places that use the old API" needs grep/codegraph. Use swarm.
- **Don't use MOE2 for cheap daily-driver questions.** Wasteful when MOE1 would do.
- **Don't use either for a single focused question.** "What's the right cron syntax for X" doesn't need 3 opinions. Just look it up.
- **Don't use MOE2 if you only have one provider available.** The whole point is diversity. With one provider, it's just expensive swarm.

## Cost model assumptions (June 2026)

- Free tier: openrouter, zen, nvidia — 50/day combined (cap varies per provider)
- Cheap paid: deepseek-v4-flash on opencode-go — ~$0.005/call, used as judge
- Paid providers: opus (claude, plan-covered), gpt-5.5 (codex, plan-covered)
- Free review model: mimo-v2.5-free on zen
- Custom aliases live in `~/.config/agent-workflows/model_aliases.toml`.

## Pattern source

- `references/sequential-multi-model-review.md` — the depth-shaped sibling (each model sees prior output). Use for high-stakes architecture decisions where you need escalation, not diversity.
- The rejected `2026-06-13-agent-os-research-moe` spec — that one is bounded source context for the Research MOE use case, separate from this.
- The `2026-06-13-agent-self-improvement-infrastructure` DRAFT spec — Stage 4 of that is the consumer of MOE1/MOE2 triage reports (it auto-generates candidate prompts when MOE flags a stale skill).
