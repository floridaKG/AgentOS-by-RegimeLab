#!/usr/bin/env bash
# test-init-superdocs.sh — Dedicated tests for scripts/init-superdocs.sh
# Tests: custom path/name, second-run idempotency, YAML/MD syntax, content, privacy
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STAGING_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
INIT_SCRIPT="${STAGING_DIR}/scripts/init-superdocs.sh"

# Test workspace (cleaned up after)
TEST_WORK="/tmp/test-init-superdocs-$$"
PASS=0
FAIL=0
TOTAL=0

# ── Helpers ──
pass() { PASS=$((PASS+1)); TOTAL=$((TOTAL+1)); echo "  ✓ $1"; }
fail() { FAIL=$((FAIL+1)); TOTAL=$((TOTAL+1)); echo "  ✗ $1"; }
cleanup() { rm -rf "$TEST_WORK" 2>/dev/null || true; }
trap cleanup EXIT

mkdir -p "$TEST_WORK"

echo "=== Tests for init-superdocs.sh ==="
echo ""

# ── Test 1: Scaffold with custom name and path ──
echo "TEST 1: Scaffold with custom project name and path"
PROJECT_NAME="my-test-project"
TARGET_DIR="${TEST_WORK}/target-project"
mkdir -p "$TARGET_DIR"
bash "$INIT_SCRIPT" --project "$PROJECT_NAME" --path "$TARGET_DIR"

DOCS_DIR="${TARGET_DIR}/docs"
if [[ -d "$DOCS_DIR" ]]; then
  pass "docs/ directory created"
else
  fail "docs/ directory not created"
fi

# Check all required subdirectories exist
for sub in governance guardrails skills workflows registry; do
  if [[ -d "${DOCS_DIR}/${sub}" ]]; then
    pass "docs/${sub}/ directory created"
  else
    fail "docs/${sub}/ directory not created"
  fi
done

# ── Test 2: Required files created ──
echo "TEST 2: Required files created"
REQUIRED_FILES=(
  "governance/README.md"
  "governance/POLICY.md"
  "governance/decision-log.md"
  "guardrails/README.md"
  "guardrails/conventions.md"
  "skills/README.md"
  "skills/SKILL_GLOSSARY.md"
  "workflows/README.md"
  "workflows/WORKFLOW_INDEX.md"
  "registry/README.md"
)
for f in "${REQUIRED_FILES[@]}"; do
  if [[ -f "${DOCS_DIR}/${f}" ]]; then
    pass "File exists: ${f}"
  else
    fail "File missing: ${f}"
  fi
done

# ── Test 3: Project name substituted in files ──
echo "TEST 3: Project name substituted in generated files"
NAME_FOUND=true
for f in "${REQUIRED_FILES[@]}"; do
  if [[ -f "${DOCS_DIR}/${f}" ]]; then
    if ! grep -q "$PROJECT_NAME" "${DOCS_DIR}/${f}"; then
      fail "Project name not found in ${f}"
      NAME_FOUND=false
    fi
  fi
done
if $NAME_FOUND; then
  pass "Project name substituted in all generated files"
fi

# ── Test 4: Second run is idempotent (does not overwrite user files) ──
echo "TEST 4: Second run is idempotent"
# Create user-modified files
echo "# My Custom Policy" > "${DOCS_DIR}/governance/POLICY.md"
echo "user added content" > "${DOCS_DIR}/custom-user-file.md"
# Record original files
ORIGINAL_FILES=$(find "$DOCS_DIR" -type f | sort)

# Run again without --force
bash "$INIT_SCRIPT" --project "$PROJECT_NAME" --path "$TARGET_DIR" 2>/dev/null || true

# Check user files preserved
if [[ -f "${DOCS_DIR}/governance/POLICY.md" ]] && [[ "$(cat "${DOCS_DIR}/governance/POLICY.md")" == "# My Custom Policy" ]]; then
  pass "User-modified files preserved on second run"
else
  fail "User-modified files overwritten on second run"
fi
if [[ -f "${DOCS_DIR}/custom-user-file.md" ]] && [[ "$(cat "${DOCS_DIR}/custom-user-file.md")" == "user added content" ]]; then
  pass "User-added files preserved on second run"
else
  fail "User-added files lost on second run"
fi

