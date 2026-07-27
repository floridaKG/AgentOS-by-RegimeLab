#!/usr/bin/env bash
# check-governance.sh — Validate a SuperDocs governance directory.
#
# Usage:
#   check-governance.sh --path /path/to/project/docs [--fix]
#
# Checks:
#   - Required directories exist
#   - Required files exist with non-empty content
#   - YAML files parse correctly (if any)
#   - Policy contains actual rules (not just TBD placeholders)
#   - Decision log has at least one ADR or the template
#
# Exit codes:
#   0 — All checks pass
#   1 — One or more checks failed

set -euo pipefail

# ── color helpers ─────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

pass_count=0
fail_count=0
warn_count=0

# ── state ─────────────────────────────────────────────────────────────────────
DOCS_DIR=""
FIX=false

# ── usage ─────────────────────────────────────────────────────────────────────
usage() {
  cat <<EOF
Usage: $(basename "$0") --path <dir> [--fix]

Validate a SuperDocs governance directory structure and content.

Options:
  --path <dir>   Path to the docs/ directory to check. REQUIRED.
  --fix          Auto-create missing directories.
  --help         Show this help message.

Exit codes:
  0  All checks pass
  1  One or more checks failed
EOF
  exit 0
}

# ── parse args ────────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --path)
      DOCS_DIR="$2"
      shift 2
      ;;
    --fix)
      FIX=true
      shift
      ;;
    --help|-h)
      usage
      ;;
    *)
      echo "Error: unknown option: $1" >&2
      echo "Run '$(basename "$0") --help' for usage." >&2
      exit 1
      ;;
  esac
done

if [[ -z "$DOCS_DIR" ]]; then
  echo "Error: --path <dir> is required." >&2
  echo "Run '$(basename "$0") --help' for usage." >&2
  exit 1
fi

if [[ ! -d "$DOCS_DIR" ]]; then
  echo "Error: directory not found: ${DOCS_DIR}" >&2
  exit 1
fi

# ── helper: check result ──────────────────────────────────────────────────────
check_result() {
  local check_name="$1"
  local status="$2"  # pass, fail, warn
  local details="$3"
  case "$status" in
    pass)
      echo -e "  [${GREEN}PASS${NC}] ${check_name}"
      pass_count=$((pass_count + 1))
      ;;
    fail)
      echo -e "  [${RED}FAIL${NC}] ${check_name}: ${details}"
      fail_count=$((fail_count + 1))
      ;;
    warn)
      echo -e "  [${YELLOW}WARN${NC}] ${check_name}: ${details}"
      warn_count=$((warn_count + 1))
      ;;
  esac
}

# ── check: required directories ───────────────────────────────────────────────
check_directories() {
  local required_dirs=("governance" "guardrails" "skills" "workflows" "registry")
  local all_found=true
  for dir in "${required_dirs[@]}"; do
    if [[ ! -d "${DOCS_DIR}/${dir}" ]]; then
      echo -e "  [${RED}FAIL${NC}] Missing directory: ${dir}/"
      all_found=false
      fail_count=$((fail_count + 1))
      if [[ "$FIX" == true ]]; then
        mkdir -p "${DOCS_DIR}/${dir}"
        echo "         Created: ${DOCS_DIR}/${dir}/"
      fi
    fi
  done
  if [[ "$all_found" == true ]]; then
    check_result "Required directories" "pass" ""
  fi
}

# ── check: required files ─────────────────────────────────────────────────────
check_files() {
  local required_files=(
    "governance/POLICY.md"
    "governance/decision-log.md"
    "guardrails/conventions.md"
    "skills/SKILL_GLOSSARY.md"
    "workflows/WORKFLOW_INDEX.md"
  )
  local all_found=true
  for file in "${required_files[@]}"; do
    if [[ ! -f "${DOCS_DIR}/${file}" ]]; then
      echo -e "  [${RED}FAIL${NC}] Missing file: ${file}"
      all_found=false
      fail_count=$((fail_count + 1))
    elif [[ ! -s "${DOCS_DIR}/${file}" ]]; then
      echo -e "  [${RED}FAIL${NC}] Empty file: ${file}"
      all_found=false
      fail_count=$((fail_count + 1))
    fi
  done
  if [[ "$all_found" == true ]]; then
    check_result "Required files exist and non-empty" "pass" ""
  fi
}

