# SuperDocs

SuperDocs is an optional documentation harness for any project. It provides
a structured `docs/` tree that agents can navigate and maintain.

## What SuperDocs Gives You

- **Governance**: project policies, decision records, standards
- **Guardrails**: operational rules and coding conventions
- **Skills**: agent skill definitions for your project
- **Workflows**: repeatable multi-step processes
- **Registry**: structured project metadata (features, infra, data sources)

## Quick Start

```bash
# Scaffold for a new project
bash scripts/init-superdocs.sh --project my-project --path /path/to/project

# Scaffold for current directory
bash scripts/init-superdocs.sh --project my-project
```

This creates a `docs/` tree with starter files you can customize.

## Structure

```
docs/
  governance/       Policies, decision records, standards
  guardrails/       Operational rules and coding conventions
  skills/           Agent skill definitions
  workflows/        Repeatable processes
  registry/         Structured project metadata
```

## Customization

1. Edit `governance/POLICY.md` with your project rules
2. Add skills to `skills/` and register in `skills/SKILL_GLOSSARY.md`
3. Define workflows in `workflows/` and index in `workflows/WORKFLOW_INDEX.md`
4. Add registry files for features, infrastructure, and data sources

## Files

| File | Purpose |
|---|---|
| `START_HERE.md` | Entry point for agents navigating your docs |
| `governance/` | Policies, decisions, standards |
| `guardrails/` | Operational rules and conventions |
| `skills/` | Agent skill definitions |
| `workflows/` | Repeatable processes |
| `registry/` | Structured project metadata |
