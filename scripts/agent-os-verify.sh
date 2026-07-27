#!/usr/bin/env bash
# Agent OS Verification Suite
# Tests: structure, registries, skills, memory, scripts.
# Exit code 0 = all pass, 1 = failures found.
#
# Usage:
#   agent-os-verify              # run all tests
#   agent-os-verify structure    # structure only
#   agent-os-verify registries   # registry validation only
#   agent-os-verify skills       # skills only
#   agent-os-verify memory       # memory stack only

set -euo pipefail

PASS=0
FAIL=0
SKIP=0
SECTION="${1:-all}"

pass()  { PASS=$((PASS+1)); echo "  PASS  $1"; }
fail()  { FAIL=$((FAIL+1)); echo "  FAIL  $1: $2"; }
skip()  { SKIP=$((SKIP+1)); echo "  SKIP  $1: $2"; }
header(){ echo ""; echo "=== $1 ==="; }

# ---------------------------------------------------------------------------
# STRUCTURE
# ---------------------------------------------------------------------------
test_structure() {
  header "Structure"

  # Required files
  for f in AGENTS.md BOOT.md README.md SETUP.md LICENSE PRIVACY_BOUNDARY.md install.sh config.env.template .env.template requirements.txt INDEX.md; do
    if [ -f "$AGENT_OS_HOME/$f" ]; then
      pass "$f"
    else
      fail "$f" "missing"
    fi
  done

  # Required directories
  for d in registry skills memory scripts bin tests docs examples; do
    if [ -d "$AGENT_OS_HOME/$d" ]; then
      pass "$d/"
    else
      fail "$d/" "missing"
    fi
  done

  # No git directory
  if [ ! -d "$AGENT_OS_HOME/.git" ]; then
    pass "no .git directory"
  else
    fail ".git" "should not exist in public release"
  fi
}

# ---------------------------------------------------------------------------
# REGISTRIES
# ---------------------------------------------------------------------------
test_registries() {
  header "Registries"

  for reg in skills.yaml tools.yaml workflows.yaml agents.yaml memory_tiers.yaml mcp_servers.yaml agent-manifest.yaml; do
    if [ -f "$AGENT_OS_HOME/registry/$reg" ]; then
      if python3 -c "import yaml; yaml.safe_load(open('$AGENT_OS_HOME/registry/$reg'))" 2>/dev/null; then
        pass "registry/$reg (valid YAML)"
      else
        fail "registry/$reg" "invalid YAML"
      fi
    else
      fail "registry/$reg" "missing"
    fi
  done

  # Verify skill paths resolve
  set +e
  local skill_check
  skill_check=$(python3 -c "
import pathlib, yaml
root = pathlib.Path('$AGENT_OS_HOME')
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
    print('\n'.join(missing))
    raise SystemExit(1)
" 2>&1)
  local skill_rc=$?
  set -e
  if [ $skill_rc -eq 0 ]; then
    pass "skill paths resolve"
  else
    fail "skill paths resolve" "$skill_check"
  fi

  # Verify tool paths resolve
  set +e
  local tool_check
  tool_check=$(python3 -c "
import pathlib, yaml
root = pathlib.Path('$AGENT_OS_HOME')
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
    print('\n'.join(missing))
    raise SystemExit(1)
" 2>&1)
  local tool_rc=$?
  set -e
  if [ $tool_rc -eq 0 ]; then
    pass "tool paths resolve"
  else
    fail "tool paths resolve" "$tool_check"
  fi
}

# ---------------------------------------------------------------------------
# SKILLS
# ---------------------------------------------------------------------------
test_skills() {
  header "Skills"

  for skill in acp recall lesson digest doc-audit skill-optimizer upward-handoff changes-review; do
    if [ -f "$AGENT_OS_HOME/skills/shared/$skill/SKILL.md" ]; then
      pass "$skill"
    else
      fail "$skill" "missing SKILL.md"
    fi
  done

  # Verify YAML syntax of all skills
  set +e
  local yaml_check
  yaml_check=$(python3 -c "
import pathlib, yaml
root = pathlib.Path('$AGENT_OS_HOME')
bad = []
for path in root.rglob('*.yaml'):
    if '.ossbuild' in path.parts or 'tests' in path.parts:
        continue
    try:
        yaml.safe_load(path.read_text())
    except Exception as exc:
        bad.append(f'{path.relative_to(root)}: {exc}')
if bad:
    print('\n'.join(bad))
    raise SystemExit(1)
" 2>&1)
  local yaml_rc=$?
  set -e
  if [ $yaml_rc -eq 0 ]; then
    pass "all YAML valid"
  else
    fail "YAML validation" "$yaml_check"
  fi
}

# ---------------------------------------------------------------------------
# MEMORY
# ---------------------------------------------------------------------------
test_memory() {
  header "Memory"

  # Core files
  for f in README.md core/short_term.py core/recall_hook.py core/promote.py core/inject.py core/citation.py core/ledger.py; do
    if [ -f "$AGENT_OS_HOME/memory/$f" ]; then
      pass "memory/$f"
    else
      fail "memory/$f" "missing"
    fi
  done

  # Adapters
  for adapter in pinecone neo4j; do
    if [ -f "$AGENT_OS_HOME/memory/adapters/$adapter/ADAPTER.md" ]; then
      pass "adapter: $adapter"
    else
      fail "adapter: $adapter" "missing"
    fi
  done

  # Python syntax check (ast.parse — no bytecode created)
  set +e
  local py_check
  py_check=$(python3 -c "
import ast, pathlib
root = pathlib.Path('$AGENT_OS_HOME/memory')
bad = []
for path in root.rglob('*.py'):
    if '__pycache__' in path.parts:
        continue
    try:
        ast.parse(path.read_text(), filename=str(path))
    except SyntaxError as exc:
        bad.append(f'{path.relative_to(root)}: {exc}')
if bad:
    print('\n'.join(bad))
    raise SystemExit(1)
" 2>&1)
  local py_rc=$?
  set -e
  if [ $py_rc -eq 0 ]; then
    pass "memory Python syntax"
  else
    fail "memory Python syntax" "$py_check"
  fi
}

# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
echo "Agent OS Verification Suite"
echo "=========================="
echo "Section: $SECTION"
echo ""

case "$SECTION" in
  structure) test_structure ;;
  registries) test_registries ;;
  skills) test_skills ;;
  memory) test_memory ;;
  all)
    test_structure
    test_registries
    test_skills
    test_memory
    ;;
  *)
    echo "Usage: agent-os-verify [all|structure|registries|skills|memory]"
    exit 1
    ;;
esac

echo ""
echo "=========================="
echo "PASS: $PASS  FAIL: $FAIL  SKIP: $SKIP"
echo "=========================="

[ "$FAIL" -eq 0 ] && exit 0 || exit 1
