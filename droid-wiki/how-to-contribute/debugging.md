# Debugging

## Purpose

This page covers common issues, debugging techniques, and troubleshooting steps for Agent OS.

## Health check

The fastest way to diagnose issues:

```bash
bash $AGENT_OS_HOME/scripts/agent-os-health.sh
```

This checks file structure, registry validity, skill presence, and memory tier health.

## Common problems

### AGENT_OS_HOME not set

Source the config file:

```bash
source ~/.config/agent-os/config.env
```

Add this to your shell profile (`~/.bashrc` or `~/.zshrc`) to make it permanent.

### Memory health shows DEGRADED

If only the local tier shows DEGRADED, that indicates a problem with the SQLite database. Run:

```bash
python3 $AGENT_OS_HOME/memory/core/short_term.py init
```

This creates the database if it doesn't exist. It's safe to run multiple times.

If Pinecone or Neo4j tiers show DEGRADED, that's expected when those services are not configured. See the health check output for which tiers are optional.

### Python import errors

```bash
pip install -r $AGENT_OS_HOME/requirements.txt
```

### CLI tool not found

Add `bin/` and `scripts/` to your PATH:

```bash
export PATH="$AGENT_OS_HOME/bin:$AGENT_OS_HOME/scripts:$PATH"
```

### ACP daemon not running

```bash
bash $AGENT_OS_HOME/scripts/acp-daemon-setup.sh
```

This starts the daemon in a tmux session named `acp`.

## Debugging the memory database

The SQLite database is at `~/.local/state/agent-os/memory/short_term.sqlite`. Inspect it directly:

```bash
sqlite3 ~/.local/state/agent-os/memory/short_term.sqlite
.tables
SELECT id, intent, summary FROM records LIMIT 10;
```

For testing without affecting the live database:

```bash
export AGENT_OS_ST_DB="/tmp/test-memory.sqlite"
```

## Boot diagnostics

Run the boot script to see detailed diagnostics:

```bash
bash $AGENT_OS_HOME/scripts/agent-os-boot.sh
```

This shows:
- Whether `config.env` was found and sourced
- Whether `secrets.env` exists and has valid keys
- Health check results
- Current session state

## Key source files

| File | Purpose |
|---|---|
| `scripts/agent-os-boot.sh` | Boot sequence with diagnostics |
| `scripts/agent-os-health.sh` | Health check script |
| `scripts/agent-os-verify.sh` | Installation verification |
| `SETUP.md` | Troubleshooting table and setup guide |
