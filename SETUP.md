# Agent OS Setup Guide

## Overview

Agent OS is an agent-agnostic harness for orchestrating AI coding agents
with shared memory, enforced protocols, and cross-agent learning.

This guide covers installation, configuration, verification, and optional
integrations. The default installation works entirely locally with zero
external services.


For the fastest setup, review and run:

```bash
curl -fsSL https://raw.githubusercontent.com/floridaKG/AgentOS-by-RegimeLab/main/bootstrap.sh | bash
```

This clones into `~/.local/share/agent-os`, runs the installer, and leaves the
checkout available for ACP workflow installation. Pin a release tag or review
the script first when supply-chain control is required. After installation,
run `agent-os setup --check` for a headless gap report, or `agent-os-setup`
for the human-readable readiness check.

## Agent-driven setup (recommended)

If you use Claude Code or any agent with shell access, you do not need to
configure everything by hand. Point the agent at this repo and say
**"set me up."** The agent follows the sequence in
[docs/AGENT_SETUP.md](docs/AGENT_SETUP.md): it verifies the core install,
installs rtk, ACPx, and CodeGraph, detects your agent CLIs, wires providers
it finds in your environment, routes roles and workspaces, and verifies the
result. Agent OS never collects API keys; Claude Code's own login is the
credential for the Claude lane.

- **Diagnostic:** `agent-os setup --check` prints a headless JSON gap report
  (what is ready, what is missing, and the exact fix command for each gap).
- **What stays manual:** account signups (Anthropic, and a provider for
  open-source models such as OpenRouter or an OpenAI-compatible endpoint),
  and interactive logins like `claude` or `codex` on a fresh machine.

## Prerequisites

### Required (Local Core)

- **Python 3.10+ and pip** — check with `python3 --version` and `python3 -m pip --version`
- **Git** — check with `git --version`
- **Bash** — standard on Linux and WSL2
- **No API key for the local core**. An authenticated agent CLI and provider API
  key are required only when you enable ACP multi-agent dispatch.

### Optional (not part of Local Core)

- **curl** — only for advanced RTK install (`./install.sh --with-rtk`)
- **Node.js 18+ and npm** — only if you install ACPx or CodeGraph
- **ACPx** — `npm install -g acpx` for real multi-agent dispatch (without it, ACP dry-runs)
- **Pinecone API key** — semantic memory (vector search across sessions)
- **Neo4j credentials** — graph memory (relationship-based queries)
- **Hindsight** — optional memory bank (`pip install hindsight-client` + running API)

### Supported Platforms

| Platform | Status |
|---|---|
| Linux (Debian/Ubuntu, Fedora, Arch) | ✅ Tested (v1 supported) |
| WSL2 (Windows Subsystem for Linux) | ✅ Tested (v1 supported) |
| macOS | ⚠️ ACPx may run, but the Agent OS daemon/workflows are not verified |

## Windows Users (WSL2)

Agent OS's full CLI harness and daemon are Linux-native. Windows users
**must install WSL2**. ACP and ACPx themselves are cross-platform in principle,
but the surrounding Agent OS shell workflows are currently verified only on
Linux and WSL2.

1. **Install WSL2:**
   ```powershell
   # Run in PowerShell as Administrator:
   wsl --install -d Ubuntu-24.04
   ```
   Restart your PC when prompted. On first launch, create a Linux username and password.

2. **Open Ubuntu** from the Start Menu. All subsequent commands run inside this terminal.

3. **Clone Agent OS inside the Linux filesystem** (do NOT clone under `/mnt/c/` — cross-filesystem I/O hurts SQLite performance):
   ```bash
   git clone https://github.com/floridaKG/AgentOS-by-RegimeLab.git ~/agent-os
   cd ~/agent-os
   ./install.sh
   ```

4. **Windows files are accessible at `/mnt/c/`.** You can work on projects stored on your Windows drive, but keep Agent OS itself in the Linux home directory.

5. **All Agent OS CLI commands run inside WSL.** There is no native Windows terminal support.

## Quick Install

```bash
git clone https://github.com/floridaKG/AgentOS-by-RegimeLab.git
cd agent-os
./install.sh
```

Or download and extract a release archive, then run `./install.sh` from the
extracted directory.

