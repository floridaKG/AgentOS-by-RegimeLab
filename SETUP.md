# Agent OS Setup Guide

## Overview

Agent OS is an agent-agnostic harness for orchestrating AI coding agents
with shared memory, enforced protocols, and cross-agent learning.

This guide covers installation, configuration, verification, and optional
integrations. The default installation works entirely locally with zero
external services.

## Prerequisites

- **Python 3.10+** — check with `python3 --version`
- **Git** (optional) — needed for skill updates
- **Node.js 18+** (optional) — needed for some plugins
- **One LLM provider API key** — OpenAI, Anthropic, or OpenRouter-compatible

### Supported Platforms

- Linux (Debian/Ubuntu, Fedora, Arch)
- macOS (Homebrew or system Python)
- WSL2 (Windows Subsystem for Linux — required for Windows users)

## Windows Users (WSL2)

Agent OS is a Linux-native CLI harness. Windows users **must install WSL2**.

1. **Install WSL2:**
   ```powershell
   # Run in PowerShell as Administrator:
   wsl --install -d Ubuntu-24.04
   ```
   Restart your PC when prompted. On first launch, create a Linux username and password.

2. **Open Ubuntu** from the Start Menu. All subsequent commands run inside this terminal.

3. **Clone Agent OS inside the Linux filesystem** (do NOT clone under `/mnt/c/` — cross-filesystem I/O hurts SQLite performance):
   ```bash
   git clone https://github.com/floridaKG/AgentOS-by-RegimeLab.git ~/AgentOS-by-RegimeLab
   cd ~/AgentOS-by-RegimeLab
   ./install.sh
   ```

4. **Windows files are accessible at `/mnt/c/`.** You can work on projects stored on your Windows drive, but keep Agent OS itself in the Linux home directory.

5. **All Agent OS CLI commands run inside WSL.** There is no native Windows terminal support.

## Quick Install

```bash
git clone https://github.com/floridaKG/AgentOS-by-RegimeLab.git
cd AgentOS-by-RegimeLab
./install.sh
```

Or download and extract a release archive, then run `./install.sh` from the
extracted directory.

## What the Installer Does

1. Checks prerequisites (Python, Git, Node.js)
2. Verifies repo structure
3. Creates `~/.config/agent-os/config.env` and `secrets.env`
4. Installs Python dependencies from `requirements.txt`
5. Verifies all CLI entry points (`bin/`) and health scripts (`scripts/`)
6. Initializes the memory directory (SQLite database, schema)
7. **Installs multi-agent configuration** under `~/.config/agent-workflows/` — roles, model aliases, panels, safety rules, ACP dispatch scripts, and swarm/council/dialogue orchestration workflows
8. **Auto-adds `$AGENT_OS_HOME/bin` to PATH** in your shell profile (`~/.bashrc`, `~/.zshrc`, or `~/.profile`)

The installer is **idempotent** — running it again is safe and will not
overwrite existing configuration.

### Non-Interactive Test Mode

```bash
AGENT_OS_TEST=1 ./install.sh
```

Skips pip install and interactive prompts. Useful for CI and verification.

## Configuration

### Minimum Configuration (Local-Core Only)

After installation, edit `~/.config/agent-os/config.env`:

```bash
# Source this file in your shell profile
source ~/.config/agent-os/config.env

# Required: your LLM provider
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

## Memory Profiles

| Profile | Components | When to Use |
|---|---|---|
| **Local/Core** | SQLite only | Default. Works offline, no external deps |
| **Semantic** | Local + Pinecone | Cross-session semantic recall |
| **Graph** | Local + Neo4j | Relationship-based memory queries |
| **Full** | Local + Pinecone + Neo4j | Maximum memory capabilities |

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

### Try the Unified CLI

Agent OS ships with a unified CLI that dispatches to 18 subsystems:

```bash
python3 $AGENT_OS_HOME/scripts/agent-os --help
python3 $AGENT_OS_HOME/scripts/agent-os doctor
python3 $AGENT_OS_HOME/scripts/agent-os health
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
printf '{"workspace":"home","intent":"OPS","objective":"test lesson"}' > /tmp/agent-os-packet.json
memory-inject --packet /tmp/agent-os-packet.json --dry-run

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

### Installing ACPx (Universal Agent Launcher)

ACPx launches and manages AI coding agents through a unified interface.
It is MIT-licensed and installed separately:

```bash
npm install -g acpx
```

Verify:

```bash
acpx --version
```

ACPx provides: cooperative cancellation, named parallel sessions, crash
reconnect, and cross-model DAG orchestration. See `docs/ARCHITECTURE.md`
for details.

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

### Installing CodeGraph (Code Structure Queries)

CodeGraph answers structural code questions (who calls X, what does X call,
what breaks if I change X) in a single query instead of chaining grep/read.

```bash
npm install -g @codegraph/cli
```

Then index your project:

```bash
cd /path/to/your/project
codegraph index
```

See `docs/codegraph-setup.md` for the full reference.

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
0 2 * * * /bin/bash -c 'source ~/.config/agent-os/config.env && AGENT_OS_HOME/bin/stumble-triage'

# Weekly cleanup on Sunday at 3 AM
0 3 * * 0 /bin/bash -c 'source ~/.config/agent-os/config.env && AGENT_OS_HOME/bin/stumble-cleanup'
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
cd AgentOS-by-RegimeLab
git pull
./install.sh
```

The installer is idempotent — it will update dependencies and verify
structure without overwriting your configuration.

## Uninstall / Archive

Agent OS does not use system-wide installation. To remove:

1. Remove the agent-os directory: `rm -rf /path/to/agent-os`
2. Remove config: `rm -rf ~/.config/agent-os`
3. Remove memory state: `rm -rf $AGENT_OS_HOME/.local/state/agent-os`

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
