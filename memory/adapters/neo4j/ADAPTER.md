# Neo4j Adapter — Optional Graph Memory

## Status

Optional adapter. Not required for the default memory profile.

## Purpose

Provides graph-based relationship memory for Agent OS, enabling
structured queries across memory entities, stumbles, and resolutions.

## Requirements

- Neo4j AuraDB or self-hosted instance
- Connection credentials (`NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`)

## How to enable

1. Set `NEO4J_URI`, `NEO4J_USER`, and `NEO4J_PASSWORD` in your environment
   or `~/.config/agent-os/secrets.env`
2. The core memory system auto-detects credentials and activates the graph
   integration

## Integration points

- `promote.py` in core/ pushes resolved lessons to Neo4j as graph nodes
- The graph complements SQLite short-term memory by adding relationship
  queries

## Health check

```bash
bash $AGENT_OS_HOME/scripts/agent-os-health.sh
```

## Schema reference

See `$AGENT_OS_HOME/memory/core/schema_neo4j.cypher` for the graph schema.

## Commercial extension

A hosted memory plane may provide managed graph sync and observability.
This adapter defines the open integration surface.
