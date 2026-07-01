# Memory recall

## Purpose

Memory recall provides a unified search interface across all memory tiers — SQLite short-term memory, filesystem-based cockpit/workspace/vault stores, optional Pinecone vector search, optional Neo4j graph search, and CASS session history. The `/recall` skill lets agents ask "what do we already know about X" before starting new work, preventing redundant investigation and surfacing prior decisions.

## How it works

The recall system searches across these tiers:

| Tier | Backend | Search method |
|------|---------|---------------|
| Short-term | SQLite | FTS5 full-text search via `memory-st query` |
| Cockpit | Filesystem | `grep` on `$AGENT_OS_HOME/memory.md` + `lessons.md` |
| Workspace | Filesystem | `grep` on `<workspace>/docs/MEMORY.md` + `LESSONS.md` |
| Vault | Filesystem | `grep` on `findings/`, `insights/`, `Topics/` |
| Vector | Pinecone | Semantic search via `memory-lt` |
| Graph | Neo4j | Entity relationship queries |
| Sessions | CASS | Raw session history from Claude Code, Codex, OpenCode |

### Invocation forms

| Command | Behavior |
|---------|----------|
| `/recall \<query\>` | Grep all tiers, return top 20 hits with file path + line number |
| `/recall --tier=\<name\> \<query\>` | Restrict to one tier (cockpit, user, workspace, vault, sessions) |
| `/recall --semantic \<query\>` | Pinecone vector search (falls back to grep if not configured) |
| `/recall --explain \<query\>` | Default search with per-result metadata (tier, method, score, freshness, reliability) |

### Context pack for handoffs

For bounded context bundles suitable for reasoning model handoffs, use the `context-pack` command:

```bash
context-pack "<query>" --budget=8000
```

This queries multiple memory tiers, deduplicates, scores by relevance, and packs top-down until the byte budget is exhausted.

### Automated recall injection

The `recall_hook.py` script runs automatically on every agent prompt submission. It:

1. Reads the incoming prompt
2. Checks a health gate (cached golden-canary verdict)
3. Recalls via `memory-recall-safe --limit 8`
4. Filters, ranks, and keeps the top 3 results
5. Formats a `<agent_os_memory>` context block
6. Emits the context block for injection into the agent's working session

The hook is fail-safe: internal errors produce no output and exit 0.

## Integration points

The `recall_hook.py` integrates with Claude Code and Codex via the `UserPromptSubmit` hook `additionalContext` contract. It runs before every agent turn, automatically injecting relevant prior lessons into the agent's context window. The `context-pack.sh` script interfaces with the skill-optimizer system for handoff bundles.

## Key source files

| File | Purpose |
|------|---------|
| `skills/shared/recall/SKILL.md` | The `/recall` skill definition with invocation forms and examples |
| `scripts/recall.sh` | Shell script implementing cross-tier memory search |
| `bin/memory-recall` | Canonical programmatic recall facade (delegates to `memory-recall-safe.py`) |
| `bin/memory-recall-safe` | Compatibility facade for fallback-safe recall |
| `memory/core/recall_hook.py` | Auto-injection hook for agent prompt context |
| `bin/memory-inject` | CLI tool to inject memory context into agent packets |
