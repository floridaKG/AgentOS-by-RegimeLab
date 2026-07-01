---
title: Agent OS — Master Index
last_updated: 2026-06-25
status: active
trust_tier: Generated
purpose: Master index of skills, tools, workflows, and memory tiers. Grep this, never edit it directly.
source_of_truth: $AGENT_OS_HOME/registry/ (skills.yaml, tools.yaml, workflows.yaml, memory_tiers.yaml)
---

# Agent OS — Master Index

**How to use this file:** `grep -i <keyword> INDEX.md`

## QUICK FIND

| Keyword | Skill / Tool / File |
|---|---|
| acp, dispatch, delegate | skill: acp |
| recall, search, memory | skill: recall |
| lesson, capture, remember | skill: lesson |
| digest, summary, recent | skill: digest |
| doc-audit, audit docs | skill: doc-audit |
| skill-rank, skill-pack | skill: skill-optimizer |
| handoff, upward, review | skill: upward-handoff |
| changes, trace, audit | skill: changes-review |
| moe, mixture, panel | skill: moe; tool: team |
| swarm, council, redteam | skill: agent-workflows |
| memory-st, write, query | tool: memory-st |
| memory-lt, long-term | tool: memory-lt |
| memory-recall, cross-tier | tool: memory-recall |
| memory-recall-safe, fallback | tool: memory-recall-safe |
| memory-inject, inject | tool: memory-inject |
| memory-promote, promote | tool: memory-promote |
| agent-voice, friction, feedback | tool: agent-voice |
| health, verify, check | tool: agent-os-health, agent-os-verify |
| vault, knowledge, notes | example: examples/vault-os/ |
| superdocs, docs, project | example: examples/superdocs/ |

## 1. Skills (`skills/shared/`)

| Skill | Trigger | Description |
|---|---|---|
| [acp](skills/shared/acp/SKILL.md) | `/acp`, dispatch task, delegate to | Route work to configured agents through ACP |
| [recall](skills/shared/recall/SKILL.md) | `/recall`, recall, find lessons | Search configured memory tiers |
| [lesson](skills/shared/lesson/SKILL.md) | `/lesson`, capture this lesson | Capture reusable lessons to durable memory |
| [digest](skills/shared/digest/SKILL.md) | `/digest`, summary of recent lessons | Print human-readable memory summary |
| [doc-audit](skills/shared/doc-audit/SKILL.md) | `/doc-audit`, audit docs | Audit documentation for quality |
| [skill-optimizer](skills/shared/skill-optimizer/SKILL.md) | skill-rank, skill-pack | Discover and load relevant skills efficiently |
| [upward-handoff](skills/shared/upward-handoff/SKILL.md) | `/handoff`, upward review | Prepare findings for higher-reasoning model |
| [changes-review](skills/shared/changes-review/SKILL.md) | `/changes-review`, trace fixes | Produce traceable audit of changes |
| [moe](skills/shared/moe/SKILL.md) | `/moe`, fire a panel | Run configurable Mixture-of-Experts tiers |
| [agent-workflows](skills/shared/agent-workflows/SKILL.md) | `/swarm`, `/redteam`, multi-agent review | Select parallel, adversarial, or iterative workflows |

## 2. Tools (`scripts/`, `bin/`)

### CLI Tools

| Tool | Path | Description |
|---|---|---|
| memory-st | `bin/memory-st` | Short-term memory operations (write, query) |
| memory-lt | `bin/memory-lt` | Long-term memory operations (search, promote) |
| memory-recall | `bin/memory-recall` | Cross-tier memory search |
| memory-recall-safe | `bin/memory-recall-safe` | Fallback-safe memory search for hooks and integrations |
| memory-inject | `bin/memory-inject` | Build packet-scoped memory context |
| memory-promote | `bin/memory-promote` | Promote short-term to long-term storage |
| agent-voice | `bin/agent-voice` | Capture agent friction, improvement ideas, and risks |
| team | `bin/team` | Run configurable MOE and multi-provider panels |
| agent-workflow | `bin/agent-workflow` | Run swarm, council, dialogue, red-team, and orchestrated workflows |

### Scripts

