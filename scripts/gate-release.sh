#!/usr/bin/env bash
# gate-release.sh — Authoritative release gate for Agent OS
# Consolidates all validation into one script. Exit 0 = all pass, exit 1 = fail.
#
# Checks performed (in order):
#   1. Privacy gate (23 checks)
#   2. Syntax and registry validation
#   3. Negative fixture tests
#   4. Clean-room installation (86 checks)
#   5. Vault init tests (9 checks)
#   6. SuperDocs init tests (27 checks)
#   7. No nested .ossbuild under shipped dirs
#   8. Permission and dangling-command checks
#   9. No .git directory
set -euo pipefail

# CONFIGURABLE: Set OWNER_USERNAME to your system username or login identifier.
# The gate checks that no file in the repository contains this string.
# Example: export OWNER_USERNAME="jdoe"
OWNER_USERNAME="${OWNER_USERNAME:-}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${REPO_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"

STAGING_DIR="$REPO_ROOT"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║       Agent OS — Authoritative Release Gate                 ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "Repository root: $STAGING_DIR"
echo "Timestamp: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo ""

TOTAL_PASS=0
TOTAL_FAIL=0
FAIL_DETAILS=""

run_gate() {
  local name="$1"
  local script="$2"
  shift 2
  local label="$name"
  
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "  GATE: $label"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  
  if bash "$script" "$STAGING_DIR" "$@" 2>&1; then
    TOTAL_PASS=$((TOTAL_PASS+1))
    echo "  ✅ $label: PASS"
    echo ""
  else
    TOTAL_FAIL=$((TOTAL_FAIL+1))
    FAIL_DETAILS="${FAIL_DETAILS}\n  ❌ $label: FAIL"
    echo "  ❌ $label: FAIL"
    echo ""
  fi
}

run_check() {
  local name="$1"
  shift
  
  if "$@" >/dev/null 2>&1; then
    TOTAL_PASS=$((TOTAL_PASS+1))
    echo "  ✅ $name: PASS"
  else
    TOTAL_FAIL=$((TOTAL_FAIL+1))
    FAIL_DETAILS="${FAIL_DETAILS}\n  ❌ $name: FAIL"
    echo "  ❌ $name: FAIL"
  fi
}

# ═══════════════════════════════════════════════════════════════
# Gate 1: Privacy (23 checks)
# ═══════════════════════════════════════════════════════════════
run_gate "Privacy Gate (23 checks)" "${STAGING_DIR}/tests/privacy/privacy_gate.sh"

# ═══════════════════════════════════════════════════════════════
# Gate 2: Syntax and Registry Validation
# ═══════════════════════════════════════════════════════════════
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  GATE: Syntax and Registry Validation"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Required files
run_check "Required files present" bash -c 'for f in AGENTS.md BOOT.md README.md SETUP.md LICENSE install.sh config.env.template requirements.txt PRIVACY_BOUNDARY.md; do test -f "'"$STAGING_DIR"'/$f" || { echo "Missing: $f"; exit 1; }; done'

# Required directories
run_check "Required directories present" bash -c 'for d in bin scripts memory registry skills tests docs examples; do test -d "'"$STAGING_DIR"'/$d" || { echo "Missing: $d/"; exit 1; }; done'

# YAML validity
run_check "YAML files parse" python3 -c "
import pathlib, sys, yaml
root = pathlib.Path('$STAGING_DIR')
bad = []
for path in root.rglob('*.yaml'):
    if '.ossbuild' in path.parts or 'tests' in path.parts:
        continue
    try:
        yaml.safe_load(path.read_text())
    except Exception as exc:
        bad.append(f'{path.relative_to(root)}: {exc}')
if bad:
    print(chr(10).join(bad))
    sys.exit(1)
"

