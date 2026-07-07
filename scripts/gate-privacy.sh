#!/usr/bin/env bash
# gate-privacy.sh — Scan repository for private/sensitive content
# Exit 0 = pass, exit 1 = fail
set -euo pipefail

# CONFIGURABLE: Set OWNER_USERNAME to your system username or login identifier.
# The gate checks that no file in the repository contains this string.
# Example: export OWNER_USERNAME="jdoe"
OWNER_USERNAME="${OWNER_USERNAME:-}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${REPO_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
STAGING_DIR="${STAGING_DIR:-$REPO_ROOT}"

echo "=== Privacy Gate ==="
echo "  Scanning: $STAGING_DIR"

FAILURES=0

# ── Patterns that indicate private content ──
# Each pattern is "label|regex"
PATTERNS=(
  "RegimeLab project refs|RegimeLab|Regime_Lab|regimelab"
  "Kwant project refs|Kwant_Back|kwant"
  "API key values|api[_-]key\s*=\s*[A-Za-z0-9]"
  "Token values|token\s*=\s*[A-Za-z0-9]{20,}"
  "Password values|password\s*=\s*[A-Za-z0-9]{8,}"
  "Private env files|\.env$|\.env\.local|\.env\.prod"
  "Cloud provider specifics|DigitalOcean|Hetzner|AWS_ACCESS"
  "Internal IPs|192\.168\.|10\.0\.|172\.(1[6-9]|2[0-9]|3[01])\."
  "Production domains|\.databases\.neo4j\.io|\.onrender\.com"
  "Personal file paths|/home/username|/Users/username"
)

# Directories to scan (shipped dirs)
SCAN_DIRS=("bin" "scripts" "examples" "docs" "skills" "memory" "registry")
# Directories to skip
SKIP_DIRS=(".ossbuild" ".local.archived-from-test-run" "__pycache__" "__pycache__-cleanup" "__pycache__.removed" "tests" "node_modules" ".git")
# Binary file extensions to skip
BINARY_EXTS=".pyc .pyo .pyd .so .dylib .dll .o .a .class .jar .exe .bin"

for label_pattern in "${PATTERNS[@]}"; do
  LABEL="${label_pattern%%|*}"
  PATTERN="${label_pattern#*|}"
  
  for dir in "${SCAN_DIRS[@]}"; do
    TARGET="${STAGING_DIR}/${dir}"
    if [[ -d "$TARGET" ]]; then
      # Find text files only, exclude skip dirs and binary files
      while IFS= read -r f; do
        # Skip by extension
        FNAME=$(basename "$f")
        case "$FNAME" in
          *.pyc|*.pyo|*.pyd|*.so|*.dylib|*.dll|*.o|*.a|*.class|*.jar|*.exe|*.bin)
            continue
            ;;
        esac
        
        # Skip if file command says binary
        if file -b "$f" 2>/dev/null | grep -q "binary\|executable"; then
          continue
        fi
        
        # Skip __pycache__ directories entirely
        case "$f" in
          */__pycache__/*|*__pycache__)
            continue
            ;;
        esac
        
        if grep -qiE "$PATTERN" "$f" 2>/dev/null; then
          # Get context (first match only, truncated)
          MATCH=$(grep -iE "$PATTERN" "$f" 2>/dev/null | head -1 | cut -c1-80)
          echo "  FAIL [$LABEL]: $f"
          echo "    Match: $MATCH"
          FAILURES=$((FAILURES+1))
        fi
      done < <(find "$TARGET" -type f -not -path "*/.git/*" 2>/dev/null)
    fi
  done
done

# ── Binary-aware owner string scan ──
echo ""
echo "Checking for owner strings in non-text files..."
BINARY_FAILS=0
while IFS= read -r f; do
  # Skip known text extensions
  case "$f" in *.md|*.txt|*.yaml|*.sh|*.py|*.sql|*.json|*.template|*.toml|*.log|*.cfg|*.ini|*.csv|*.html|*.css|*.js) continue ;; esac
  # Skip .ossbuild and tests
  case "$f" in */.ossbuild/*|*/tests/*) continue ;; esac
  if [ -n "${OWNER_USERNAME:-}" ] && grep -qP "$OWNER_USERNAME" "$f" 2>/dev/null; then
    echo "  FAIL [Binary owner strings]: $f contains owner string"
    BINARY_FAILS=$((BINARY_FAILS+1))
  fi
done < <(find "$STAGING_DIR" -type f ! -path "*/.ossbuild/*" ! -path "*/tests/*" ! -name "*.md" ! -name "*.txt" ! -name "*.yaml" ! -name "*.sh" ! -name "*.py" ! -name "*.sql" ! -name "*.json" ! -name "*.template" ! -name "*.log" ! -name "*.toml" ! -name "*.cfg" ! -name "*.ini" ! -name "*.csv" ! -name "*.html" ! -name "*.css" ! -name "*.js" 2>/dev/null)
FAILURES=$((FAILURES + BINARY_FAILS))

# ── Check for .env files with real values (not templates) ──
echo ""
echo "Checking for .env files with real secrets..."
while IFS= read -r f; do
  if [[ "$f" == *.template ]]; then
    continue  # Templates are OK
  fi
  if grep -qE "(api[_-]key|token|password|secret)\s*=\s*['\"]?[A-Za-z0-9]" "$f" 2>/dev/null; then
    echo "  FAIL: Potential secrets in $f"
    FAILURES=$((FAILURES+1))
  fi
done < <(find "$STAGING_DIR" -maxdepth 3 -name "*.env" -o -name ".env.*" 2>/dev/null | grep -v ".template" | grep -v ".ossbuild")

echo ""
if [[ $FAILURES -gt 0 ]]; then
  echo "RESULT: FAIL — $FAILURES privacy violations found"
  exit 1
else
  echo "RESULT: PASS — no private/sensitive content detected"
  exit 0
fi
