# Tooling

## Purpose

Agent OS uses a combination of built-in tools and external dependencies. This page documents the tooling landscape.

## Built-in CLI tools

The `bin/` directory contains 19 executable facades. Key categories:

### Memory operations

| Tool | Path | Purpose |
|---|---|---|
| `memory-st` | `bin/memory-st` | Short-term memory operations (write, query) |
| `memory-lt` | `bin/memory-lt` | Long-term memory operations (search, promote) |
| `memory-recall` | `bin/memory-recall` | Cross-tier memory search |
| `memory-recall-safe` | `bin/memory-recall-safe` | Fallback-safe memory search |
| `memory-inject` | `bin/memory-inject` | Build packet-scoped memory context |
| `memory-promote` | `bin/memory-promote` | Promote short-term to long-term storage |

### Agent communication

| Tool | Path | Purpose |
|---|---|---|
| `acp-task` | `bin/acp-task` | Enqueue a task for ACP dispatch |
| `acp-daemon` | `bin/acp-daemon` | ACP daemon process |
| `acp-health` | `bin/acp-health` | ACP health check |
| `acp-provider-smoke` | `bin/acp-provider-smoke` | Provider smoke test |
| `agent-mail` | `bin/agent-mail` | Cross-agent messaging |

### Multi-agent orchestration

| Tool | Path | Purpose |
|---|---|---|
| `team` | `bin/team` | MOE and multi-provider panels |
| `agent-workflow` | `bin/agent-workflow` | Swarm, council, dialogue, red-team workflows |

### Agent feedback

| Tool | Path | Purpose |
|---|---|---|
| `agent-voice` | `bin/agent-voice` | Capture agent friction and ideas |

### Governance

| Tool | Path | Purpose |
|---|---|---|
| `spec-check` | `bin/spec-check` | Validate specification documents |
| `command-risk-check` | `bin/command-risk-check` | Check command risk levels |

## Scripts

The `scripts/` directory contains 23 implementation scripts:

| Script | Purpose |
|---|---|
| `agent-os-boot.sh` | Bootstrap session |
| `agent-os-health.sh` | Run health checks |
| `agent-os-verify.sh` | Verify installation integrity |
| `skill-rank` | Rank skills by relevance |
| `skill-pack` | Extract bounded context packs |
| `context-pack.sh` | Bundle context for handoffs |
| `recall.sh` | Search across memory tiers |
| `registry-check.py` | Validate registry consistency |
| `hard-rule-smoke.sh` | Smoke-test hard rules |
| `gate-release.sh` | Authoritative release gate |
| `gate-privacy.sh` | Privacy gate runner |
| `init-vault.sh` | Create or link knowledge vault |
| `init-superdocs.sh` | Scaffold SuperDocs for a project |
| `agent_voice.py` | Agent Voice backend |
| `build-manifest.py` | Build export manifest |

## External dependencies

| Tool | Package | License | Install |
|---|---|---|---|
| ACPx | `acpx` | MIT | `npm install -g acpx` |
| CodeGraph | `@codegraph/cli` | MIT | `npm install -g @codegraph/cli` |

Python dependencies (minimal):
- `pyyaml>=6.0` — YAML parsing for registries

Optional integrations:
- Pinecone (`pinecone>=9.0.0`) — semantic memory
- Neo4j (`neo4j>=5.20.0`) — graph memory

## RTK (Token-Efficient CLI Proxy)

RTK is a high-performance CLI proxy that filters and summarizes system output before it reaches an LLM context. It provides compact alternatives to standard commands:

| RTK command | Replaces | Token savings |
|---|---|---|
| `rtk ls` | `ls -la` | Drops permissions, owners, sizes |
| `rtk read file.py -l aggressive` | `cat file.py` | Drops comments, blanks |
| `rtk grep "pattern"` | `grep -r` | Groups by file, truncates lines |
| `rtk git status` | `git status` | Compact format |

## Key source files

| File | Purpose |
|---|---|
| `docs/rtk-usage-guide.md` | RTK usage reference |
| `docs/codegraph-setup.md` | CodeGraph setup guide |
| `requirements.txt` | Python dependencies |
| `registry/tools.yaml` | Tools registry |
