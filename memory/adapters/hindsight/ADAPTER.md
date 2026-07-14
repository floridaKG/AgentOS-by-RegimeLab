# Hindsight Adapter — Optional Semantic Memory Bank

## Status

Optional adapter. Not required for Local Core (SQLite). When enabled, Agent OS
can import digests from a running [Hindsight](https://pypi.org/project/hindsight-client/)
API into short-term memory, and manage bank lifecycle (GC).

## Purpose

- **Bridge** (`memory/hindsight_bridge.py`): export filtered Hindsight memories
  into Agent OS SQLite short-term storage with provenance tags.
- **GC** (`memory/hindsight_gc.py`): report / export / rebuild / prune / auto
  lifecycle for the Hindsight bank.
- **Health** (`scripts/hindsight-health-check.py`): verify client, API, and bank.

## Requirements

1. A running Hindsight API (default `http://127.0.0.1:9177`)
2. Python package: `pip install 'hindsight-client>=0.4.22'`
3. Environment:

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `AGENT_OS_HOME` | Yes | — | Agent OS install root |
| `HINDSIGHT_BANK` | Yes | — | Your Hindsight bank id |
| `HINDSIGHT_API_URL` | No | `http://127.0.0.1:9177` | API base URL |
| `HINDSIGHT_PROFILE` | No | `default` | Label used in `source_ref` provenance |
| `HINDSIGHT_STATE_DIR` | No | `~/.local/state/agent-os/hindsight` | Cursor + logs |
| `HINDSIGHT_LOG_DIR` | No | same as state dir | GC logs |
| `HINDSIGHT_GC_ARCHIVE_DIR` | No | `$AGENT_OS_HOME/memory/archive/hindsight-gc` | GC backups |

## How to enable

```bash
# 1. Install client
pip install 'hindsight-client>=0.4.22'

# 2. Configure (add to ~/.config/agent-os/config.env or secrets.env)
export HINDSIGHT_API_URL="http://127.0.0.1:9177"
export HINDSIGHT_BANK="your-bank-id"
export HINDSIGHT_PROFILE="default"   # optional label for provenance

# 3. Health check
python3 $AGENT_OS_HOME/scripts/hindsight-health-check.py

# 4. Dry-run bridge, then live export into short-term memory
python3 $AGENT_OS_HOME/memory/hindsight_bridge.py --dry-run --limit 20
python3 $AGENT_OS_HOME/memory/hindsight_bridge.py --limit 50

# 5. Lifecycle (optional)
python3 $AGENT_OS_HOME/memory/hindsight_gc.py report
```

Or use the bin facades after install: `hindsight-bridge`, `hindsight-gc`,
`hindsight-health` (if present on PATH via `$AGENT_OS_HOME/bin`).

## What stays off by default

- No bridge process runs until you invoke it (or schedule it yourself).
- Local Core SQLite memory does not depend on Hindsight.
- Delete-capable GC rebuild requires explicit flags / `LIFECYCLE_DELETE_ENABLED=1`
  where applicable — safe report/export modes are the default starting point.

## Integration points

| Component | Role |
|-----------|------|
| `memory-st write` | Bridge writes digests with tags `origin:hindsight`, `hindsight` |
| `memory-recall` / FTS | Digests become searchable in Local Core after export |
| `agent-os-health.sh` | Core health; use `hindsight-health-check.py` for this adapter |

## Privacy / safety

The bridge filters content matching denied patterns (`.ssh/`, `.env`, key
material, etc.) and never auto-deletes Agent OS records. Cursor state lives
under `~/.local/state/agent-os/hindsight/` (not in the git tree).

## Example cron (optional)

```bash
# Every hour: export new Hindsight digests into Agent OS ST
0 * * * * /bin/bash -c 'source ~/.config/agent-os/config.env && python3 $AGENT_OS_HOME/memory/hindsight_bridge.py --limit 100'
```
