#!/usr/bin/env bash
# gate-no-nested-ossbuild.sh — Verify no .ossbuild directories exist under shipped dirs
# Exit 0 = pass, exit 1 = fail (nested .ossbuild found)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STAGING_DIR="${STAGING_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)}"

# Directories that should never contain .ossbuild
SHIPPED_DIRS=("bin" "scripts" "examples" "docs" "skills" "memory" "registry")

echo "=== No-Nested-Ossbuild Gate ==="
echo "  Scanning: $STAGING_DIR"

FAILURES=0

for dir in "${SHIPPED_DIRS[@]}"; do
  TARGET="${STAGING_DIR}/${dir}"
  if [[ -d "$TARGET" ]]; then
    FOUND=$(find "$TARGET" -name ".ossbuild" -type d 2>/dev/null || true)
    if [[ -n "$FOUND" ]]; then
      echo "  FAIL: Nested .ossbuild found under $dir:"
      echo "$FOUND" | while read -r p; do echo "    $p"; done
      FAILURES=$((FAILURES + 1))
    else
      echo "  PASS: $dir — no nested .ossbuild"
    fi
  else
    echo "  SKIP: $dir — not present"
  fi
done

# Also check top-level (only the one top-level .ossbuild is allowed)
TOP_LEVEL=$(find "$STAGING_DIR" -maxdepth 1 -name ".ossbuild" -type d 2>/dev/null || true)
if [[ -n "$TOP_LEVEL" ]]; then
  echo "  INFO: Top-level .ossbuild present (expected for evidence archive)"
fi

echo ""
if [[ $FAILURES -gt 0 ]]; then
  echo "RESULT: FAIL — $FAILURES nested .ossbuild directories found"
  exit 1
else
  echo "RESULT: PASS — no nested .ossbuild under shipped dirs"
  exit 0
fi