# ── check: YAML validation ────────────────────────────────────────────────────
check_yaml() {
  local yaml_files
  yaml_files=$(find "$DOCS_DIR" -name "*.yaml" -o -name "*.yml" 2>/dev/null)
  if [[ -z "$yaml_files" ]]; then
    check_result "YAML validation" "warn" "No YAML files found to validate"
    return
  fi
  local has_errors=false
  while IFS= read -r yaml_file; do
    if command -v python3 &>/dev/null; then
      if ! python3 -c "
import yaml, sys
try:
    with open('${yaml_file}') as f:
        yaml.safe_load(f)
except Exception as e:
    sys.exit(1)
" 2>/dev/null; then
        echo -e "  [${RED}FAIL${NC}] Invalid YAML: ${yaml_file##*/}"
        has_errors=true
        fail_count=$((fail_count + 1))
      fi
    elif command -v yq &>/dev/null; then
      if ! yq eval "${yaml_file}" >/dev/null 2>&1; then
        echo -e "  [${RED}FAIL${NC}] Invalid YAML: ${yaml_file##*/}"
        has_errors=true
        fail_count=$((fail_count + 1))
      fi
    else
      echo -e "  [${YELLOW}WARN${NC}] YAML validation skipped: no python3 or yq available"
      warn_count=$((warn_count + 1))
      return
    fi
  done <<< "$yaml_files"
  if [[ "$has_errors" == false ]]; then
    check_result "YAML validation" "pass" ""
  fi
}

# ── check: policy has actual rules ────────────────────────────────────────────
check_policy() {
  local policy_file="${DOCS_DIR}/governance/POLICY.md"
  if [[ ! -f "$policy_file" ]]; then
    return  # already reported as missing
  fi
  # Check for TBD placeholder patterns suggesting the template wasn't customized
  if grep -qi "TBD" "$policy_file" 2>/dev/null || grep -qi "_Example:" "$policy_file" 2>/dev/null; then
    check_result "Policy has real rules" "fail" "Contains TBD or example placeholders"
    return
  fi
  # Check there's actual rule content beyond headings
  local rule_lines
  rule_lines=$(grep -c -E "^\- " "$policy_file" 2>/dev/null || true)
  if [[ "$rule_lines" -lt 3 ]]; then
    check_result "Policy has real rules" "fail" "Less than 3 defined rules found"
    return
  fi
  check_result "Policy has real rules" "pass" ""
}

# ── check: decision log has content ───────────────────────────────────────────
check_decision_log() {
  local log_file="${DOCS_DIR}/governance/decision-log.md"
  if [[ ! -f "$log_file" ]]; then
    return  # already reported as missing
  fi
  # Check if it has at least the ADR template or an actual ADR
  if grep -qi "ADR-NNN" "$log_file" 2>/dev/null; then
    check_result "Decision log has ADR template" "pass" ""
  elif grep -qi "^### ADR-" "$log_file" 2>/dev/null; then
    check_result "Decision log has ADR entries" "pass" ""
  else
    check_result "Decision log has ADR template" "fail" "No ADR template or entries found"
  fi
}

# ── main ──────────────────────────────────────────────────────────────────────
echo "Governance Check Report"
echo "======================"
echo "Path: ${DOCS_DIR}"
echo ""

check_directories
check_files
check_yaml
check_policy
check_decision_log

echo ""
echo "Summary: ${pass_count} passed, ${fail_count} failed, ${warn_count} warnings"

if [[ "$fail_count" -gt 0 ]]; then
  exit 1
fi
exit 0