# Python syntax (ast.parse — creates no bytecode)
run_check "Python syntax valid (ast.parse)" python3 -c "
import ast, pathlib, sys
root = pathlib.Path('$STAGING_DIR')
bad = []
for path in root.rglob('*.py'):
    if '.ossbuild' in path.parts or 'tests' in path.parts or '__pycache__' in path.parts:
        continue
    try:
        ast.parse(path.read_text(), filename=str(path))
    except SyntaxError as exc:
        bad.append(f'{path.relative_to(root)}: {exc}')
if bad:
    print(chr(10).join(bad))
    sys.exit(1)
"

# Shell syntax
run_check "Shell syntax valid" bash -c 'STAGE="'"$STAGING_DIR"'"; for f in $(find "$STAGE" -name "*.sh" -not -path "*/.ossbuild/*" -not -path "*/tests/*" 2>/dev/null); do bash -n "$f" || { echo "Syntax error: $f"; exit 1; }; done'

# Registry skill paths resolve
run_check "Skill registry paths resolve" python3 -c "
import pathlib, sys, yaml
root = pathlib.Path('$STAGING_DIR')
data = yaml.safe_load((root / 'registry/skills.yaml').read_text()) or {}
missing = []
for entry in data.get('skills', []):
    path = str(entry.get('path', ''))
    prefix = '\$AGENT_OS_HOME/'
    if path.startswith(prefix):
        candidate = root / path[len(prefix):]
        if not candidate.exists():
            missing.append(str(candidate.relative_to(root)))
if missing:
    print('Missing skill paths:')
    print(chr(10).join(missing))
    sys.exit(1)
"

# Registry tool paths resolve
run_check "Tool registry paths resolve" python3 -c "
import pathlib, sys, yaml
root = pathlib.Path('$STAGING_DIR')
data = yaml.safe_load((root / 'registry/tools.yaml').read_text()) or {}
missing = []
for entry in data.get('tools', []):
    path = str(entry.get('binary', ''))
    prefix = '\$AGENT_OS_HOME/'
    if path.startswith(prefix):
        candidate = root / path[len(prefix):]
        if not candidate.exists():
            missing.append(str(candidate.relative_to(root)))
if missing:
    print('Missing tool paths:')
    print(chr(10).join(missing))
    sys.exit(1)
"

# INDEX.md no dangling paths
run_check "INDEX.md paths resolve" python3 -c "
import pathlib, re, sys
root = pathlib.Path('$STAGING_DIR')
text = (root / 'INDEX.md').read_text()
paths = sorted(set(re.findall(r'\\\$AGENT_OS_HOME/([A-Za-z0-9_./-]+)', text)))
missing = []
for path in paths:
    cleaned = path.rstrip('.,)\`')
    if not (root / cleaned).exists():
        missing.append(cleaned)
if missing:
    print('Dangling INDEX paths:')
    print(chr(10).join(missing))
    sys.exit(1)
"

echo "  Syntax and registry: done"
echo ""

# ═══════════════════════════════════════════════════════════════
# Gate 2b: Binary-Aware Owner Scan
# ═══════════════════════════════════════════════════════════════
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  GATE: Binary-Aware Owner Scan"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

