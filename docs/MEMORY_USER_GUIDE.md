# Memory User Guide

> A practical reference for working with Agent OS memory.
> For architecture details, see `memory/README.md`.

## Overview

Agent OS has a three-tier memory system. Every session starts with the
short-term tier available; semantic and graph tiers are optional add-ons.

| Tier | Backend | Status | Purpose |
|---|---|---|---|
| Short-Term | SQLite | Always on | Recent activity, lessons, stumbles, decisions |
| Semantic | Pinecone | Optional | Vector search across sessions |
| Graph | Neo4j | Optional | Relationship queries, provenance |

## Profiles

| Profile | Components | Use Case |
|---|---|---|
| **Local/Core** | SQLite only | Default. Works offline, zero external services |
| **Semantic** | SQLite + Pinecone | Cross-session semantic recall |
| **Graph** | SQLite + Neo4j | Relationship-based memory queries |
| **Full** | All three | Maximum memory capabilities |

## Writing to Memory

Use the `memory-st` CLI to record observations:

```bash
memory-st write --run-id <run-id> --agent-id <agent-id> \
  --workspace <workspace> --intent LESSON --kind observation \
  --summary "..." --content-file <content-file> --source-ref cli:...
```

### Supported Intents

| Intent | When to Use |
|---|---|
| `LESSON` | A practice, rule, or insight worth preserving |
| `STUMBLE` | Something that went wrong; a gotcha or pitfall |
| `DECISION` | A design choice with rationale |
| `CONFIRMED` | Something verified to work correctly |

### Examples

```bash
# Record a lesson
memory-st write --run-id boot-001 --agent-id explorer \
  --workspace cockpit --intent LESSON --kind observation \
  --summary "Always source config.env before calling health checks" \
  --content-file lesson.txt --source-ref cli:manual

# Record a stumble
memory-st write --run-id boot-001 --agent-id explorer \
  --workspace cockpit --intent STUMBLE --kind bug \
  --summary "BOOT_FACTS.yaml missing caused boot failure at step 2" \
  --content-file stumble.txt --source-ref cli:manual
```

## Recalling from Memory

### Quick recall

```bash
recall "your search query"
```

### Targeted recall

```bash
recall --tier=cockpit "query"
recall --semantic "query"    # Pinecone vector search
recall --hybrid "query"      # Merge vector + FTS5 + graph results
recall --explain "query"     # Show provenance for each hit
```

### Low-level recall

```bash
memory-lt search-vector --text "query" --namespace all --limit 10
memory-recall-safe --text "query" --limit 10
```

## Health Checks

```bash
bash $AGENT_OS_HOME/scripts/agent-os-health.sh
```

Expected output: short-term tier shows GREEN. Optional tiers show
DEGRADED if not configured (expected) or GREEN if operational.

## Promotion Pipeline

Records flow through four stages:

```
Capture → Filter → Promote → Prune
```

1. **Capture** — facts, tool events, errors, outcomes recorded during work
2. **Filter** — compress, deduplicate, classify (keep only useful signals)
3. **Promote** — stable facts written to semantic/graph memory or source docs
4. **Prune** — long-term memory stays curated, not an unbounded dump

Records with intent LESSON, STUMBLE, DECISION, or CONFIRMED are eligible for
promotion to Pinecone or Neo4j when those adapters are configured. Promotion
is performed explicitly with `memory-promote`. The recall hook can inject
recently promoted memories into new agent sessions.

### Manual promotion

```bash
# Show promotion candidates without writing to optional providers
memory-promote --target st-vector --dry-run --limit 5

# Promote one short-term record to the graph tier
memory-promote --target graph --short-term-id <record-id> \
  --reason "stable lesson"

# Print promotion backlog and provider health
memory-promote --target report
```

If Pinecone or Neo4j is not configured, long-term operations fail closed with
JSON errors and local SQLite memory continues to work.

## Memory Injection and Hooks

Use `memory-inject` when you have a task packet and want a scoped
`memory_context` JSON payload:

```bash
memory-inject --packet packet.json --token-budget 1000 --dry-run
memory-inject --packet packet.json --token-budget 1000 --out memory_context.json
```

The recall hook is available at `memory/core/recall_hook.py`. Agent wrappers can
call it before a prompt is sent:

```bash
python3 $AGENT_OS_HOME/memory/core/recall_hook.py --agent codex < prompt.txt
```

The hook reads local SQLite first and uses optional Pinecone/Neo4j tiers only
when they are configured.

## Agent Feedback

Agents can report friction, improvement ideas, and risks without editing docs:

```bash
agent-voice emit --kind friction --statement "Describe the friction"
agent-voice list --limit 10
```

## Offline Operation

Local/Core mode works entirely offline. Zero external services are
required. All operations use SQLite locally. Semantic and graph tiers
are strictly optional and only activate when their config variables
are set.

## Reference

- Architecture: `memory/README.md`
- CLI: `bin/memory-st`, `bin/memory-lt`, `bin/memory-recall`,
  `bin/memory-recall-safe`, `bin/memory-inject`, `bin/memory-promote`
- Scripts: `scripts/agent-os-health.sh`
