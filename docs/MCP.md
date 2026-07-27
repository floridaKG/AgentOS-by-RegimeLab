# MCP (Model Context Protocol) Setup

Agent OS provides a local MCP server that exposes memory and diagnostics tools
over stdio transport. This allows AI coding agents to read and write memory
using the MCP protocol.

## Quick Start

```bash
# Start the MCP server
agent-os mcp serve

# Or run directly
bin/agent-os-mcp
```

## MCP Tools

The server exposes these tools:

| Tool | Description |
|------|-------------|
| `memory_search` | Search memory records using full-text search |
| `memory_write` | Add a memory record with safe defaults |
| `memory_list` | List memory records with optional filters |
| `memory_health` | Check memory subsystem health |
| `agent_os_doctor` | Run comprehensive diagnostic checks |
| `capabilities` | Report version, platform, and features |

## Client Configuration

### Claude Code

```bash
# Install MCP config for Claude
agent-os mcp install --client claude

# Or dry-run to see what would be done
agent-os mcp install --client claude --dry-run
```

This adds the following to `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "agent-os": {
      "command": "/absolute/path/to/python3",
      "args": ["-m", "agent_os.mcp_server"],
      "env": {}
    }
  }
}
```

### Codex

```bash
# Install MCP config for Codex
agent-os mcp install --client codex

# Or dry-run to see what would be done
agent-os mcp install --client codex --dry-run
```

This adds the following to `~/.codex/config.json`:

```json
{
  "mcp_servers": {
    "agent-os": {
      "command": "/absolute/path/to/python3",
      "args": ["-m", "agent_os.mcp_server"],
      "env": {}
    }
  }
}
```

### OpenCode

```bash
# Install MCP config for OpenCode
agent-os mcp install --client opencode

# Or dry-run to see what would be done
agent-os mcp install --client opencode --dry-run
```

This adds the following to `~/.opencode/config.json`:

```json
{
  "mcp_servers": {
    "agent-os": {
      "command": "/absolute/path/to/python3",
      "args": ["-m", "agent_os.mcp_server"],
      "env": {}
    }
  }
}
```

## Uninstalling

```bash
# Uninstall MCP config for a client
agent-os mcp uninstall --client claude

# Or dry-run to see what would be done
agent-os mcp uninstall --client claude --dry-run
```

## Options

| Flag | Description |
|------|-------------|
| `--client` | Required. Client: `claude`, `codex`, or `opencode` |
| `--dry-run` | Show what would be done without making changes |
| `--force` | Overwrite existing config or skip parse errors |

## Security Notes

- The MCP server runs locally and does not send data to external services
- Configuration files are modified only when explicitly requested
- The server refuses malformed config files unless `--force` is used
- Only the Agent OS entry is modified; unrelated config is preserved

## Requirements

- Python 3.10+
- MCP package (`pip install mcp`)
- Agent OS installed and configured

## Troubleshooting

### MCP package not found

```bash
pip install mcp
```

### Config file parse error

```bash
# Check the config file for syntax errors
cat ~/.claude/settings.json | python3 -m json.tool

# Force overwrite (backs up nothing)
agent-os mcp install --client claude --force
```

### Agent already installed

```bash
# Check if agent-os is already in the config
agent-os mcp install --client claude

# Force reinstall
agent-os mcp install --client claude --force
```
