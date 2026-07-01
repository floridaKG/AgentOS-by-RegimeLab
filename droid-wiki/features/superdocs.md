# SuperDocs

## Purpose

SuperDocs is an optional documentation harness for any project. It provides a structured `docs/` tree that agents can navigate and maintain, with predefined directories for governance, guardrails, skills, workflows, and registry metadata. It standardizes how projects surface rules, conventions, and capabilities to AI agents.

## How it works

SuperDocs is scaffolded by running `init-superdocs.sh`, which creates a `docs/` tree under the target project directory:

```
docs/
  governance/       Policies, decision records, standards
  guardrails/       Operational rules and coding conventions
  skills/           Agent skill definitions
  workflows/        Repeatable processes
  registry/         Structured project metadata
```

### Quick start

```bash
# Scaffold for a new project at a specific path
bash scripts/init-superdocs.sh --project my-project --path /path/to/project

# Scaffold for the current directory
bash scripts/init-superdocs.sh --project my-project
```

### Directory contents

| Directory | Starter files | Purpose |
|-----------|---------------|---------|
| `governance/` | `POLICY.md`, `README.md`, `decision-log.md` | Project policies, architecture decisions, standards |
| `guardrails/` | `README.md`, `conventions.md` | Operational rules and coding conventions agents must follow |
| `skills/` | `SKILL_GLOSSARY.md`, `README.md` | Agent skill definitions for this project |
| `workflows/` | `WORKFLOW_INDEX.md`, `README.md` | Repeatable multi-step processes |
| `registry/` | `README.md` | Structured project metadata (features, infra, data sources) |

### Agent entrypoint

The SuperDocs scaffold includes an `AGENTS.md` that instructs agents to read in order:

1. `docs/governance/POLICY.md` — project rules and standards
2. `docs/guardrails/conventions.md` — coding conventions
3. `docs/skills/SKILL_GLOSSARY.md` — available agent skills

### Hard rules embedded in the scaffold

Agents using SuperDocs must:
- Read `docs/governance/POLICY.md` before making changes
- Record architecture decisions in `docs/governance/decision-log.md`
- Update documentation alongside code changes
- Run `check-governance.sh` before submitting changes

### CI workflow integration

The scaffold includes a `.github/workflows/governance-check.yml` CI workflow that validates governance compliance on push and pull request events.

### Customization

After scaffolding, teams customize the documentation:

1. Edit `governance/POLICY.md` with project-specific rules
2. Add skills to `skills/` and register in `skills/SKILL_GLOSSARY.md`
3. Define workflows in `workflows/` and index in `workflows/WORKFLOW_INDEX.md`
4. Add registry files for features, infrastructure, and data sources

## Integration points

SuperDocs is project-scoped and does not integrate directly with Agent OS memory tiers. However, the `recall.sh` script can be configured to search a project's SuperDocs tree via workspace-specific tiers. The `init-superdocs.sh` script uses the skeleton at `examples/superdocs/` as its template source.

## Key source files

| File | Purpose |
|------|---------|
| `examples/superdocs/` | SuperDocs skeleton directory with starter files |
| `scripts/init-superdocs.sh` | Shell script to scaffold a SuperDocs `docs/` tree |
| `examples/superdocs/README.md` | SuperDocs overview, structure, and customization guide |
