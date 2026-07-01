#!/usr/bin/env bash
# Agent OS Health Check
# Exits 0 if all checks pass, non-zero if anything is degraded.
set -euo pipefail

_realpath() {
  local f="$1"
  if command -v realpath >/dev/null 2>&1; then
    realpath "$f"
  else
    echo "$(cd "$(dirname "$f")" && pwd)/$(basename "$f")"
  fi
}
SCRIPT_DIR="$(dirname "$(_realpath "${BASH_SOURCE[0]}")")"
AGENT_OS_HOME="${AGENT_OS_HOME:-$(cd "$SCRIPT_DIR/.." && pwd)}"

STATUS=0
pass() { echo "  ✓ $*"; }
fail() { echo "  ✗ $*" >&2; STATUS=1; }
warn() { echo "  ⚠  $*"; }
info() { echo "  •  $*"; }

echo "── Agent OS Health Check ──"
echo ""

# ── 1. File structure ──
echo "▸ Structure"
for f in AGENTS.md BOOT.md README.md SETUP.md LICENSE PRIVACY_BOUNDARY.md; do
  if [[ -f "$AGENT_OS_HOME/$f" ]]; then
    pass "$f"
  else
    fail "missing: $f"
  fi
done

for d in registry skills memory scripts bin tests docs examples; do
  if [[ -d "$AGENT_OS_HOME/$d" ]]; then
    pass "$d/"
  else
    fail "missing: $d/"
  fi
done

# ── 2. Registries ──
echo ""
echo "▸ Registries"
for reg in skills.yaml tools.yaml workflows.yaml agents.yaml memory_tiers.yaml mcp_servers.yaml; do
  if [[ -f "$AGENT_OS_HOME/registry/$reg" ]]; then
    if python3 -c "import yaml; yaml.safe_load(open('$AGENT_OS_HOME/registry/$reg'))" 2>/dev/null; then
      pass "registry/$reg (valid YAML)"
    else
      fail "registry/$reg (invalid YAML)"
    fi
  else
    fail "missing: registry/$reg"
  fi
done

# ── 3. Skills ──
echo ""
echo "▸ Skills"
for skill in acp recall lesson digest doc-audit skill-optimizer upward-handoff changes-review; do
  if [[ -f "$AGENT_OS_HOME/skills/shared/$skill/SKILL.md" ]]; then
    pass "$skill"
  else
    fail "missing: skills/shared/$skill/SKILL.md"
  fi
done

# ── 4. Memory ──
echo ""
echo "▸ Memory"
if [[ -f "$AGENT_OS_HOME/memory/README.md" ]]; then
  pass "memory/README.md"
else
  fail "missing: memory/README.md"
fi
for f in short_term.py recall_hook.py promote.py inject.py; do
  if [[ -f "$AGENT_OS_HOME/memory/core/$f" ]]; then
    pass "memory/core/$f"
  else
    fail "missing: memory/core/$f"
  fi
done
for adapter in pinecone neo4j; do
  if [[ -f "$AGENT_OS_HOME/memory/adapters/$adapter/ADAPTER.md" ]]; then
    pass "adapter: $adapter"
  else
    fail "missing: memory/adapters/$adapter/ADAPTER.md"
  fi
done

# ── 5. Scripts ──
echo ""
echo "▸ Scripts"
for script in agent-os-health.sh agent-os-verify.sh registry-check.py; do
  if [[ -f "$AGENT_OS_HOME/scripts/$script" ]]; then
    pass "$script"
  else
    fail "missing: scripts/$script"
  fi
done

# ── 6. CLI facades ──
echo ""
echo "▸ CLI facades"
for cmd in memory-st memory-lt memory-recall memory-recall-safe memory-inject memory-promote agent-voice team agent-workflow; do
  if [[ -f "$AGENT_OS_HOME/bin/$cmd" ]]; then
    pass "bin/$cmd"
  else
    fail "missing: bin/$cmd"
  fi
done

# ── 7. Python dependencies ──
echo ""
echo "▸ Python"
if python3 -c "import yaml" 2>/dev/null; then
  pass "pyyaml installed"
else
  warn "pyyaml not installed (run: pip install pyyaml)"
fi

# ── 8. Optional services ──
echo ""
echo "▸ Optional services"
_key="${PINECONE_API_KEY:-}"
if [[ -z "$_key" || "$_key" == *"your-"* || "$_key" == *"placeholder"* ]]; then
  info "Pinecone: not configured (optional)"
else
  pass "Pinecone: configured"
fi

_neo4j="${NEO4J_URI:-}"
if [[ -z "$_neo4j" ]]; then
  info "Neo4j: not configured (optional)"
else
  pass "Neo4j: configured"
fi

# ── Summary ──
echo ""
if [[ $STATUS -eq 0 ]]; then
  echo "All checks passed ✓"
else
  echo "Some checks failed — review above ✗"
fi
exit $STATUS