| Script | Path | Description |
|---|---|---|
| agent-os-health | `scripts/agent-os-health.sh` | Run health checks |
| agent-os-verify | `scripts/agent-os-verify.sh` | Verify installation integrity |
| agent-os-boot | `scripts/agent-os-boot.sh` | Bootstrap session |
| agent-os-health | `scripts/agent-os-health.sh` | Check memory and system tier health |
| registry-check | `scripts/registry-check.py` | Validate registry consistency |
| hard-rule-smoke | `scripts/hard-rule-smoke.sh` | Smoke-test hard rules |
| skill-rank | `scripts/skill-rank` | Rank skills by relevance |
| skill-pack | `scripts/skill-pack` | Extract bounded context packs |
| context-pack | `scripts/context-pack.sh` | Bundle context for handoffs |
| recall | `scripts/recall.sh` | Search across memory tiers |
| sync-check | `scripts/sync-check.sh` | Check file sync status |
| build-manifest | `scripts/build-manifest.py` | Build export manifest |
| build-skills-repo | `scripts/build-skills-repo.sh` | Build skills repository |
| init-vault | `scripts/init-vault.sh` | Create or link knowledge vault |
| init-superdocs | `scripts/init-superdocs.sh` | Scaffold SuperDocs for a project |

## 3. Memory Stack

Source of truth: `registry/memory_tiers.yaml`

| Tier | Backend | Scope | Status |
|---|---|---|---|
| Short-Term | SQLite + FTS5 | Operational events, lessons, stumbles | Core (always available) |
| Semantic | Pinecone | Vector search for cross-session recall | Optional (needs API key) |
| Graph | Neo4j | Relationship-based memory queries | Optional (needs credentials) |

### Memory Commands

| Action | Command |
|---|---|
| Write lesson/stumble | `memory-st write --intent LESSON --summary "..." --source-ref cli:...` |
| Search memory | `recall "query"` or `memory-lt search-vector --text "..."` |
| Check health | `bash scripts/agent-os-health.sh` |
| Promote record | `memory-promote --id <record-id> --target auto` |
| Dry-run memory injection | `memory-inject --packet packet.json --dry-run` |
| Capture agent feedback | `agent-voice emit --kind friction --statement "..."` |
| MOE quick panel | `team fire --tier 1 --panel quick --task "..."` |
| Provider-diverse swarm | `team fire --tier 2 --members "claude default, codex default" --task "..."` |

## 4. Workflows

| Workflow | Trigger | Description |
|---|---|---|
| session-start | agent-boot | Mandatory boot sequence |
| lesson-capture | /lesson | Capture reusable lessons |
| memory-recall | /recall | Search across memory tiers |
| skill-optimization | skill-rank | Discover and load skills |
| doc-audit | /doc-audit | Audit documentation quality |

## 5. Agent Integrations

| Agent | Description | Use When |
|---|---|---|
| claude | Anthropic Claude Code | Complex reasoning, code review |
| codex | OpenAI Codex | Deep code analysis, refactoring |
| opencode | OpenCode | Lightweight model hosting |

## 6. Configuration

| File | Purpose |
|---|---|
| `config.env.template` | Environment variables template |
| `.env.template` | Secrets template |
| `registry/` | All registries (skills, tools, workflows, agents, memory) |

## 7. Documentation

| File | Purpose |
|---|---|
| `README.md` | Project overview and quickstart |
| `SETUP.md` | Installation and configuration guide |
| `PRIVACY_BOUNDARY.md` | What ships and what is excluded |
| `COMMERCIAL_BOUNDARY.md` | Open-core versus managed/commercial boundary |
| `AGENTS.md` | Agent entrypoint and boot routing |
| `BOOT.md` | Intent router for workspace matching |
| `docs/rtk-usage-guide.md` | RTK usage guide |
| `docs/codegraph-setup.md` | CodeGraph setup guide |
| `docs/MEMORY_USER_GUIDE.md` | Memory operation guide |

## 8. Examples

| Example | Purpose |
|---|---|
| `examples/vault-os/` | Generic knowledge vault scaffold |
| `examples/superdocs/` | Generic project documentation scaffold |

## 9. Tests

| Test | Purpose |
|---|---|
| `tests/smoke/cold_boot.sh` | Structure and syntax validation |
| `tests/smoke/release_gate.sh` | Comprehensive release validation |
| `tests/privacy/privacy_gate.sh` | Privacy and secret scanning |
| `tests/clean-room/install_and_verify.sh` | Isolated installation proof |
