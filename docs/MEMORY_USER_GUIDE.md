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

### Manual recall (always available)

The simplest way to query shared memory is `recall` or direct FTS5 search.
No configuration needed — works immediately after install:

```bash
recall "how do we handle token refresh errors"
memory-st query --text "auth token refresh" --limit 5
```

### Packet-based injection

Use `memory-inject` when you have a task packet and want a scoped
`memory_context` JSON payload:

```bash
memory-inject --packet packet.json --token-budget 1000 --dry-run
memory-inject --packet packet.json --token-budget 1000 --out memory_context.json
```

### Auto-injection via recall hook (requires one-time agent setup)

The recall hook (`memory/core/recall_hook.py`) injects relevant prior
lessons before every prompt. It searches memory, filters by relevance,
and returns a formatted `<agent_os_memory>` context block. The hook is
fail-safe: on any error it prints nothing and exits 0 — it never blocks
a prompt.

**Supported agents:** Claude Code (`--agent cc`), Codex (`--agent codex`),
Pi (`--agent pi`).

**Kill switch:** Set `AGENT_OS_RECALL_HOOK_DISABLED=1` in your environment
to disable the hook without removing the configuration.

#### Claude Code setup

Add a UserPromptSubmit hook to your Claude Code configuration. Create or
edit `~/.claude/settings.json`:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "command": "python3 $AGENT_OS_HOME/memory/core/recall_hook.py --agent cc",
        "timeout": 10000
      }
    ]
  }
}
```

Replace `$AGENT_OS_HOME` with the actual path (Claude Code does not expand
environment variables in hook command strings).

Restart Claude Code. On the next prompt, the hook fires, searches memory,
and injects relevant context. Verify it's working by checking the telemetry
log:

```bash
tail -5 ~/.local/state/agent-os/logs/memory/recall-hook.jsonl
```

Each line records whether injection succeeded and how many results were
injected.

#### Codex setup

Codex hooks use a different configuration path. Add to your Codex hook
configuration (see Codex documentation for the exact file location):

```json
{
  "onUserPromptSubmit": "python3 /absolute/path/to/agent-os/memory/core/recall_hook.py --agent codex"
}
```

#### Verifying injection is working

1. Write a test memory record:
   ```bash
   TEST_FILE="$AGENT_OS_HOME/.local/state/agent-os/test_lesson.txt"
   mkdir -p "$(dirname "$TEST_FILE")"
   echo "This is a test lesson" > "$TEST_FILE"
   memory-st write --run-id test-001 --agent-id test --workspace test \
     --intent LESSON --kind observation \
     --summary "The login endpoint rate-limits after 5 failed attempts" \
     --content-file "$TEST_FILE" --source-ref test:verify
   ```

2. Run the hook manually:
   ```bash
   echo '{"prompt":"How does the login endpoint handle rate limiting?"}' | \
     python3 $AGENT_OS_HOME/memory/core/recall_hook.py --agent cc
   ```

3. Look for `<agent_os_memory>` in the output. If present, injection is
   working. If silent (no output), the golden-canary health gate hasn't
   accumulated enough history yet — this is normal on first run. Try
   again after a few real prompts.

The hook reads local SQLite first and uses optional Pinecone/Neo4j tiers only
when they are configured. Without optional backends, injection uses FTS5
keyword matching — functional but less semantically rich.

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
