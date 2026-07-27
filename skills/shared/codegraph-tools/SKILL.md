---
name: codegraph-tools
description: Use CodeGraph for structural code queries (callers, callees, impact, trace, definition) instead of multi-call grep/read chains. Pre-indexed code knowledge graph. Saves 3-8 tool calls per structural query. MCP tools where available, CLI everywhere.
last_reviewed: 2026-07-13
---

# CodeGraph Tools

**CodeGraph is an OPTIONAL external dependency.** It is NOT bundled with Agent OS
and must be installed separately via `npm install -g @codegraph/cli`. Without
CodeGraph, Agent OS agents fall back to grep/read chains for structural code
queries. No functionality is lost — structural queries just take more tool calls.

CodeGraph is a pre-indexed code knowledge graph (Tree-sitter → SQLite). It answers
*structural* questions — who calls X, what X calls, what breaks if X changes, how X
reaches Y — that grep can only answer with 5-15 manual read/search chains.

Users must install and index their own workspaces:
```bash
codegraph init /path/to/your/project
codegraph index /path/to/your/project
```

## When to Use

| Query type | MCP tool | CLI | Why not grep |
|------------|----------|-----|--------------|
| "Where is symbol X defined?" | `codegraph_search` | `codegraph query "X" -p <repo>` | grep finds text; CodeGraph returns structured symbol data |
| "What calls function X?" | `codegraph_callers` | `codegraph callers X -p <repo>` | grep needs 3-8 chained calls |
| "What does X call?" | `codegraph_callees` | `codegraph callees X -p <repo>` | multi-grep walk |
| "What breaks if I change X?" | `codegraph_impact` | `codegraph impact X -p <repo>` | manual blast radius = 5-15 calls |
| "How does X reach Y?" | `codegraph_trace` | (use impact/callees) | requires connecting multiple files |
| "Map this feature area" | `codegraph_context` | `codegraph context "task" -p <repo>` | 5+ search_files calls |
| Code-only file tree | `codegraph_files` | `codegraph files -p <repo>` | faster than ls for code dirs |

## When NOT to Use

Simple text search ("find all occurrences of this string"). Use grep — CodeGraph
earns its overhead only on *structural* questions.

## Agent Coverage (on-demand, no persistent daemon)

Two transports for the same indexes. MCP gives native tools; CLI works everywhere.

| Agent | Transport | Config / mechanism |
|-------|-----------|--------------------|
| Claude Code | MCP tools | `~/.claude/settings.json` → `mcpServers.codegraph` |
| Codex CLI | MCP subprocess | `~/.codex/config.toml` → `[mcp_servers.codegraph]` |
| OpenCode | MCP (local) | `~/.config/opencode/opencode.jsonc` → `mcp.codegraph` |
| Any agent | CLI only | Shell out to the `codegraph` CLI |

If your tool list has no `codegraph_*` tools, you are CLI-only: the CLI always works.

## CLI flag gotcha (read before scripting)

CLI argument form is **inconsistent by command**:
- **Positional path:** `status`, `files`, `sync`, `index` → `codegraph status "/path/to/repo"`
- **`-p` flag:** `query`, `callers`, `callees`, `impact`, `context` → `codegraph query "X" -p "/path/to/repo"`

Using the wrong form silently ignores the path.

## Index freshness

Indexes are point-in-time snapshots; they rot as code changes. Keep them current
by running `codegraph sync "/path/to/repo"` periodically or setting up a cron job.

## Initial Setup

```bash
# Install the codegraph CLI (see codegraph.dev or your package manager)
# Index your project (one-time):
codegraph init /path/to/your/project
codegraph index /path/to/your/project

# Verify:
codegraph status /path/to/your/project    # expect Files/Nodes counts
codegraph query "SomeSymbol" -p /path/to/your/project  # expect symbol hits
```

## Pitfalls

- ~600ms Node+SQLite cold-start per session; first query is slowest.
- A new project needs `codegraph init` + `codegraph index` once before queries work.
- MCP server can be left `enabled: false` after install — verify the agent's config.
