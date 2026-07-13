---
title: rtk Usage Guide
last_updated: 2026-07-13
status: active
source_of_truth: $AGENT_OS_HOME/docs/rtk-usage-guide.md
---

# rtk — Token-Efficient CLI Proxy

**IMPORTANT: RTK is NOT bundled with Agent OS.** It is a separate external
project ([github.com/rtk-ai/rtk](https://github.com/rtk-ai/rtk)) that you
must install independently. Agent OS falls back to standard commands (grep,
cat, ls) automatically when `rtk` is not on PATH. No Agent OS functionality
requires RTK — it is purely an optimization.

**rtk** is a high-performance CLI proxy that filters and summarizes system outputs before they reach your LLM context. Use it instead of standard commands to save tokens.

RTK is an external Apache 2.0 project ([github.com/rtk-ai/rtk](https://github.com/rtk-ai/rtk)) — a single Rust binary, zero dependencies, 100+ supported commands. Install it separately:

```bash
brew install rtk
# or
curl -fsSL https://raw.githubusercontent.com/rtk-ai/rtk/master/install.sh | sh
```

If not installed, Agent OS falls back to standard commands automatically.

## Quick Reference

| Command | What it does | Example |
|---------|-------------|---------|
| `rtk ls` | Ultra-dense directory listing | `rtk ls` or `rtk ls /path/to/dir` |
| `rtk read` | Read file with intelligent filtering | `rtk read file.py` or `rtk read file.py -l aggressive` |
| `rtk find` | Find files with compact tree output | `rtk find "*.py"` or `rtk find "SKILL.md" src/` |
| `rtk grep` | Compact grep (strips whitespace, truncates, groups) | `rtk grep "pattern" path/` |
| `rtk git` | Git commands with compact output | `rtk git status` or `rtk git diff` |
| `rtk diff` | Ultra-condensed diff (only changed lines) | `rtk diff` |
| `rtk log` | Filter and deduplicate log output | `rtk log` |
| `rtk err` | Run command, show only errors/warnings | `rtk err make build` |
| `rtk test` | Run tests, show only failures | `rtk test` |

## Detailed Usage

### rtk ls — Directory Listing

```bash
rtk ls                    # Current directory, dense format
rtk ls /path/to/dir       # Specific directory
```

**Output:** One entry per line, no permissions/owners/sizes. Optimized for scanning.

**Note:** rtk ls blocks sensitive paths (`.ssh/`, `.mssh/`, `*_ed25519`, `*.pem`, `.env*`).

### rtk read — File Reading

```bash
rtk read file.py                    # Normal read
rtk read file.py -l aggressive      # Aggressive filtering (strip comments, blanks)
```

**Use `-l aggressive`** when you need the structure but not the full content — saves significant tokens on large files.

### rtk find — File Discovery

```bash
rtk find "*.py"                     # Find all Python files in cwd
rtk find "SKILL.md" src/            # Find SKILL.md files under src/
rtk find "*.test.ts" --type f       # Find test files
```

**Output:** Compact tree-style list, one path per line.

### rtk grep — Text Search

```bash
rtk grep "function_name"            # Search in cwd
rtk grep "TODO" src/               # Search in specific directory
rtk grep -i "error" logs/          # Case-insensitive search
```

**Output:** Grouped by file, truncated lines, whitespace stripped. Much more compact than raw `grep -r`.

### rtk git — Git Operations

```bash
rtk git status                      # Compact status
rtk git diff                        # Condensed diff
rtk git log --oneline -10           # Recent commits
rtk git branch                      # List branches
```

**Output:** Strips noise, focuses on what changed.

### rtk err / rtk test — Error-Only Output

```bash
rtk err make build                  # Show only errors from build
rtk test                            # Show only test failures
```

**Use case:** When you only care about what went wrong, not the full output.

## Token Savings

rtk typically saves 30-70% of tokens compared to raw commands:
- `ls -la` → `rtk ls` (drops permissions, owners, sizes)
- `cat file.py` → `rtk read file.py -l aggressive` (drops comments, blanks)
- `grep -r "x" .` → `rtk grep "x"` (groups by file, truncates lines)
- `git status` → `rtk git status` (compact format)

## When NOT to Use rtk

- When you need full output (e.g., `ls -la` for permissions debugging)
- When RTK is not installed (falls back to standard tools)
- When the command is already token-efficient (e.g., `wc -l`)

## Integration

- **INDEX.md:** Quick Find entry `<!-- FIND: rtk list read find grep git ... -->`
- **Tool registry:** Listed in `agent-os/registry/tools.yaml`