### MCP Server Setup

After installation, you can set up the MCP server for your AI coding agent:

```bash
# Start the MCP server
agent-os mcp serve

# Install MCP config for Claude Code
agent-os mcp install --client claude

# Install MCP config for Codex
agent-os mcp install --client codex

# Install MCP config for OpenCode
agent-os mcp install --client opencode
```

See [docs/MCP.md](docs/MCP.md) for full documentation.

## What the Installer Does

1. Checks prerequisites (Python 3.10+, Git, Bash)
2. Verifies repo structure
3. Creates `~/.config/agent-os/config.env` and `secrets.env`
4. Installs Python dependencies from `requirements.txt`
5. Verifies all CLI entry points (`bin/`) and health scripts (`scripts/`)
6. Initializes the memory directory (SQLite database, schema)
7. **Installs multi-agent workflow configuration** under `~/.config/agent-workflows/` — roles, model aliases, panels, safety rules, ACP dispatch scripts, and swarm/council/dialogue orchestration workflows
8. **Auto-adds `$AGENT_OS_HOME/bin` to PATH** in your shell profile (`~/.bashrc`, `~/.zshrc`, or `~/.profile`)

**What the installer does NOT install by default:**
- RTK (Rust Token Killer) — advanced opt-in with `./install.sh --with-rtk` (downloads a third-party install script over HTTPS)
- ACPx (universal agent launcher) — external npm package, install separately
- CodeGraph (structural code queries) — external npm package, install separately
- Shell profile edits — skip with `./install.sh --no-path` if you manage PATH yourself

The Python wheel provides the packaged local CLI and MCP core. Multi-agent ACP
workflows are distributed with the full repository checkout and installed by
`install.sh`; `pip install agent-os` alone does not provide `acp-task`,
`acp-daemon`, or the workflow configuration.

The installer is **idempotent** — running it again is safe and will not
overwrite existing configuration files.

### Non-Interactive Test Mode

```bash
AGENT_OS_TEST=1 ./install.sh
```

Skips pip install and interactive prompts. Useful for CI and verification.

## Configuration

### Minimum Configuration (Local-Core Only)

The local core works without provider configuration. For ACP dispatch, edit
`~/.config/agent-os/config.env` and authenticate the provider CLI separately:

```bash
# Source this file in your shell profile
source ~/.config/agent-os/config.env

# Used by optional integrations and workflow tooling
export LLM_PROVIDER="openai"    # or "anthropic", "openrouter"
export LLM_API_KEY="your-api-key-here"
```

**Never commit your API key to version control.**

### Shell Profile Integration

Add to `~/.bashrc`, `~/.zshrc`, or equivalent:

```bash
source ~/.config/agent-os/config.env
export PATH="$AGENT_OS_HOME/bin:$PATH"
```

### Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `AGENT_OS_HOME` | Yes | install directory | Root of Agent OS installation |
| `LLM_PROVIDER` | Yes | — | LLM provider name |
| `LLM_API_KEY` | Yes | — | API key for your LLM provider |
| `VAULT_PATH` | No | — | Path to knowledge vault |
| `PINECONE_API_KEY` | No | — | Pinecone API key (optional) |
| `PINECONE_INDEX` | No | — | Pinecone index name (optional) |
| `NEO4J_URI` | No | — | Neo4j connection URI (optional) |
| `NEO4J_USER` | No | — | Neo4j username (optional) |
| `NEO4J_PASSWORD` | No | — | Neo4j password (optional) |
| `HINDSIGHT_BANK` | No | — | Hindsight bank id (optional adapter) |
| `HINDSIGHT_API_URL` | No | `http://127.0.0.1:9177` | Hindsight API base URL |
| `HINDSIGHT_PROFILE` | No | `default` | Provenance label for digests |

## Memory Profiles

| Profile | Components | When to Use |
|---|---|---|
| **Local/Core** | SQLite only | Default. Works offline, no external deps |
| **Semantic** | Local + Pinecone | Cross-session semantic recall |
| **Graph** | Local + Neo4j | Relationship-based memory queries |
| **Hindsight** | Local + Hindsight bridge/GC | Import digests from a Hindsight bank |
| **Full** | Local + any combination | Maximum memory capabilities for your setup |

