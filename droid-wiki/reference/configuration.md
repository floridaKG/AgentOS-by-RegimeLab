# Configuration

## Overview

Agent OS is configured through environment variables, config files, and memory tier profiles. The default installation works with zero external services — only `LLM_PROVIDER` and `LLM_API_KEY` are required.

## Environment variables

### Core variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `AGENT_OS_HOME` | Yes | Install directory | Root of Agent OS installation |
| `LLM_PROVIDER` | Yes | — | LLM provider name (openai, anthropic, openrouter) |
| `LLM_API_KEY` | Yes | — | API key for your LLM provider |
| `VAULT_PATH` | No | — | Path to knowledge vault |
| `AGENT_STATE_DIR` | No | `.agent-os` | Agent state directory name |

### Optional memory adapters

| Variable | Required For | Description |
|---|---|---|
| `PINECONE_API_KEY` | Pinecone (semantic) | Pinecone API key |
| `PINECONE_INDEX` | Pinecone (semantic) | Pinecone index name |
| `NEO4J_URI` | Neo4j (graph) | Neo4j connection URI |
| `NEO4J_USER` | Neo4j (graph) | Neo4j username |
| `NEO4J_PASSWORD` | Neo4j (graph) | Neo4j password |
| `LESSONS_NAMESPACE` | Pinecone | Vector namespace (default: `agent-os-lessons`) |

### Session compressor

| Variable | Default | Description |
|---|---|---|
| `SESSION_COMPRESS_MODEL` | `deepseek-v4-flash` | Override the LLM model for session compression |
| `SESSION_COMPRESS_BASE_URL` | `https://opencode.ai/zen/go/v1` | Override the API base URL |
| `OPENCODE_GO_API_KEY` | — | API key for the session compressor |

### Short-term memory

| Variable | Default | Description |
|---|---|---|
| `AGENT_OS_ST_DB` | `~/.local/state/agent-os/memory/short_term.sqlite` | Override the SQLite database path (for testing) |

## Config files

### config.env

The primary configuration file at `~/.config/agent-os/config.env`:

```bash
export AGENT_OS_HOME=$HOME/agent-os
export LLM_API_KEY=your-api-key-here
export LLM_PROVIDER=openai
```

Shell integration: `source ~/.config/agent-os/config.env` in `.bashrc` or `.zshrc`.

### config.env.template

The file `config.env.template` at the repository root serves as a template:

```
AGENT_OS_HOME=$HOME/agent-os
LLM_API_KEY=your-api-key-here
LLM_PROVIDER=openai
# PINECONE_API_KEY=your-pinecone-key
# NEO4J_URI=neo4j+s://your-instance.databases.neo4j.io
```

### secrets.env

Sensitive credentials (Pinecone, Neo4j) are stored separately at `~/.config/agent-os/secrets.env` to avoid committing them to version control.

## Memory profiles

Agent OS supports four memory profiles, each with different capabilities and dependencies:

| Profile | Components | Dependencies | Use Case |
|---|---|---|---|
| **Local/Core** | SQLite + FTS5 | None (Python stdlib) | Always-on local storage, works offline |
| **Semantic** | Local + Pinecone | `PINECONE_API_KEY`, `PINECONE_INDEX` | Cross-session semantic recall |
| **Graph** | Local + Neo4j | `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` | Relationship-based memory queries |
| **Full** | Local + Pinecone + Neo4j | All above | Maximum memory capabilities |

### Memory tier details (from `registry/memory_tiers.yaml`)

| Tier | Layer | Backend | Status |
|---|---|---|---|
| `short_term` | short-term | SQLite + FTS5 | **core** — always available |
| `pinecone` | long-term-vector | Pinecone | **optional** — requires API key |
| `neo4j` | long-term-graph | Neo4j | **optional** — requires connection |

The health check (`agent-os-health.sh`) reports GREEN for core tiers and DEGRADED for optional tiers when their dependencies are not configured.

## Additional configuration

### Agent workflows

Located at `~/.config/agent-workflows/`:

| File | Purpose |
|---|---|
| `roles.toml` | Role-to-agent mappings for ACP dispatch |
| `panels.toml` | MOE panel definitions |
| `model_aliases.toml` | User-defined model aliases |

### PATH setup

For full functionality, add to your shell profile:

```bash
export PATH="$AGENT_OS_HOME/bin:$PATH"
export PATH="$AGENT_OS_HOME/scripts:$PATH"
```

## Key files

| File | Purpose |
|---|---|
| `config.env.template` | Configuration template |
| `SETUP.md` | Full installation and configuration guide |
| `registry/memory_tiers.yaml` | Memory tier definitions |
| `~/.config/agent-os/config.env` | User configuration (created by installer) |
| `~/.config/agent-os/secrets.env` | User secrets (created by installer) |
