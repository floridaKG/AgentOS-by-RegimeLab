#!/usr/bin/env bash
# init-superdocs.sh — Scaffold a SuperDocs documentation structure for any project.
#
# Usage:
#   scripts/init-superdocs.sh --project <name> [--path <dir>] [--force]
#   scripts/init-superdocs.sh --help
#
# Creates a docs/ tree under <path> with governance, guardrails, skills,
# workflows, and registry directories, each pre-populated with starter files.

set -euo pipefail

# ── defaults ──────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_OS_HOME="${AGENT_OS_HOME:-$(cd "$SCRIPT_DIR/.." && pwd)}"
PROJECT=""
TARGET_PATH=""
FORCE=false
DOCS_DIR=""

# ── usage ─────────────────────────────────────────────────────────────────────
usage() {
  cat <<EOF
Usage: $(basename "$0") --project <name> [--path <dir>] [--force]
       $(basename "$0") --help

Options:
  --project <name>   Project name (used in READMEs and config). REQUIRED.
  --path <dir>       Project root directory (default: \$PWD).
  --force            Overwrite existing docs/ directory and files without prompting.
  --help             Show this help message.

Creates a SuperDocs documentation structure under <path>/docs/:
  docs/
    governance/   POLICY.md, README.md, decision-log.md
    guardrails/   README.md, conventions.md
    skills/       SKILL_GLOSSARY.md, README.md
    workflows/    WORKFLOW_INDEX.md, README.md
    registry/     README.md, project metadata
EOF
}

# ── parse args ────────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --project)
      PROJECT="$2"
      shift 2
      ;;
    --path)
      TARGET_PATH="$2"
      shift 2
      ;;
    --force)
      FORCE=true
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Error: unknown option: $1" >&2
      echo "Run '$(basename "$0") --help' for usage." >&2
      exit 1
      ;;
  esac
done

# ── validate ──────────────────────────────────────────────────────────────────
if [[ -z "$PROJECT" ]]; then
  echo "Error: --project <name> is required." >&2
  echo "Run '$(basename "$0") --help' for usage." >&2
  exit 1
fi

if [[ -z "$TARGET_PATH" ]]; then
  TARGET_PATH="$PWD"
fi

DOCS_DIR="${TARGET_PATH}/docs"

# ── check existing ────────────────────────────────────────────────────────────
if [[ -d "$DOCS_DIR" ]] && [[ "$FORCE" != true ]]; then
  echo "Error: ${DOCS_DIR} already exists." >&2
  echo "Use --force to overwrite existing files." >&2
  exit 1
fi

# ── create directories ────────────────────────────────────────────────────────
mkdir -p "$DOCS_DIR"/{governance,guardrails,skills,workflows,registry}

# ── helper: write file only if it doesn't exist (or --force) ──────────────────
write_file() {
  local path="$1"
  if [[ -f "$path" ]] && [[ "$FORCE" != true ]]; then
    return 0
  fi
  cat > "$path"
}

# ── governance ────────────────────────────────────────────────────────────────
write_file "$DOCS_DIR/governance/README.md" <<EOF
# Governance

Purpose: policies, decision records, and operational governance for **${PROJECT}**.

Open when:
- you need to review project policies or standards
- you are recording an architecture decision
- you want to understand governance conventions

## Files