The default install uses **Local/Core**. All other profiles require
additional configuration and external services.

### Enabling Pinecone (Optional)

Add to `~/.config/agent-os/secrets.env`:

```bash
export PINECONE_API_KEY="your-pinecone-key"
export PINECONE_INDEX="agent-vault"
```

### Enabling Neo4j (Optional)

Add to `~/.config/agent-os/secrets.env`:

```bash
export NEO4J_URI="neo4j+s://your-instance.databases.neo4j.io"
export NEO4J_USER="your-username"
export NEO4J_PASSWORD="your-password"
```

### Enabling Hindsight (Optional)

Hindsight is a **working optional adapter**, not a stub. Full guide:
`memory/adapters/hindsight/ADAPTER.md`.

```bash
# 1. Client package
pip install 'hindsight-client>=0.4.22'

# 2. Config (config.env or secrets.env)
export HINDSIGHT_API_URL="http://127.0.0.1:9177"
export HINDSIGHT_BANK="your-bank-id"
export HINDSIGHT_PROFILE="default"

# 3. Verify
hindsight-health
# or: python3 $AGENT_OS_HOME/scripts/hindsight-health-check.py

# 4. Export digests into Agent OS short-term memory
hindsight-bridge --dry-run --limit 20
hindsight-bridge --limit 50
```

Requires a running Hindsight API. Local Core SQLite keeps working if you skip this.

## Verifying Installation

Run the health check:

```bash
bash $AGENT_OS_HOME/scripts/agent-os-health.sh
```

Expected output: all checks pass, memory health shows GREEN for local tier.

Run the verification script:

```bash
bash $AGENT_OS_HOME/scripts/agent-os-verify.sh
```

## What's Available After Install

After a default install, these subsystems are ready to use:

| Subsystem | Command | Description |
|---|---|---|
| Health check | `bash $AGENT_OS_HOME/scripts/agent-os-health.sh` | Verify all systems operational |
| Memory (write) | `memory-st write ...` | Record lessons, stumbles, decisions |
| Memory (recall) | `memory-recall --text "query"` | Search memory by text |
| Memory (inject) | `memory-inject --packet file.json` | Inject from packet file |
| Agent Voice | `agent-voice emit ...` | Report friction and improvements |
| Multi-agent | `team fire ...` | Dispatch multi-agent panels |
| Unified CLI | `python3 $AGENT_OS_HOME/scripts/agent-os` | All-in-one CLI dispatcher |

Not included by default (install separately if needed):

| Tool | Install command | Purpose |
|---|---|---|
| RTK | `./install.sh --with-rtk` | Token savings CLI proxy |
| ACPx | `npm install -g acpx` | Universal agent launcher |
| CodeGraph | `npm install -g @codegraph/cli` | Structural code queries |

### Try the Unified CLI

Agent OS ships with a unified CLI that dispatches to 18 subsystems:

```bash
python3 $AGENT_OS_HOME/scripts/agent-os --help
python3 $AGENT_OS_HOME/scripts/agent-os doctor
python3 $AGENT_OS_HOME/scripts/agent-os health
```

## First-Run Checklist

After running `./install.sh`, follow this sequence to verify everything works:

```bash
# 1. Source the config (or open a new terminal)
source ~/.config/agent-os/config.env

# 2. Add your LLM API key
#    Edit ~/.config/agent-os/config.env and set LLM_API_KEY

# 3. Verify installation health
bash $AGENT_OS_HOME/scripts/agent-os-health.sh

# 4. Register a workspace (optional — create one for your project)
mkdir -p ~/my-agent-os-workspace
#    Add to ~/.config/agent-os/config.env:
#    export AGENT_OS_WORKSPACE="$HOME/my-agent-os-workspace"

# 5. Write your first memory lesson
memory-st write --run-id first-run --agent-id test --workspace home \
  --intent LESSON --kind observation \
  --summary "First run verified" --content-file /dev/stdin \
  --source-ref cli:first-run <<< "Installation complete, memory system working."

# 6. Recall your lesson
memory-recall --text "first run"

# 7. Check what's available
bash $AGENT_OS_HOME/scripts/agent-os-health.sh --verbose
```

