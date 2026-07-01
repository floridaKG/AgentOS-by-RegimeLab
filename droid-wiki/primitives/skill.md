# Skill

## Overview

A skill is a reusable agent capability definition in Agent OS. Skills are defined in a standardized SKILL.md format, registered in the central skills registry, and loaded by agents at runtime. The skill system provides discovery, relevance scoring, and bounded-context extraction.

## SKILL.md format

Each skill is defined by a SKILL.md file with YAML frontmatter and markdown instructions. The frontmatter follows this schema:

```yaml
---
id: <stable-slug>
name: <display-name>
trigger:
  - /command-name
  - natural language trigger phrases
scope: <workspace-scope>
status: <stable|active|draft|deprecated>
agents: <agents-that-can-use-this>
description: <one-line description>
last_reviewed: <YYYY-MM-DD>
---
```

| Field | Required | Description |
|---|---|---|
| `id` | Yes | Stable unique slug for the skill |
| `name` | Yes | Human-readable display name |
| `trigger` | Yes | List of invocation triggers (/commands and natural language) |
| `scope` | Yes | Workspace scope (e.g., cross-workspace, workspace-project-a) |
| `status` | Yes | Maturity status (stable, active, draft, deprecated) |
| `agents` | No | Which agents can use this skill |
| `description` | Yes | One-line description |
| `last_reviewed` | No | Date of last review |

The body of the SKILL.md contains the full instructions for the agent, organized in markdown sections with `##` headings. This body is what gets loaded into the agent's context.

### Example frontmatter

From the acp skill:

```yaml
---
id: acp
name: acp
trigger:
  - /acp
  - dispatch to executor
  - delegate to
scope: cross-workspace
status: stable
agents: any (claude, opencode, codex, pi, gemini, qwen)
description: Dispatch a task to another agent via ACP (Agent Communication Protocol)
last_reviewed: 2026-06-15
---
```

## Skill registry

Skills are registered in `registry/skills.yaml`, which is the source of truth for all discoverable skills. The registry uses this schema:

| Field | Type | Description |
|---|---|---|
| `name` | string | Skill identifier, matches the SKILL.md id |
| `tier` | string | Availability tier (os-shared, workspace-*, personal) |
| `status` | string | active, planned, deprecated, archived |
| `path` | string | Absolute path to the SKILL.md file |
| `trigger` | list | Trigger phrases for relevance matching |
| `description` | string | One-line description |
| `user_invocable` | bool | Whether users can invoke directly |

### Tiers

| Tier | Meaning |
|---|---|
| `os-shared` | Available to all agents across all workspaces |
| `workspace-*` | Scoped to a specific workspace (e.g., workspace-project-a) |
| `personal` | Personal agent skills |

### Current skills

The public distribution includes 10 os-shared skills:

| Skill | Description |
|---|---|
| `acp` | Cross-agent task dispatch via ACP |
| `recall` | Search configured memory tiers |
| `lesson` | Capture reusable lessons |
| `digest` | Summarize recent memory activity |
| `doc-audit` | Audit documentation quality |
| `skill-optimizer` | Discover and load relevant skills |
| `upward-handoff` | Prepare findings for higher-reasoning model review |
| `changes-review` | Traceable audit of changes |
| `moe` | Multi-provider Mixture-of-Experts panels |
| `agent-workflows` | Swarm, council, red-team workflows |

## Skill loading

Skills are loaded through a layered process:

1. **Skill-rank** — Given a task query, ranks skills by relevance using trigger match, description match, and tier boost
2. **Skill-pack** — Extracts only the actionable sections from the top-ranked skill, bounded by a token budget
3. **Skill-context** — Injects relevant skill context into the agent's system prompt

### skill-rank relevance scoring

The `scripts/skill-rank` tool scores skills against a natural language query:

```
skill-rank "<task description>" --top 3
```

Scoring considers:

- **Trigger match** — How well the query matches the skill's trigger phrases
- **Description match** — How well the query matches the skill's description
- **Tier boost** — Skills at the appropriate tier get a relevance bonus

Output can be text or JSON. Optional `--tier` filter limits results to a specific tier.

### skill-pack extraction

The `scripts/skill-pack` tool extracts bounded context from skill files:

```
skill-pack <skill-name> --budget 4000
```

Features:

- `--list-sections` — Lists all `##` headings in the skill
- `--section <heading>` — Extracts a specific section by heading
- `--budget <bytes>` — Truncates output to a byte limit

Skill files are discovered by searching `$AGENT_OS_HOME/skills/shared/` and other configured skill directories.

## Usage tracking

Each skill invocation is logged to `~/.cache/agent-workflows/skill-usage.jsonl` with timestamp, skill ID, agent, workspace, success status, and notes.

## Key files

| File | Purpose |
|---|---|
| `registry/skills.yaml` | Central skills registry |
| `skills/shared/*/SKILL.md` | Individual skill definitions |
| `scripts/skill-rank` | Relevance scoring tool |
| `scripts/skill-pack` | Bounded-context extraction tool |