run_check "Binary-aware owner scan" bash -c '
  if [ -z "${OWNER_USERNAME:-}" ]; then
    echo "  SKIP: \$OWNER_USERNAME not set -- configure with export OWNER_USERNAME=\"your_username\"" >&2
    exit 0
  fi
  FOUND=0
  while IFS= read -r f; do
    case "$f" in */.ossbuild/*|*/tests/*|*/droid-wiki/*|*/PRIVACY_BOUNDARY.md) continue ;; esac
    if grep -qP "$OWNER_USERNAME" "$f" 2>/dev/null; then
      echo "  FAIL: Owner string found in binary/non-text file: $f"
      FOUND=1
    fi
  done < <(find "'"$STAGING_DIR'"'" -type f ! -path "*/.ossbuild/*" ! -path "*/tests/*" ! -name "*.md" ! -name "*.txt" ! -name "*.yaml" ! -name "*.sh" ! -name "*.py" ! -name "*.sql" ! -name "*.json" ! -name "*.template" ! -name "*.log" ! -name "*.toml" ! -name "*.cfg" ! -name "*.ini" ! -name "*.csv" ! -name "*.html" ! -name "*.css" ! -name "*.js" 2>/dev/null)
  if [[ $FOUND -eq 1 ]]; then exit 1; fi
  echo "  PASS: No owner strings in binary files"
'
echo ""

# ═══════════════════════════════════════════════════════════════
# Gate 3: Negative Fixture Tests
# ═══════════════════════════════════════════════════════════════
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  GATE: Negative Fixture Tests"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

run_check "Owner path fixture detected" bash -c '
  TMPDIR=$(mktemp -d)
  trap '"'"'rm -rf "$TMPDIR"'"'"' EXIT
  mkdir -p "$TMPDIR/test-project"
  echo "root: /home/user/projects" > "$TMPDIR/test-project/test.yaml"
  if bash "'"$STAGING_DIR"'/tests/privacy/privacy_gate.sh" "$TMPDIR/test-project" 2>/dev/null; then
    echo "ERROR: Owner path fixture was NOT detected"
    exit 1
  fi
'

run_check "Secret fixture detected" bash -c '
  TMPDIR=$(mktemp -d)
  trap '"'"'rm -rf "$TMPDIR"'"'"' EXIT
  mkdir -p "$TMPDIR/test-project"
  echo "api_key: ***********************************" > "$TMPDIR/test-project/test.yaml"
  if bash "'"$STAGING_DIR"'/tests/privacy/privacy_gate.sh" "$TMPDIR/test-project" 2>/dev/null; then
    echo "ERROR: Secret fixture was NOT detected"
    exit 1
  fi
'
run_check "Scanner error reports FAIL_SCAN not FAIL" bash -c '
  STAGING_DIR="'"$STAGING_DIR"'"
  TMPDIR=$(mktemp -d)
  trap '"'"'rm -rf "$TMPDIR"'"'"' EXIT
  mkdir -p "$TMPDIR/test-project"
  echo "sample content" > "$TMPDIR/test-project/test.yaml"
  # Stub rg that exits 2 (error) with no output to simulate scanner failure
  STUBDIR="$TMPDIR/stub"
  mkdir -p "$STUBDIR"
  cat > "$STUBDIR/rg" << '"'"'STUB'"'"'
#!/bin/bash
exit 2
STUB
  chmod +x "$STUBDIR/rg"
  output=$(PATH="$STUBDIR:$PATH" "$STAGING_DIR/tests/privacy/privacy_gate.sh" "$TMPDIR/test-project" 2>&1 || true)
  if echo "$output" | grep -q "FAIL_SCAN"; then
    echo "  PASS: Scanner error correctly reported as FAIL_SCAN"
  else
    echo "ERROR: Scanner error was not reported as FAIL_SCAN"
    echo "$output" | tail -5
    exit 1
  fi
'

echo "  Negative fixtures: done"
echo ""

# ═══════════════════════════════════════════════════════════════
# Gate 4: Clean-Room Installation (86 checks)
# ═══════════════════════════════════════════════════════════════
run_gate "Clean-Room Installation (86 checks)" "${STAGING_DIR}/tests/clean-room/install_and_verify.sh"

# ═══════════════════════════════════════════════════════════════
# Gate 5: Vault Init Tests (9 checks)
# ═══════════════════════════════════════════════════════════════
run_gate "Vault Init Tests (9 checks)" "${STAGING_DIR}/tests/test-init-vault.sh"

# ═══════════════════════════════════════════════════════════════
# Gate 6: SuperDocs Init Tests (27 checks)
# ═══════════════════════════════════════════════════════════════
run_gate "SuperDocs Init Tests (27 checks)" "${STAGING_DIR}/tests/test-init-superdocs.sh"

# ═══════════════════════════════════════════════════════════════
# Gate 7: No Nested .ossbuild
# ═══════════════════════════════════════════════════════════════
run_gate "No Nested .ossbuild" "${STAGING_DIR}/scripts/gate-no-nested-ossbuild.sh"

# ═══════════════════════════════════════════════════════════════
# Gate 8: Permission and Dangling-Command Checks
# ═══════════════════════════════════════════════════════════════
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  GATE: Permission and Dangling-Command Checks"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

PERM_FAILURES=0

# Check .sh files are executable (755)
while IFS= read -r f; do
  PERMS=$(stat -c %a "$f" 2>/dev/null)
  if [[ "$PERMS" != "755" ]]; then
    echo "  FAIL: $f has perms $PERMS (expected 755)"
    PERM_FAILURES=$((PERM_FAILURES+1))
  fi
done < <(find "$STAGING_DIR" -name "*.sh" -type f ! -path "*/.ossbuild/*" 2>/dev/null)

# Check bin/ files are executable (755)
while IFS= read -r f; do
  PERMS=$(stat -c %a "$f" 2>/dev/null)
  if [[ "$PERMS" != "755" ]]; then
    echo "  FAIL: $f has perms $PERMS (expected 755)"
    PERM_FAILURES=$((PERM_FAILURES+1))
  fi
done < <(find "$STAGING_DIR/bin" -type f 2>/dev/null)

# Check non-entrypoint .py files are 644
while IFS= read -r f; do
  PERMS=$(stat -c %a "$f" 2>/dev/null)
  # Entry points (called from bin/ or directly executable) should be 755
  case "$f" in
    */memory-recall-safe.py|*/skill_health.py|*/registry-check.py|*/skill-pack|*/skill-rank)
      if [[ "$PERMS" != "755" ]]; then
        echo "  FAIL: $f has perms $PERMS (expected 755 for entrypoint)"
        PERM_FAILURES=$((PERM_FAILURES+1))
      fi
      ;;
    *)
      if [[ "$PERMS" != "644" ]]; then
        echo "  FAIL: $f has perms $PERMS (expected 644 for library)"
        PERM_FAILURES=$((PERM_FAILURES+1))
      fi
      ;;
  esac
