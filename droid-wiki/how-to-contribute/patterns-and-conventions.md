# Patterns and conventions

## Purpose

Agent OS has established patterns and conventions that every agent should follow when working in this codebase. This page documents the coding rules, skill-selection convention, report format, and other cross-cutting concerns.

## Coding rules

Every agent follows six rules defined in `AGENTS.md`:

1. **Think before coding** — no silent assumptions. State what you're assuming. Ask before guessing.
2. **Simplicity first** — minimum code that solves the problem. No speculative features.
3. **Surgical changes** — touch only what you must. Don't improve adjacent code.
4. **Goal-driven execution** — define success criteria. Loop until verified.
5. **Skill-selection convention** — before loading any skill SKILL.md, run `skill-rank "<task>" --top 3 --json` to find the best match.
6. **Verify before trusting** — if you read a doc that makes a factual claim, check the live state before acting.

## Hard rules

Machine-readable hard rules are defined in `registry/hard_rules.yaml`. Key prohibitions:

| Rule | Severity | Rationale |
|---|---|---|
| Never commit secrets to version control | Blocking | Prevent credential exposure |
| Never use rm, rmdir, or shred | Blocking | Preserve evidence and enable rollback |
| Use absolute paths only | Blocking | Prevent ambiguity in multi-user and CI environments |
| Verify claims against live state | Warning | Prevent acting on stale documentation |
| Minimum code that solves the problem | Suggestion | Prevent over-engineering |
| ACP workers must not use git commands | Blocking | Prevent autonomous git modification |
| Install scripts must be idempotent | Blocking | Prevent state corruption |

## Report conventions

Every task report must end with three sections defined in `docs/AGENT_REPORT_CONVENTIONS.md`:

### STUMBLES
List anything that was blocked, worked around, or uncertain during the task. Include specific errors, what was tried, and what remains unresolved.

### CONFIRMED
List every surface or component touched that worked correctly without stumbling.

### ARTIFACTS
List every file created or modified during the task with full paths and one-line summaries.

## CLI facade pattern

The `bin/` directory contains lightweight facade scripts that delegate to Python implementations. The pattern is:

```bash
#!/bin/bash
# <tool-name> — short description
exec /usr/bin/python3 "$(dirname "$(dirname "$(readlink -f "$0")")")/<implementation_path>" "$@"
```

Examples:
- `bin/memory-st` → `memory/core/short_term.py`
- `bin/agent-voice` → `scripts/agent_voice.py`
- `bin/memory-recall` → `scripts/recall.sh`

## Registry-driven configuration

All tools, skills, workflows, agents, and memory tiers are defined in YAML registries under `registry/`. Each registry file follows a schema with `id`, `description`, and reference fields. Registries are validated by `scripts/registry-check.py`.

## Idempotent installs

The installer (`install.sh`) must be idempotent — running it repeatedly must not change the system state after the first successful run. The installer checks prerequisites, creates config files only if missing, and does not overwrite existing user configuration.

## Gate-based validation

Changes are validated through a series of gates:

- **Privacy gate** (`tests/privacy/privacy_gate.sh`) — scans for prohibited patterns, owner identifiers, and secrets
- **Release gate** (`scripts/gate-release.sh`) — comprehensive validation including privacy, syntax, registries, clean-room install, and permissions
- **Cold boot test** (`tests/smoke/cold_boot.sh`) — structure and syntax validation

## Key source files

| File | Purpose |
|---|---|
| `AGENTS.md` | Coding rules and agent entrypoint |
| `registry/hard_rules.yaml` | Machine-readable hard rules |
| `docs/AGENT_REPORT_CONVENTIONS.md` | Report format standard |
| `docs/HANDOFF_AUTHORING_STANDARD.md` | Handoff document standard |
| `docs/SPEC_TEMPLATE.md` | Specification template |
| `install.sh` | Idempotent installer |
| `scripts/gate-release.sh` | Authoritative release gate |