# ── Test 5: --force flag works ──
echo "TEST 5: --force flag overwrites files"
echo "# Custom Policy" > "${DOCS_DIR}/governance/POLICY.md"
bash "$INIT_SCRIPT" --project "$PROJECT_NAME" --path "$TARGET_DIR" --force
if grep -q "Project Policies" "${DOCS_DIR}/governance/POLICY.md"; then
  pass "--force correctly overwrites files"
else
  fail "--force did not overwrite files"
fi

# ── Test 6: Markdown syntax validation ──
echo "TEST 6: Markdown syntax validation"
MD_PASS=true
while IFS= read -r f; do
  # Check for broken headers (line starts with # but no space after)
  if grep -nE '^[#]{1,6}[^ #]' "$f" 2>/dev/null; then
    fail "Broken markdown header in $f"
    MD_PASS=false
  fi
  # Check file is not empty
  if [[ ! -s "$f" ]]; then
    fail "Empty file: $f"
    MD_PASS=false
  fi
done < <(find "$DOCS_DIR" -name "*.md" -type f)
if $MD_PASS; then
  pass "All Markdown files have valid syntax"
fi

# ── Test 7: Content validation — no private/project-specific content ──
echo "TEST 7: Content is generic (no private project content)"
PRIVATE_PATTERNS=(
  "regimelab\|Regime_Lab"
  "kwant\|Kwant_Back"
  "testuser"
  "\.ssh"
  "api.key\|api_key.*=.*[A-Za-z0-9]"
  "token.*=.*[A-Za-z0-9]"
  "password.*=.*[A-Za-z0-9]"
  "\.env"
  "DigitalOcean\|Hetzner\|AWS"
  "production\.databases"
  "neo4j\+s://"
  "pinecone\.io"
)
PRIVACY_PASS=true
for pattern in "${PRIVATE_PATTERNS[@]}"; do
  if grep -rliE "$pattern" "${DOCS_DIR}/" 2>/dev/null | grep -v ".git" > /dev/null; then
    fail "Private content found: $pattern"
    PRIVACY_PASS=false
  fi
done
if $PRIVACY_PASS; then
  pass "SuperDocs content is generic — no private project content"
fi

# ── Test 8: No .ossbuild under docs/ ──
echo "TEST 8: No nested .ossbuild under docs/"
if [[ -d "${DOCS_DIR}/.ossbuild" ]]; then
  fail "Nested .ossbuild found under docs/"
else
  pass "No nested .ossbuild under docs/"
fi

# ── Test 9: YAML registry files are valid (if any) ──
echo "TEST 9: YAML files valid syntax"
YAML_PASS=true
while IFS= read -r f; do
  if command -v python3 &>/dev/null; then
    if ! python3 -c "import yaml; yaml.safe_load(open('$f'))" 2>/dev/null; then
      fail "Invalid YAML: $f"
      YAML_PASS=false
    fi
  fi
done < <(find "$DOCS_DIR" -name "*.yaml" -o -name "*.yml" 2>/dev/null)
if $YAML_PASS; then
  pass "All YAML files have valid syntax"
fi

# ── Test 10: Empty --project fails gracefully ──
echo "TEST 10: Empty --project fails gracefully"
if bash "$INIT_SCRIPT" --project "" --path "$TEST_WORK/empty-test" 2>/dev/null; then
  fail "Empty --project should fail"
else
  pass "Empty --project correctly rejected"
fi

# ── Test 11: Missing --project fails gracefully ──
echo "TEST 11: Missing --project fails gracefully"
if bash "$INIT_SCRIPT" --path "$TEST_WORK/no-project-test" 2>/dev/null; then
  fail "Missing --project should fail"
else
  pass "Missing --project correctly rejected"
fi

# ── Test 12: Default path (current directory) works ──
echo "TEST 12: Default path (current directory) works"
CWD_TEST="${TEST_WORK}/cwd-test"
mkdir -p "$CWD_TEST"
(cd "$CWD_TEST" && bash "$INIT_SCRIPT" --project "cwd-project")
if [[ -d "${CWD_TEST}/docs/governance" ]]; then
  pass "Default path (current directory) works"
else
  fail "Default path did not create docs/ in current directory"
fi

# ── Summary ──
echo ""
echo "=== init-superdocs.sh Test Results: $PASS/$TOTAL passed, $FAIL failed ==="
if [[ $FAIL -gt 0 ]]; then
  exit 1
fi
exit 0