## Getting Started

1. **Read `AGENTS.md`** — the entry point for every agent session
2. **Read `BOOT.md`** — the intent router for matching tasks to capabilities
3. **Explore `skills/shared/`** — available shared skills
4. **Read `memory/README.md`** — memory system architecture
5. **Try a recall**: `memory-recall --text "test query"` (after adding bin/ to PATH)

### First Memory Operation

```bash
# Initialize the memory database (first run only)
python3 $AGENT_OS_HOME/memory/core/short_term.py init

# Write a lesson
memory-st write --run-id test-run --agent-id test-agent --workspace home \
  --intent LESSON --kind observation \
  --summary "Test lesson" --content-file /dev/stdin \
  --source-ref cli:test <<< "This is a test lesson"

# Search for it
memory-recall --text "test lesson"

# Dry-run packet memory injection
PACKET_FILE="$AGENT_OS_HOME/.local/state/agent-os/agent-os-packet.json"
mkdir -p "$(dirname "$PACKET_FILE")"
printf '{"workspace":"home","intent":"OPS","objective":"test lesson"}' > "$PACKET_FILE"
memory-inject --packet "$PACKET_FILE" --dry-run

# Check memory health
bash $AGENT_OS_HOME/scripts/agent-os-health.sh
```

### Agent Voice

Agent Voice is enabled locally after install:

```bash
agent-voice emit --kind friction --statement "Setup step was unclear"
agent-voice list --limit 10
```

## Optional: Knowledge Vault

A knowledge vault is an optional user-owned knowledge workspace for
storing structured notes, research, and agent-readable content.

### Create a Vault

```bash
bash scripts/init-vault.sh --create ~/my-vault
```