done < <(find "$STAGING_DIR/scripts" "$STAGING_DIR/memory" -name "*.py" -type f ! -path "*/.ossbuild/*" ! -path "*/__pycache__/*" 2>/dev/null)

# Check for dangling commands (references to non-existent scripts in docs)
DANGLING_FAILURES=0
echo ""
echo "Checking for dangling command references in docs..."
while IFS= read -r f; do
  # Skip binary files
  if file -b "$f" 2>/dev/null | grep -q "binary"; then continue; fi
  # Check for references to missing scripts
  while IFS= read -r ref; do
    SCRIPT_PATH=$(echo "$ref" | sed -n 's/.*scripts\/\([^ "`)]*\).*/\1/p' | head -1)
    if [[ -n "$SCRIPT_PATH" ]]; then
      CANDIDATE="$STAGING_DIR/scripts/$SCRIPT_PATH"
      case "$f" in
        "$STAGING_DIR"/droid-wiki/*)
          WIKI_CANDIDATE="$STAGING_DIR/droid-wiki/scripts/$SCRIPT_PATH"
          if [[ -f "$WIKI_CANDIDATE" ]]; then
            CANDIDATE="$WIKI_CANDIDATE"
          fi
          ;;
      esac
      if [[ ! -f "$CANDIDATE" ]]; then
        echo "  FAIL: Dangling ref to scripts/$SCRIPT_PATH in $f"
        DANGLING_FAILURES=$((DANGLING_FAILURES+1))
      fi
    fi
  done < <(grep -n "scripts/" "$f" 2>/dev/null || true)
done < <(find "$STAGING_DIR" -name "*.md" -type f ! -path "*/.ossbuild/*" ! -path "*/tests/*" 2>/dev/null)

# Manifest truth is validated by tests/manifest-truth-gate.sh (called separately)
MANIFEST_ALLOWLIST_FAILURES=0

# Cross-check: .ossbuild directory must not be referenced as shipping content
echo "Checking .ossbuild is not referenced as shipping content..."
OSSBUILD_REF_FAILURES=0
while IFS= read -r f; do
  if file -b "$f" 2>/dev/null | grep -q "binary"; then continue; fi
  # Look for .ossbuild references outside of itself
  case "$f" in
    */.ossbuild/*) continue ;;
  esac
  # Allow .ossbuild as a known non-shipping directory in docs
  if grep -q '"\.ossbuild/"' "$f" 2>/dev/null; then
    echo "  FAIL: $f references .ossbuild/ as if it ships"
    OSSBUILD_REF_FAILURES=$((OSSBUILD_REF_FAILURES+1))
  fi
done < <(find "$STAGING_DIR" -type f \( -name "*.md" -o -name "*.yaml" \) ! -path "*/.ossbuild/*" ! -path "*/tests/*" 2>/dev/null)

# Cross-check: INDEX.md paths resolve against actual files
echo "Cross-checking INDEX.md paths..."
INDEX_FAILURES=0
python3 -c "
import pathlib, re, sys
root = pathlib.Path('$STAGING_DIR')
text = (root / 'INDEX.md').read_text()
paths = sorted(set(re.findall(r'\\\$AGENT_OS_HOME/([A-Za-z0-9_./-]+)', text)))
missing = []
for path in paths:
    cleaned = path.rstrip('.,)\x60')
    if not (root / cleaned).exists():
        missing.append(cleaned)
if missing:
    for m in missing:
        print(f'  FAIL: INDEX.md path {m} does not exist')
    sys.exit(1)
" && INDEX_FAILURES=0 || INDEX_FAILURES=1

TOTAL_DANGLING=$((DANGLING_FAILURES + MANIFEST_ALLOWLIST_FAILURES + OSSBUILD_REF_FAILURES + INDEX_FAILURES))
if [[ $PERM_FAILURES -eq 0 ]] && [[ $TOTAL_DANGLING -eq 0 ]]; then
  TOTAL_PASS=$((TOTAL_PASS+1))
  echo "  ✅ Permission and dangling-command: PASS"
else
  TOTAL_FAIL=$((TOTAL_FAIL+1))
  FAIL_DETAILS="${FAIL_DETAILS}\n  ❌ Permission/dangling: FAIL ($PERM_FAILURES perm + $TOTAL_DANGLING inventory)"
  echo "  ❌ Permission and dangling-command: FAIL"
fi
echo ""

# ═══════════════════════════════════════════════════════════════
# Gate 8b: Manifest Truth (allowlist vs shipped files)
# ═══════════════════════════════════════════════════════════════
run_gate "Manifest Truth" "${STAGING_DIR}/tests/manifest-truth-gate.sh"

# ═══════════════════════════════════════════════════════════════
# Gate 9: No .git Directory
# ═══════════════════════════════════════════════════════════════
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  GATE: No .git Directory"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

run_check "No .git directory in staging" bash -c "cd '$STAGING_DIR' && ! find '.' -mindepth 2 -name '.git' -type d | grep ."

# ═══════════════════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════════════════
echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║                     RELEASE GATE SUMMARY                    ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "  Gates passed: $TOTAL_PASS"
echo "  Gates failed: $TOTAL_FAIL"
echo ""

# Write artifact
GATE_DIR="$STAGING_DIR/.ossbuild/release-gate"
mkdir -p "$GATE_DIR"
cat > "$GATE_DIR/summary.txt" << EOF
release_gate_pass=$TOTAL_PASS
release_gate_fail=$TOTAL_FAIL
timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)
staging_dir=$STAGING_DIR
EOF

if [[ $TOTAL_FAIL -gt 0 ]]; then
  echo "RESULT: FAIL — $TOTAL_FAIL gate(s) failed"
  echo ""
  echo "Failure details:$FAIL_DETAILS"
  echo ""
  echo "Fix the issues above before release."
  exit 1
else
  echo "RESULT: PASS — all gates passed"
  echo ""
  echo "Staging area is ready for public release."
  exit 0
fi
