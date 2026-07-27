# CodeGraph — Code Structure Query Engine

CodeGraph is a pre-indexed code knowledge graph (Tree-sitter → SQLite) that answers
structural questions — who calls X, what X calls, what breaks if X changes — in a
single query instead of 5–15 manual grep/read chains.

**Status in Agent OS:** External dependency. Not bundled; users install separately.

## Installation

```bash
npm install -g @codegraph/cli
```

Then index your project:

```bash
cd /path/to/your/project
codegraph index
```

## Agent Integration

Once indexed, agents with MCP client support can use CodeGraph tools for structural
code queries. Configure the MCP server in your agent's config.

## Key Operations

| Query | CLI | What it does |
|-------|-----|--------------|
| Find symbol | `codegraph query "funcName"` | Locate definitions |
| Callers | `codegraph callers funcName` | Who calls this? |
| Callees | `codegraph callees funcName` | What does this call? |
| Impact | `codegraph impact funcName` | What breaks if I change this? |
| Context | `codegraph context "task desc"` | Map a feature area |
| Files | `codegraph files` | Code-only file tree |

## When to Use CodeGraph vs grep

- **CodeGraph:** structural questions (who calls X, what depends on Y, blast radius)
- **grep:** simple text search (find all occurrences of a string)

CodeGraph adds ~600ms overhead per query. It earns that back on structural questions
that would take 3–8 grep/read chains otherwise.
