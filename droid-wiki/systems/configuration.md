# Configuration

## Purpose

Agent OS uses a layered configuration system built on environment variables, YAML files, and shell-sourced config files. This page describes how configuration flows through the system.

## Configuration layers

```mermaid
graph TD
    EnvTemplate[config.env.template] -->|install.sh creates| ConfigEnv[~/.config/agent-os/config.env]
    EnvTemplate2[.env.template] -->|install.sh creates| SecretsEnv[~/.config/agent-os/secrets.env]
    ConfigEnv -->|sourced by| BootScript[scripts/agent-os-boot.sh
    SecretsEnv -->|sourced by| BootScript
    BootScript -->|exports| EnvVars[Environment Variables]
    EnvVars -->|read by| Memory[Memory System]
    EnvVars -->|read by| ACP[ACP Daemon]
    EnvVars -->|read by| Registries[YAML Registries]

    subgraph "User config"
        ConfigEnv
        SecretsEnv
    end

    subgraph "Registry defaults"
        Registries
    end
```

## Environment variables

### Core variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `AGENT_OS_HOME` | Yes | Install directory | Root of Agent OS installation |
| `LLM_PROVIDER` | Yes | — | LLM provider name (openai, anthropic, openrouter) |
| `LLM_API_KEY` | Yes | — | API key for the LLM provider |

### Optional memory adapters

| Variable | Required for | Description |
|---|---|---|
| `PINECONE_API_KEY` | Pinecone semantic memory | Pinecone API key |
| `PINECONE_INDEX` | Pinecone semantic memory | Pinecone index name (default: agent-vault) |
| `NEO4J_URI` | Neo4j graph memory | Neo4j connection URI |
| `NEO4J_USER` | Neo4j graph memory | Neo4j username |
| `NEO4J_PASSWORD` | Neo4j graph memory | Neo4j password |

### Short-term memory override

| Variable | Default | Description |
|---|---|---|
| `AGENT_OS_ST_DB` | `~/.local/state/agent-os/memory/short_term.sqlite` | Override SQLite database path (useful for testing) |

## Config file locations

| File | Purpose | Created by |
|---|---|---|
| `~/.config/agent-os/config.env` | Primary configuration | `install.sh` |
| `~/.config/agent-os/secrets.env` | Secrets (API keys, credentials) | `install.sh` with placeholder comments |
| `~/.config/agent-workflows/panels.toml` | MOE panel definitions | `install.sh` |
| `~/.config/agent-workflows/model_aliases.toml` | Model alias mappings | `install.sh` |
| `~/.config/agent-workflows/roles.toml` | Agent role definitions | `install.sh` |
| `~/.config/agent-workflows/safety.toml` | Safety constraints | `install.sh` |

## Memory profiles

| Profile | Components | When to use |
|---|---|---|
| **Local/Core** | SQLite only | Default. Works offline, no external deps |
| **Semantic** | Local + Pinecone | Cross-session semantic recall |
| **Graph** | Local + Neo4j | Relationship-based memory queries |
| **Full** | Local + Pinecone + Neo4j | Maximum memory capabilities |

## Key source files

| File | Purpose |
|---|---|
| `config.env.template` | Configuration template with placeholders |
| `.env.template` | Secrets template with placeholders |
| `install.sh` | Creates config files during installation |
| `scripts/agent-os-boot.sh` | Sources config during boot |
| `SETUP.md` | Full configuration documentation |
