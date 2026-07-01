#!/usr/bin/env bash
# gate-cleanroom.sh — Verify staging area has no build artifacts, caches, or temp files
# Exit 0 = pass, exit 1 = fail
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STAGING_DIR="${STAGING_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)}"

echo "=== Clean-Room Gate ==="
echo "  Scanning: $STAGING_DIR"

FAILURES=0

# ── Forbidden patterns (build artifacts, caches, temp files) ──
FORBIDDEN_DIRS=(
  "__pycache__"
  ".pytest_cache"
  "node_modules"
  ".tox"
  "*.egg-info"
  "dist"
  "build"
  ".mypy_cache"
  ".coverage"
  "htmlcov"
  ".local.archived-from-test-run"
)

FORBIDDEN_FILES=(
  "*.pyc"
  "*.pyo"
  "*.pyd"
  "*.so"
  "*.dylib"
  "*.dll"
  "*.o"
  "*.a"
  "*.class"
  "*.jar"
  "*.war"
  "*.ear"
  "*.log"
  "*.tmp"
  "*.temp"
  "*.swp"
  "*.swo"
  "*~"
  ".DS_Store"
  "Thumbs.db"
)

echo ""
echo "Checking for forbidden directories..."
for pattern in "${FORBIDDEN_DIRS[@]}"; do
  while IFS= read -r d; do
    if [[ -n "$d" ]]; then
      # Skip .ossbuild (evidence archive)
      if [[ "$d" == *".ossbuild/"* ]] || [[ "$d" == *".ossbuild" ]]; then
        continue
      fi
      # Allow __pycache__ in scripts/ only
      if [[ "$d" == *"scripts/__pycache__"* ]]; then
        echo "  WARN: $d (allowed in scripts/)"
      else
        echo "  FAIL: Forbidden directory: $d"
        FAILURES=$((FAILURES+1))
      fi
    fi
  done < <(find "$STAGING_DIR" -name "$pattern" -type d 2>/dev/null)
done

echo ""
echo "Checking for forbidden files..."
for pattern in "${FORBIDDEN_FILES[@]}"; do
  while IFS= read -r f; do
    if [[ -n "$f" ]]; then
      # Skip .ossbuild evidence archive
      if [[ "$f" == *".ossbuild/"* ]]; then
        continue
      fi
      echo "  FAIL: Forbidden file: $f"
      FAILURES=$((FAILURES+1))
    fi
  done < <(find "$STAGING_DIR" -name "$pattern" -type f 2>/dev/null | grep -v ".ossbuild")
done

# ── Check for .git directories (should not exist in shipped dirs) ──
echo ""
echo "Checking for .git directories in shipped dirs..."
while IFS= read -r d; do
  if [[ -n "$d" ]]; then
    # Skip .ossbuild evidence archive
    if [[ "$d" == *".ossbuild/"* ]]; then
      continue
    fi
    echo "  FAIL: .git directory in shipped location: $d"
    FAILURES=$((FAILURES+1))
  fi
done < <(find "$STAGING_DIR" -name ".git" -type d 2>/dev/null | grep -v ".ossbuild")

# ── Check for files with excessive permissions ──
echo ""
echo "Checking for files with excessive permissions..."
while IFS= read -r f; do
  if [[ -f "$f" ]]; then
    PERMS=$(stat -c %a "$f" 2>/dev/null || stat -f %Lp "$f" 2>/dev/null)
    # Scripts should be 755 or 775, others should be 644 or 664
    if [[ "$f" == *".sh" ]] || [[ "$f" == *"scripts/"* ]] || [[ "$f" == *"bin/"* ]]; then
      if [[ "$PERMS" != "755" ]] && [[ "$PERMS" != "775" ]]; then
        echo "  WARN: Script $f has perms $PERMS (expected 755/775)"
      fi
    fi
  fi
done < <(find "$STAGING_DIR" -type f \( -name "*.sh" -o -path "*/scripts/*" -o -path "*/bin/*" \) 2>/dev/null | grep -v ".ossbuild")

echo ""
if [[ $FAILURES -gt 0 ]]; then
  echo "RESULT: FAIL — $FAILURES clean-room violations found"
  exit 1
else
  echo "RESULT: PASS — staging area is clean"
  exit 0
fi