| File | Purpose |
|---|---|
| \`POLICY.md\` | Project rules, standards, and conventions |
| \`decision-log.md\` | Architecture decision records (ADRs) |
EOF

write_file "$DOCS_DIR/governance/POLICY.md" <<EOF
# Project Policies: ${PROJECT}

This document defines the governing rules, standards, and conventions for **${PROJECT}**.

## Standards

<!-- List coding standards, review requirements, release criteria, etc. -->

| Standard | Description | Status |
|---|---|---|
| _Example: Code review required_ | All PRs need at least one approval | _TBD_ |
| _Example: Tests required_ | Changes to core modules need test coverage | _TBD_ |

## Conventions

<!-- Naming, structure, formatting, or process conventions. -->

## Decision Authority

<!-- Who approves what. Example: architectural changes require user sign-off. -->

## Enforcement

Policies are enforced through code review and CI checks. Exceptions must be
documented here with a rationale and expiration date.
EOF

write_file "$DOCS_DIR/governance/decision-log.md" <<EOF
# Decision Log: ${PROJECT}

Record architecture and design decisions here. Each entry follows the ADR format.

## ADR Template

\`\`\`
### ADR-NNN: <title>
- **Date:** YYYY-MM-DD
- **Status:** Proposed | Accepted | Deprecated | Superseded by ADR-XXX
- **Context:** What situation prompted this decision?
- **Decision:** What did we decide?
- **Consequences:** What are the trade-offs?
\`\`\`

---

<!-- Add new decisions below this line. -->
EOF

# ── guardrails ────────────────────────────────────────────────────────────────
write_file "$DOCS_DIR/guardrails/README.md" <<EOF
# Guardrails

Purpose: operational guardrails and conventions for **${PROJECT}**.

Guardrails protect live contracts that must not change without explicit
unlock procedures. Each guardrail names the locked surface, states the rule,
and documents the enforcement mechanism.

## How to Add a Guardrail

1. Name the locked surfaces (file paths, symbols, APIs).
2. State the rule in one sentence.
3. Cite the incident or concern that motivated it.
4. Point to the enforcing test, or mark \`enforcement: docs-only\`.
5. Document the unlock procedure.

## Files

| File | Protects |
|---|---|
| \`conventions.md\` | Coding conventions and standards |
EOF

write_file "$DOCS_DIR/guardrails/conventions.md" <<EOF
# Coding Conventions: ${PROJECT}

This document captures the coding conventions, naming standards, and structural
rules for **${PROJECT}**.

## Code Style

<!-- Language-specific style rules, formatter config, linter rules, etc. -->

## File Organization

<!-- Directory structure conventions, where things live. -->

## Naming

<!-- Naming patterns for variables, functions, files, routes, etc. -->

## Testing

<!-- Test conventions: naming, structure, coverage expectations. -->

## Documentation

<!-- When and how to document code, READMEs, inline comments. -->
EOF

# ── skills ────────────────────────────────────────────────────────────────────
write_file "$DOCS_DIR/skills/README.md" <<EOF
# Skills

Purpose: agent skill definitions for **${PROJECT}**.

Skills are reusable capability definitions that tell agents what a workflow
does, when to use it, and what tools are required.

## Files

| File | Purpose |
|---|---|
| \`SKILL_GLOSSARY.md\` | Index of all available skills with trigger conditions |

## Adding a Skill

1. Create a new \`.md\` file in this directory.
2. Add a glossary entry in \`SKILL_GLOSSARY.md\`.
3. Include: name, trigger, steps, tools required, success criteria.
EOF

write_file "$DOCS_DIR/skills/SKILL_GLOSSARY.md" <<EOF
# Skill Glossary: ${PROJECT}

Index of available agent skills for **${PROJECT}**.

| Skill | Trigger | Description |
|---|---|---|
| _Example: deploy_ | _"deploy to staging"_ | _Build, test, and push to staging_ |
| _Example: lint-fix_ | _"lint errors"_ | _Run linter and auto-fix_ |

---

<!-- Add new skills below this line. Use the format:
| skill-name | "trigger phrase" | Short description |
-->
EOF

# ── workflows ─────────────────────────────────────────────────────────────────
write_file "$DOCS_DIR/workflows/README.md" <<EOF
# Workflows

Purpose: project workflows and multi-step processes for **${PROJECT}**.

Workflows describe repeatable processes that agents or operators follow.

## Files

| File | Purpose |
|---|---|
| \`WORKFLOW_INDEX.md\` | Index of all workflows with status and ownership |

## Adding a Workflow

1. Create a new \`.md\` file in this directory.
2. Register it in \`WORKFLOW_INDEX.md\`.
3. Include: name, trigger, steps, verification, rollback.
EOF

write_file "$DOCS_DIR/workflows/WORKFLOW_INDEX.md" <<EOF
# Workflow Index: ${PROJECT}

Index of available workflows for **${PROJECT}**.

| Workflow | Status | Description |
|---|---|---|
| _Example: release_ | _Draft_ | _Version bump, changelog, tag, push_ |

---

<!-- Add new workflows below this line. Use the format:
| workflow-name | Draft/Active | Short description |
-->
EOF

# ── registry ──────────────────────────────────────────────────────────────────
write_file "$DOCS_DIR/registry/README.md" <<EOF
# Registry

Purpose: structured project metadata for **${PROJECT}**.

The registry holds machine-readable and human-readable project facts:
features, infrastructure, data sources, and configuration.

## Files

Add YAML or Markdown files here to capture:

- \`features.yaml\` — feature catalog with status and owners
- \`infra.yaml\` — infrastructure and deployment targets
- \`data-sources.yaml\` — upstream data and APIs
- \`backend.yaml\` — backend services and endpoints

## Conventions

- Keep registry files as structured YAML where possible.
- Update registry when infrastructure or features change.
- Reference registry files from governance policies when needed.
EOF

# ── print created tree ────────────────────────────────────────────────────────
echo ""
echo "SuperDocs scaffolded for '${PROJECT}' in ${DOCS_DIR}/"
echo ""
if command -v tree &>/dev/null; then
  tree "$DOCS_DIR" --charset ascii
else
  find "$DOCS_DIR" -type f | sort | while read -r f; do
    # Print relative to DOCS_DIR for readability
    echo "  ${f#${DOCS_DIR}/}"
  done
fi

# Optionally copy CI workflow
if [[ -d "${AGENT_OS_HOME}/examples/superdocs/.github" ]]; then
  echo ""
  echo "  CI governance workflow available at:"
  echo "    ${DOCS_DIR}/.github/workflows/governance-check.yml"
  echo "  (copied from examples/superdocs/.github/)"
  mkdir -p "${DOCS_DIR}/.github/workflows"
  cp -rf "${AGENT_OS_HOME}/examples/superdocs/.github/workflows/"* "${DOCS_DIR}/.github/workflows/" 2>/dev/null || true
fi
