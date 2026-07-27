# Pinecone Adapter — Optional Semantic Memory

## Status

Optional adapter. Not required for the default memory profile.

## Purpose

Provides vector-based semantic search across Agent OS memory, enabling
cross-session recall by semantic similarity rather than keyword matching.

## Requirements

- Pinecone API key (`PINECONE_API_KEY`)
- Pinecone index name (default: `agent-vault`)

## How to enable

1. Set `PINECONE_API_KEY` and `PINECONE_INDEX` in your environment or
   `~/.config/agent-os/secrets.env`
2. The core memory system auto-detects the key and activates the Pinecone
   integration on next boot

## Integration points

- `promote.py` in core/ pushes lessons to the Pinecone lessons namespace
  during the nightly promotion cycle
- `recall_hook.py` uses Pinecone as a recall source when available
- The `recall` command merges Pinecone results with local SQLite results

## Health check

```bash
bash $AGENT_OS_HOME/scripts/agent-os-health.sh
```

## Commercial extension

A hosted memory plane may replace self-managed Pinecone with a managed
embeddings service. This adapter is the open-source integration point that
the commercial product can supersede.
