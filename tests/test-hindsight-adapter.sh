#!/usr/bin/env bash
set -euo pipefail

# test-hindsight-adapter.sh — Verify Hindsight adapter files are complete and correct
# This test validates that the optional Hindsight adapter ships correctly
# without requiring the hindsight-client package or a running Hindsight API.

REPO_ROOT="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
REPO_ROOT="$(cd "$REPO_ROOT" && pwd)"

echo "=== Hindsight Adapter Test ==="
echo "Repo root: $REPO_ROOT"
echo ""

PASS_COUNT=0
FAIL_COUNT=0

check() {
  local desc="$1"
  shift
  if "$@" >/dev/null 2>&1; then
    echo "  PASS: $desc"
    PASS_COUNT=$((PASS_COUNT + 1))
  else
    echo "  FAIL: $desc"
    FAIL_COUNT=$((FAIL_COUNT + 1))
  fi
}

echo "--- File Presence ---"
check "memory/hindsight_bridge.py exists" test -f "$REPO_ROOT/memory/hindsight_bridge.py"
check "memory/hindsight_gc.py exists" test -f "$REPO_ROOT/memory/hindsight_gc.py"
check "scripts/hindsight-health-check.py exists" test -f "$REPO_ROOT/scripts/hindsight-health-check.py"
check "bin/hindsight-bridge exists" test -f "$REPO_ROOT/bin/hindsight-bridge"
check "bin/hindsight-gc exists" test -f "$REPO_ROOT/bin/hindsight-gc"
check "bin/hindsight-health exists" test -f "$REPO_ROOT/bin/hindsight-health"
check "memory/adapters/hindsight/ADAPTER.md exists" test -f "$REPO_ROOT/memory/adapters/hindsight/ADAPTER.md"

echo ""
echo "--- Executable Permissions ---"
check "bin/hindsight-bridge is executable" test -x "$REPO_ROOT/bin/hindsight-bridge"
check "bin/hindsight-gc is executable" test -x "$REPO_ROOT/bin/hindsight-gc"
check "bin/hindsight-health is executable" test -x "$REPO_ROOT/bin/hindsight-health"

echo ""
echo "--- Python Syntax ---"
check "hindsight_bridge.py syntax" python3 -m py_compile "$REPO_ROOT/memory/hindsight_bridge.py"
check "hindsight_gc.py syntax" python3 -m py_compile "$REPO_ROOT/memory/hindsight_gc.py"
check "hindsight-health-check.py syntax" python3 -m py_compile "$REPO_ROOT/scripts/hindsight-health-check.py"

echo ""
echo "--- Shell Syntax ---"
check "bin/hindsight-bridge syntax" bash -n "$REPO_ROOT/bin/hindsight-bridge"
check "bin/hindsight-gc syntax" bash -n "$REPO_ROOT/bin/hindsight-gc"
check "bin/hindsight-health syntax" bash -n "$REPO_ROOT/bin/hindsight-health"

echo ""
echo "--- No /tmp Writes ---"
check "hindsight_bridge.py uses STATE_DIR not /tmp" bash -c "! grep -q '/tmp/' \"$REPO_ROOT/memory/hindsight_bridge.py\""
check "hindsight_gc.py uses LOG_DIR not /tmp" bash -c "! grep -q '/tmp/' \"$REPO_ROOT/memory/hindsight_gc.py\""

echo ""
echo "--- Registry References ---"
check "registry/tools.yaml lists hindsight-bridge" grep -q "hindsight-bridge" "$REPO_ROOT/registry/tools.yaml"
check "registry/tools.yaml lists hindsight-gc" grep -q "hindsight-gc" "$REPO_ROOT/registry/tools.yaml"
check "registry/tools.yaml lists hindsight-health" grep -q "hindsight-health" "$REPO_ROOT/registry/tools.yaml"

echo ""
echo "--- Manifest References ---"
check "EXPORT_MANIFEST.yaml lists hindsight-bridge" grep -q "hindsight-bridge" "$REPO_ROOT/EXPORT_MANIFEST.yaml"
check "EXPORT_MANIFEST.yaml lists hindsight-gc" grep -q "hindsight-gc" "$REPO_ROOT/EXPORT_MANIFEST.yaml"
check "EXPORT_MANIFEST.yaml lists hindsight-health" grep -q "hindsight-health" "$REPO_ROOT/EXPORT_MANIFEST.yaml"
check "EXPORT_MANIFEST.yaml lists hindsight_bridge.py" grep -q "hindsight_bridge.py" "$REPO_ROOT/EXPORT_MANIFEST.yaml"
check "EXPORT_MANIFEST.yaml lists hindsight_gc.py" grep -q "hindsight_gc.py" "$REPO_ROOT/EXPORT_MANIFEST.yaml"
check "EXPORT_MANIFEST.yaml lists hindsight-health-check.py" grep -q "hindsight-health-check.py" "$REPO_ROOT/EXPORT_MANIFEST.yaml"
check "EXPORT_MANIFEST.yaml lists adapters/hindsight/ADAPTER.md" grep -q "adapters/hindsight/ADAPTER.md" "$REPO_ROOT/EXPORT_MANIFEST.yaml"

echo ""
echo "--- Documentation ---"
check "README.md mentions Hindsight" grep -q "Hindsight" "$REPO_ROOT/README.md"
check "SETUP.md documents Hindsight setup" grep -q "Hindsight" "$REPO_ROOT/SETUP.md"
check "memory/README.md documents Hindsight" grep -q "Hindsight" "$REPO_ROOT/memory/README.md"
check "ADAPTER.md documents environment variables" grep -q "HINDSIGHT_BANK" "$REPO_ROOT/memory/adapters/hindsight/ADAPTER.md"
check "ADAPTER.md documents usage" grep -q "hindsight-bridge" "$REPO_ROOT/memory/adapters/hindsight/ADAPTER.md"

echo ""
echo "--- Optional Dependency ---"
check "requirements.txt does NOT require hindsight-client" bash -c "! grep -Eq '^hindsight-client([<=>]|$)' \"$REPO_ROOT/requirements.txt\""
check "requirements.txt mentions hindsight-client as optional comment" grep -q "#.*hindsight-client" "$REPO_ROOT/requirements.txt"

echo ""
echo "--- Results ---"
echo "  Passed: $PASS_COUNT"
echo "  Failed: $FAIL_COUNT"

if [ "$FAIL_COUNT" -eq 0 ]; then
  echo ""
  echo "=== HINDSIGHT ADAPTER TEST PASS ==="
  exit 0
else
  echo ""
  echo "=== HINDSIGHT ADAPTER TEST FAIL ==="
  exit 1
fi
