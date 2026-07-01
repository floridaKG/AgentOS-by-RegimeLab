# How to contribute

## Overview

Agent OS is an open-source project under Apache 2.0. This section covers how to work with the codebase, from picking up a task to getting changes merged.

## Quick links

- [Development workflow](development-workflow.md) - branch, code, test, PR, merge
- [Testing](testing.md) - frameworks, patterns, how to run tests
- [Debugging](debugging.md) - logs, common errors, troubleshooting
- [Patterns and conventions](patterns-and-conventions.md) - coding style, error handling, cross-cutting concerns
- [Tooling](tooling.md) - build system, linters, code generators, CI

## Before you start

Read these files in order:

1. `AGENTS.md` - the entry point for every agent session
2. `BOOT.md` - the intent router for matching tasks to capabilities
3. `docs/BOOT_FACTS.yaml` - current session state and required reads

## Pick up work

1. Scan `INDEX.md` for available skills, tools, and workflows
2. Check the registry files in `registry/` for the current system configuration
3. Look for TODO/FIXME comments in the source files
4. Run `bash scripts/agent-os-health.sh` to verify the current state

## Submit changes

1. Run the privacy gate: `bash tests/privacy/privacy_gate.sh .`
2. Verify registry consistency: `python3 scripts/registry-check.py`
3. Run the cold boot test: `bash tests/smoke/cold_boot.sh`
4. If adding new skills or tools, update the relevant registry files
5. If changing the memory schema, update `memory/core/schema_short_term.sql`

## Key source files

| File | Purpose |
|---|---|
| `AGENTS.md` | Agent entrypoint and boot routing |
| `INDEX.md` | Master index of skills, tools, workflows |
| `BOOT.md` | Intent router |
| `docs/BOOT_FACTS.yaml` | Boot facts |
| `registry/` | All registries |
