# Skill optimization

## Purpose

The skill optimization toolkit provides four utilities that make skill loading cheaper and handoffs cleaner. Instead of loading full SKILL.md files or scanning the registry manually, agents can rank skills by relevance to a task, extract only the actionable sections they need, bundle cross-tier memory into bounded context packs, and auto-inject relevant skill context during deterministic dispatch.

## How it works

### skill-rank

Searches the skills registry (`registry/skills.yaml`) by query string and returns scored results. Scores are calculated by trigger-keyword match (0.5 max), description match (0.3 max), and tier boost (0.2 max).

```bash
skill-rank "deploy project-a" --top 5
skill-rank "recall memory" --json
```

### skill-pack

Extracts specific sections from large SKILL.md files with token-bounded output. Useful when a skill file is 10KB+ and only the execution instructions are needed.

```bash
skill-pack memory-stack --list-sections           # See available sections
skill-pack recall --budget 4000                    # Extract Execute section
skill-pack acp-delegation --section "How It Works" # Specific heading
```

Section extraction fallback order: `Execute` -> `Execution` -> `How To Invoke` -> `Usage` -> `Quick Reference` -> `Core Commands` -> first 2000 bytes.

### context-pack

Bundles relevant memory across tiers into a bounded text block for handoffs, task takeover, or review gates. Queries multiple memory tiers, deduplicates by fingerprint, scores by relevance, and packs top-down until the byte budget is exhausted.

```bash
context-pack "project-a deployment"                # Default 8KB budget
context-pack "kanban dispatch" --budget=4000        # Tighter budget
context-pack "acp configuration" --tiers=cockpit,vector  # Specific tiers
```

### skill-context

Auto-injects relevant skill context when the task text matches a skill above a threshold (default 0.60, stricter than the manual-load rule at 0.50). Used by deterministic dispatch paths such as `droid-exec`, `agent-workflow lib/run.sh`, and `sidecar` to ensure skill adoption doesn't depend on agents remembering the AGENTS.md skill-selection convention.

```bash
# Typically invoked internally, not directly by agents
skill-context "deploy project-a to staging" 4000
```

### Scoring and thresholds

| Threshold | Context | Purpose |
|-----------|---------|---------|
| 0.50 | Manual agent invocation | Default for skill-rank relevance |
| 0.60 | Automatic injection | Stricter for skill-context to avoid wrong-skill injection |

## Integration points

All four utilities are available as CLI tools from any directory via PATH symlinks in `$AGENT_OS_HOME/.local/bin/`. The `skill-context.sh` script is called from deterministic dispatch paths (droid-exec, agent-workflow runner, sidecar) for automatic skill injection. `skill-pack` resolves skill names to SKILL.md files by searching shared skills directories, state skills, and `.claude/skills`.

## Key source files

| File | Purpose |
|------|---------|
| `scripts/skill-rank` | Skill registry search and relevance scoring |
| `scripts/skill-pack` | Section extraction from SKILL.md files with budget-aware truncation |
| `scripts/context-pack.sh` | Cross-tier memory bundling for handoffs |
| `scripts/skill-context.sh` | Auto-injection of relevant skill context for deterministic dispatch |
| `skills/shared/skill-optimizer/SKILL.md` | Skill definition with usage examples and integration notes |
