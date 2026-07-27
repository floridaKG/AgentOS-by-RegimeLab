---
id: skill-optimizer
name: skill-optimizer
trigger:
  - /skill-pack
  - /skill-rank
  - /context-pack
  - what skills are relevant
  - find skills for
  - pack skill
  - load skill section
  - context for handoff
  - bundle memory for
scope: os-shared
status: stable
description: "Discover relevant skills by query (skill-rank), extract only the sections you need from large skill files (skill-pack), bundle memory into bounded context packs for handoffs (context-pack), and auto-inject relevant skill context (skill-context). Use before loading any skill over 10KB, when searching for relevant skills, or when building context for a reasoning model handoff."
version: "1.1"
user-invocable: true
allowed-tools: Read, Bash
last_reviewed: 2026-06-17
---

## Purpose

Four utilities that make skill loading cheaper and handoffs cleaner:

1. **skill-rank** -- search the skills registry by query, get scored results
2. **skill-pack** -- load just the actionable section of a skill file, not the whole thing
3. **context-pack** -- bundle relevant memory across tiers into a bounded text block for handoffs
4. **skill-context** -- auto-inject relevant skill context (skill-rank + skill-pack in one call with a threshold)

These replace "load the full 100KB SKILL.md and hope for the best" with targeted, budget-aware loading.

---

## Execute

### skill-rank: Find relevant skills

```bash
$AGENT_OS_HOME/scripts/skill-rank "<query>" [--top N] [--tier <tier>] [--json]
```

**When to use:** Before loading any skill, check if it's relevant. Especially useful when you're not sure which skill matches a task.

**Examples:**
```bash
# What skills help with deploying the work workspace?
skill-rank "work deploy"

# What skills help with kanban/ACP dispatch?
skill-rank "kanban dispatch"

# Only show workspace-work skills
skill-rank "deploy" --tier workspace-work

# JSON output for programmatic use
skill-rank "recall memory" --json
```

**Scoring:** Skills are scored 0.0-1.0 by trigger-keyword match (0.5 max), description match (0.3 max), and tier boost (0.2 max). Top results are most relevant.

### skill-pack: Extract sections from skill files

```bash
$AGENT_OS_HOME/scripts/skill-pack <skill-name> [--list-sections] [--section <heading>] [--budget <bytes>]
```

**When to use:** When a skill file is large (10KB+) and you only need the execution instructions, not the full documentation.

**Examples:**
```bash
# See what sections a skill has
skill-pack memory-stack --list-sections

# Get just the Execute section (default extraction)
skill-pack memory-stack --budget 4000

# Get a specific section
skill-pack acp-delegation --section "How It Works"

# Get the first 2000 bytes (frontmatter + overview)
skill-pack recall --budget 2000
```

**Section extraction fallback:** If no matching heading is found, falls back in order: Execute -> Execution -> How To Invoke -> Usage -> Quick Reference -> Core Commands -> first 2000 bytes.

**Output format:**
```
=== SKILL PACK ===
Skill: <name>
Source: <path>
Original size: <N> bytes
Packed size: <N> bytes
Section: <extracted section>
=== BEGIN ===
<content>
=== END ===
```

### context-pack: Bundle memory for handoffs

```bash
$AGENT_OS_HOME/scripts/context-pack.sh "<query>" [--budget=<bytes>] [--tiers=<tier1,tier2>]
```

**When to use:** When building context for a reasoning model handoff, task takeover, or review gate. Queries multiple memory tiers, deduplicates, scores by relevance, and packs top-down until the byte budget is exhausted.

**Examples:**
```bash
# Bundle 8KB of context about work deployment
context-pack "work deployment"

# Tighter budget for a cheap model
context-pack "kanban dispatch" --budget=4000

# Only query specific tiers
context-pack "acp configuration" --tiers=cockpit,vector
```

**Output format:**
```
=== CONTEXT PACK ===
Query: "<query>"
Budget: <N> bytes
Used: <N> bytes
Results: <N> (deduplicated from <M>)

--- [1] TIER:<tier> METHOD:<method> SCORE:<score> FRESHNESS:<date> RELIABILITY:<level> ---
<result text>

--- [2] ...
=== END PACK ===
```

### skill-context: Auto-inject relevant skill context

```bash
$AGENT_OS_HOME/scripts/skill-context.sh "<task text>" [budget_bytes]
```

**When to use:** Called from deterministic dispatch paths (agent-workflow runner, sidecar) to auto-inject an actionable skill pack when skill-rank scores above 0.60. Not typically invoked directly by an agent — the threshold is deliberately stricter (0.60 vs 0.50) to avoid injecting the wrong skill.

**Example (internal use):**
```bash
skill-context "deploy work to staging" 4000
```

**Output format (emits nothing if below threshold or on error):**
```
<relevant_skill name="<name>" note="auto-injected by skill-context; matched the task text">
=== SKILL PACK ===
...
</relevant_skill>
```

---

## When to Use

- **Before loading any skill over 10KB** -- use skill-pack to get just the Execute section
- **When searching for relevant skills** -- use skill-rank instead of scanning the full registry
- **Before dispatching to a reasoning model** -- use context-pack to build a bounded context bundle
- **When taking over a task from another agent** -- use context-pack to get relevant memory
- **When setting up a deterministic dispatch path** -- reference skill-context.sh for auto-injection
- **As an agent invoking skill workflow directly** -- use skill-pack directly when you know the skill name

---

## When NOT to Use

- For quick recall lookups (use `/recall` directly, it's faster)
- For skills under 10KB (the overhead of packing isn't worth it)
- When you need the full skill documentation (read the SKILL.md directly)
- For real-time monitoring (these are on-demand CLI tools, not daemons)

---

## Integration Notes

- **Scripts live at:** `$AGENT_OS_HOME/scripts/skill-pack`, `$AGENT_OS_HOME/scripts/skill-rank`, `$AGENT_OS_HOME/scripts/context-pack.sh`, `$AGENT_OS_HOME/scripts/skill-context.sh`
- **PATH symlinks:** Each script is symlinked from `$AGENT_OS_HOME/.local/bin/` so short names (`skill-rank`, `skill-pack`, `context-pack`) work from any directory
- **Registry:** `$AGENT_OS_HOME/registry/skills.yaml` (skill-rank reads this)
- **No changes to:** Claude Code auto-discovery or the skills registry schema
- **Cross-agent:** Any agent with bash access can call these scripts directly

---

## Pitfalls

- **SIGPIPE on large files.** skill-pack's `extract_actionable` reads SKILL.md files via `while read` loops. If piped to `head -1` or `tail -n +2` under `set -o pipefail`, the script exits with 141 on files over ~10KB. Fix: capture output into a variable first, then split.
- **Scripts without skills are invisible.** Creating the script is step 1. Step 2 is creating the SKILL.md. Step 3 is registering in skills.yaml. Skip any step and agents that don't already know about the tool can't discover it.
- **Distribution is separate from creation.** After adding a skill, run `$AGENT_OS_HOME/scripts/build-skills-repo.sh` to include it in the distribution repo. Then sync to agent silos (symlinks for Claude Code/OpenCode, copies for Codex). The skill exists at the canonical path but agents in the "copy camp" won't see it until distribution runs.
- **skill-rank only finds registered skills.** If a skill isn't in `skills.yaml`, skill-rank won't score it. User-created skills outside the registry are invisible to skill-rank.

## Known limitations

- **skill-pack uses first-N-bytes truncation, not semantic extraction;** long skills may lose tail sections — raise `--budget` if a needed section is missing.
