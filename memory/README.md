# Agent OS Memory System

## Architecture

Agent OS memory is a **core-plus-adapters** architecture. The core provides
local SQLite memory after install — no cloud keys required. Optional
adapters add semantic search and graph capabilities when configured.

```
agent-os/memory/
  core/               # SQLite-backed local memory (always on)
  adapters/
    pinecone/         # Optional semantic search (Pinecone)
    neo4j/            # Optional graph memory (Neo4j)
    hindsight/        # Optional Hindsight bank bridge + GC
  hindsight_bridge.py # Export Hindsight digests → short-term SQLite
  hindsight_gc.py     # Hindsight bank lifecycle
  README.md           # This file
```

## Memory Profiles

| Profile | Components | Mandatory | Config |
|---------|-----------|-----------|--------|
| **Local/core** | SQLite short-term + lesson files | Yes | None needed |
| **Semantic** | Local + Pinecone vector search | No | `PINECONE_API_KEY` |
| **Graph** | Local + Neo4j relationship graph | No | `NEO4J_*` credentials |
| **Hindsight** | Local + Hindsight bank bridge/GC | No | `HINDSIGHT_BANK` + API |
| **Full** | Local + any combination of adapters | No | Per-adapter credentials |

The default install starts in **Local/core** mode. No external service
credentials are required.

## How It Works

### Core (always active)

- **Short-Term SQLite** (`core/short_term.py`): Records agent lessons,
  stumbles, decisions, and confirmed facts. FTS5-backed for keyword search.
- **Recall** (`core/recall_hook.py`): Merges results from all active memory
  tiers into a unified recall response.
- **Promotion** (`core/promote.py`): Validates and promotes short-term
  records to long-term storage (Pinecone and/or Neo4j when configured).
- **Citation** (`core/citation.py`): Tracks source attribution for memory
  records.
- **Health Gates**: Graceful degradation when optional backends are
  unavailable.

### Optional Adapters

- **Pinecone** (`adapters/pinecone/`): Vector embeddings for semantic
  similarity search. Activated when `PINECONE_API_KEY` is set.
- **Neo4j** (`adapters/neo4j/`): Graph relationship storage for structured
  memory queries. Activated when `NEO4J_URI` is set.
- **Hindsight** (`adapters/hindsight/`, `hindsight_bridge.py`, `hindsight_gc.py`):
  Optional bank bridge. Install `hindsight-client`, set `HINDSIGHT_BANK`, run
  the bridge to export digests into SQLite. Full guide:
  `adapters/hindsight/ADAPTER.md`.

## Environment Variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `AGENT_OS_HOME` | Yes | Path to Agent OS installation |
| `PINECONE_API_KEY` | No | Enables Pinecone semantic adapter |
| `PINECONE_INDEX` | No | Pinecone index name (default: `agent-vault`) |
| `NEO4J_URI` | No | Enables Neo4j graph adapter |
| `NEO4J_USER` | No | Neo4j username |
| `NEO4J_PASSWORD` | No | Neo4j password |
| `HINDSIGHT_BANK` | No | Enables Hindsight bridge/GC (bank id) |
| `HINDSIGHT_API_URL` | No | Hindsight API base (default `http://127.0.0.1:9177`) |
| `HINDSIGHT_PROFILE` | No | Provenance label (default `default`) |

## Fallback Behavior

The memory system degrades gracefully when optional backends are unavailable:

| Scenario | Behavior |
|----------|----------|
| No Pinecone key | Recall uses SQLite FTS5 only |
| No Neo4j credentials | Graph queries return empty |
| Pinecone rate-limited | Falls back to SQLite silently |
| Neo4j connection error | Graph promotion skipped, core continues |
| All adapters down | Local SQLite + file-based memory works fully |

## Health Check

```bash
bash $AGENT_OS_HOME/scripts/agent-os-health.sh
```

## Commercial Extension Seam

The open-source Agent OS memory is designed with a clear boundary for
commercial extensions. The following capabilities are reserved for the
commercial hosted product:

- **Hosted memory plane**: Managed Pinecone and Neo4j infrastructure
- **Managed embeddings/graph sync**: No self-hosting required
- **Observability and analytics**: Memory usage metrics and trends
- **Premium retrieval/ranking**: Advanced reranking and hybrid search
- **Team governance**: Multi-user access controls and audit trails
- **Enterprise controls**: Compliance, retention policies, SSO

The adapter interfaces (`adapters/pinecone/`, `adapters/neo4j/`) define the
open integration surface that the commercial product can supersede without
breaking the open-source core.