**Note:** The vault uses Obsidian-compatible `[[wikilink]]` syntax for cross-referencing.
Installing Obsidian (https://obsidian.md) gives you graph view, backlinks, and visual
navigation for your vault. This is optional — the wikilinks work in any markdown editor.

### Link an Existing Vault

```bash
bash scripts/init-vault.sh --link ~/existing-kb
```

The vault path is written to `~/.config/agent-os/config.env` as `VAULT_PATH`.

**Vault ownership**: The vault is your content. Agent OS reads and writes
to it, but you own the data. Back it up independently.

## Optional: SuperDocs

SuperDocs is a project documentation harness that agents can navigate.

### Scaffold for a Project

```bash
bash scripts/init-superdocs.sh --project my-project --path /path/to/project
```

This creates a `docs/` tree with governance, guardrails, skills,
workflows, and registry directories.

## Optional: Agent Integration

Agent OS supports multiple AI agents through ACP (Agent Communication
Protocol). Configure your preferred agent in the registry.

See `registry/agents.yaml` for supported agent types and configuration.

### ACPx (Universal Agent Launcher) — Optional, External

ACPx is an external MIT-licensed tool that launches and manages AI coding
agents through a unified interface. It is **not part of the Agent OS default
install** and must be installed separately if you need it:

```bash
npm install -g acpx
```

Requires Node.js 18+ and npm. ACPx provides cooperative cancellation, named
parallel sessions, crash reconnect, and cross-model DAG orchestration.

### Adding another ACP-compatible agent

Agent OS is extensible. The built-in registry includes common integrations,
but users can add any ACP-compatible agent that their installed ACPx supports:

1. Add an agent entry under `~/.config/agent-os/registry/agents.yaml` (or the
   repository `registry/agents.yaml` before installation).
2. Add a role mapping in `~/.config/agent-workflows/roles.toml`, using the ACPx
   agent/profile name as `provider` and the provider's advertised model ID as
   `model`.
3. Verify the profile directly with `acpx <agent> exec "ping"` before using it
   in a workflow.

Custom provider names are accepted when they contain only letters, numbers,
periods, underscores, or hyphens. Agent OS does not assume every provider
supports the same model-selection flags, so provider-specific setup remains
the source of truth.

### Configuring MOE and Multi-Agent Panels

Agent OS installs the `team` dispatcher and example configuration under:

```text
~/.config/agent-workflows/panels.toml
~/.config/agent-workflows/model_aliases.toml
~/.config/agent-workflows/roles.toml
```

Replace the example aliases with model IDs available from your installed
providers. Then validate configuration without making provider calls:

```bash
team fire --tier 2 \
  --members "claude default, codex default" \
  --task "Review this architecture" \
  --dry-run --json
```

Available modes include quick parallel panels, provider-diverse swarms,
read-only review swarms, persistent collaboration, red-team review, and
sequential pipelines. Provider credentials remain in each provider's normal
CLI/configuration; Agent OS does not copy or store them.

### CodeGraph (Code Structure Queries) — Optional, External

CodeGraph is an external tool that answers structural code questions (who
calls X, what does X call, what breaks if I change X) in a single query.
It is **not part of the Agent OS default install** and must be installed
separately if you need it:

```bash
npm install -g @codegraph/cli
cd /path/to/your/project
codegraph index
```

### Setting Up the Self-Learning Loop

Agent OS includes a stumble capture → triage → review → promotion pipeline
that lets your agents learn from their mistakes over time. The tools ship with
the core install, but you need a scheduler (cron, systemd timer, or similar)
to run them automatically.

**Tools in the loop:**

| Step | Command | Runs |
|---|---|---|
| Record stumbles | `log-stumble <workspace> "<summary>"` | Agents call this during sessions |
| Triage clusters | `stumble-triage` | Daily |
| Review decisions | `stumble-review list` then `stumble-review decide <fp> fix` | After triage |
| Apply fixes | `python3 $AGENT_OS_HOME/scripts/stumble-apply-decision.py --apply --all` | After review |
| Cleanup | `stumble-cleanup` | Weekly |

**Example cron setup** (add to `crontab -e`):

```bash
# Daily stumble triage at 2 AM
0 2 * * * /bin/bash -c 'source ~/.config/agent-os/config.env && $AGENT_OS_HOME/bin/stumble-triage'

# Weekly cleanup on Sunday at 3 AM
0 3 * * 0 /bin/bash -c 'source ~/.config/agent-os/config.env && $AGENT_OS_HOME/bin/stumble-cleanup'
```

**Manual workflow** (run interactively):

```bash
# 1. Agents record stumbles as they work
log-stumble home "ACP dispatch timed out after 300s" --source-ref cli:my-session

# 2. Daily: triage clusters
stumble-triage

# 3. Review undecided clusters
stumble-review list
stumble-review show <fingerprint>
stumble-review decide <fingerprint> fix --note "Added timeout retry"

# 4. Weekly: clean stale reports
stumble-cleanup
```

The pipeline uses the same SQLite memory database as `memory-st`. Decisions
are stored in the `st_decisions` table. Reports land in
`~/.local/state/agent-os/stumble-reports/`.

## Upgrade

```bash
cd agent-os
git pull
./install.sh
```

The installer is idempotent — it will update dependencies and verify
structure without overwriting your configuration.

## Uninstall / Archive

Agent OS does not use system-wide installation. To remove:

1. Remove the agent-os directory: `rm -rf /path/to/agent-os`
2. Remove config: `rm -rf ~/.config/agent-os` and `rm -rf ~/.config/agent-workflows`
3. Remove memory state: `rm -rf ~/.local/state/agent-os`
4. Remove any PATH lines you added to `~/.bashrc` / `~/.zshrc` / `~/.profile`

Or archive by moving the directory.

## Troubleshooting

| Problem | Likely Cause | Fix |
|---|---|---|
| `AGENT_OS_HOME not set` | Missing config | Source `~/.config/agent-os/config.env` |
| Memory health shows DEGRADED | Optional adapter missing | Expected if no Pinecone/Neo4j configured |
| `skill-pack` not found | Scripts not in PATH | Add `$AGENT_OS_HOME/scripts` to PATH |
| Python import errors | Missing dependencies | `pip install -r requirements.txt` |
| `memory-st: command not found` | bin/ not in PATH | Add `$AGENT_OS_HOME/bin` to PATH |
| YAML parse errors | Corrupted registry file | Re-download or restore from git |

## Support Boundaries

The open-source Agent OS is community-supported. For issues:

1. Check this troubleshooting table
2. Search existing issues on GitHub
3. File a new issue with reproduction steps

Commercial support, managed memory infrastructure, and enterprise features
are available separately.
