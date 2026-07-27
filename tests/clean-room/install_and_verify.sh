#!/usr/bin/env bash
# Agent OS Clean-Room Installation Test
# Proves that a new user can install Agent OS in an isolated temporary HOME
# without access to the owner's machine, private repositories, or services.
#
# Proves: isolation, idempotency, CLI availability, config placement,
#         first-use memory write/recall, no original-tree mutation.
set -euo pipefail

STAGE="${1:-}"
if [[ -z "$STAGE" ]]; then
  echo "usage: $0 <agent-os-root>" >&2
  exit 2
fi
STAGE="$(cd "$STAGE" && pwd)"
echo "=== Agent OS Clean-Room Installation Test ==="
echo "Stage: $STAGE"
echo ""

# Create isolated HOME
CLEANROOM_DIR=$(mktemp -d)
CLEANROOM_HOME="$CLEANROOM_DIR/home"
LAUNCHER_HOME="$CLEANROOM_DIR/launcher-home"
mkdir -p "$CLEANROOM_HOME"
mkdir -p "$LAUNCHER_HOME"
export HOME="$CLEANROOM_HOME"

# Remove any AGENT_OS_HOME that might leak from the parent
unset AGENT_OS_HOME 2>/dev/null || true

echo "Clean-room HOME: $CLEANROOM_HOME"
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

# ── Step 1: Verify isolated environment ──
echo "--- Step 1: Isolated environment ---"
check "HOME is clean-room" bash -c 'test "$HOME" = "'"$CLEANROOM_HOME"'"'
check "No .config/agent-os yet" bash -c 'test ! -d "'"$CLEANROOM_HOME"'/.config/agent-os"'
check "Clean-room HOME has no agent-os state" bash -c 'test ! -d "'"$CLEANROOM_HOME"'/.local/state/agent-os"'
check "Clean-room HOME has no private keys" bash -c 'test ! -e "'"$CLEANROOM_HOME"'/.ssh/id_ed25519" && test ! -e "'"$CLEANROOM_HOME"'/.ssh/id_rsa"'
check "Original tree has no .git" bash -c "cd '$STAGE' && ! find '.' -mindepth 2 -name '.git' -type d | grep ."

# ── Step 2: Run installer ──
echo ""
echo "--- Step 2: Run installer ---"
check "install.sh executes" bash -c "AGENT_OS_TEST=1 AGENT_OS_TEST_HOME='$CLEANROOM_HOME' AGENT_OS_HOME='$STAGE' HOME='$LAUNCHER_HOME' bash '$STAGE/install.sh' 2>&1"
check "config.env created" bash -c 'test -f "'"$CLEANROOM_HOME"'/.config/agent-os/config.env"'
check "secrets.env created" bash -c 'test -f "'"$CLEANROOM_HOME"'/.config/agent-os/secrets.env"'
check "config.env has AGENT_OS_HOME" bash -c 'grep -q "AGENT_OS_HOME" "'"$CLEANROOM_HOME"'/.config/agent-os/config.env"'

# ── Step 3: Verify structure ──
echo ""
echo "--- Step 3: Verify structure ---"
check "AGENTS.md exists" test -f "$STAGE/AGENTS.md"
check "bootstrap.sh exists" test -f "$STAGE/bootstrap.sh"
check "BOOT.md exists" test -f "$STAGE/BOOT.md"
check "README.md exists" test -f "$STAGE/README.md"
check "SETUP.md exists" test -f "$STAGE/SETUP.md"
check "LICENSE exists" test -f "$STAGE/LICENSE"
check "PRIVACY_BOUNDARY.md exists" test -f "$STAGE/PRIVACY_BOUNDARY.md"
check "registry/ exists" test -d "$STAGE/registry"
check "skills/ exists" test -d "$STAGE/skills"
check "memory/ exists" test -d "$STAGE/memory"
check "scripts/ exists" test -d "$STAGE/scripts"
check "bin/ exists" test -d "$STAGE/bin"

# ── Step 4: Verify skills ──
echo ""
echo "--- Step 4: Verify skills ---"
for skill in acp recall lesson digest doc-audit skill-optimizer upward-handoff changes-review; do
  check "skill: $skill" test -f "$STAGE/skills/shared/$skill/SKILL.md"
done

# ── Step 5: Verify memory ──
echo ""
echo "--- Step 5: Verify memory ---"
check "memory/README.md" test -f "$STAGE/memory/README.md"
check "memory/core/short_term.py" test -f "$STAGE/memory/core/short_term.py"
check "memory/core/recall_hook.py" test -f "$STAGE/memory/core/recall_hook.py"
check "memory/core/promote.py" test -f "$STAGE/memory/core/promote.py"
check "adapter: pinecone" test -f "$STAGE/memory/adapters/pinecone/ADAPTER.md"
check "adapter: neo4j" test -f "$STAGE/memory/adapters/neo4j/ADAPTER.md"

# ── Step 6: Verify scripts ──
echo ""
echo "--- Step 6: Verify scripts ---"
check "agent-os-health.sh" test -f "$STAGE/scripts/agent-os-health.sh"
check "agent-os-verify.sh" test -f "$STAGE/scripts/agent-os-verify.sh"
check "registry-check.py" test -f "$STAGE/scripts/registry-check.py"

# ── Step 7: Verify CLI facades ──
echo ""
echo "--- Step 7: Verify CLI facades ---"
for cmd in memory-st memory-lt memory-recall memory-recall-safe memory-inject memory-promote agent-voice team agent-workflow agent-os agent-os-mcp agent-os-setup; do
  check "bin/$cmd" test -f "$STAGE/bin/$cmd"
done

# ── Step 8: Verify registries ──
echo ""
echo "--- Step 8: Verify registries ---"
check "skills.yaml parses" python3 -c "import yaml; yaml.safe_load(open('$STAGE/registry/skills.yaml'))"
check "tools.yaml parses" python3 -c "import yaml; yaml.safe_load(open('$STAGE/registry/tools.yaml'))"
check "workflows.yaml parses" python3 -c "import yaml; yaml.safe_load(open('$STAGE/registry/workflows.yaml'))"
check "agents.yaml parses" python3 -c "import yaml; yaml.safe_load(open('$STAGE/registry/agents.yaml'))"
check "memory_tiers.yaml parses" python3 -c "import yaml; yaml.safe_load(open('$STAGE/registry/memory_tiers.yaml'))"
check "mcp_servers.yaml parses" python3 -c "import yaml; yaml.safe_load(open('$STAGE/registry/mcp_servers.yaml'))"

# ── Step 9: Verify optional scaffolds ──
echo ""
echo "--- Step 9: Verify optional scaffolds ---"
check "init-vault.sh" test -f "$STAGE/scripts/init-vault.sh"
check "init-superdocs.sh" test -f "$STAGE/scripts/init-superdocs.sh"
check "vault-os example" test -f "$STAGE/examples/vault-os/README.md"
check "superdocs example" test -f "$STAGE/examples/superdocs/README.md"

# ── Step 10: Verify tests ──
echo ""
echo "--- Step 10: Verify tests ---"
check "cold_boot.sh" test -f "$STAGE/tests/smoke/cold_boot.sh"
check "release_gate.sh" test -f "$STAGE/tests/smoke/release_gate.sh"
check "privacy_gate.sh" test -f "$STAGE/tests/privacy/privacy_gate.sh"
check "install_and_verify.sh" test -f "$STAGE/tests/clean-room/install_and_verify.sh"

# ── Step 11: Vault init test ──
echo ""
echo "--- Step 11: Vault init test ---"
TEST_VAULT="$CLEANROOM_DIR/test-vault"
check "vault init creates vault" bash -c "HOME='$CLEANROOM_HOME' bash '$STAGE/scripts/init-vault.sh' --create '$TEST_VAULT'"
check "vault has BOOT.md" test -f "$TEST_VAULT/BOOT.md"
check "vault has GLOSSARY.md" test -f "$TEST_VAULT/GLOSSARY.md"

# ── Step 12: SuperDocs init test ──
echo ""
echo "--- Step 12: SuperDocs init test ---"
TEST_PROJECT="$CLEANROOM_DIR/test-project"
mkdir -p "$TEST_PROJECT"
check "superdocs init creates docs" bash -c "bash '$STAGE/scripts/init-superdocs.sh' --project test-project --path '$TEST_PROJECT'"
check "superdocs has governance" test -d "$TEST_PROJECT/docs/governance"
check "superdocs has guardrails" test -d "$TEST_PROJECT/docs/guardrails"
check "superdocs has skills" test -d "$TEST_PROJECT/docs/skills"
check "superdocs has workflows" test -d "$TEST_PROJECT/docs/workflows"
check "superdocs has registry" test -d "$TEST_PROJECT/docs/registry"
check "superdocs has POLICY.md" test -f "$TEST_PROJECT/docs/governance/POLICY.md"
check "superdocs has SKILL_GLOSSARY.md" test -f "$TEST_PROJECT/docs/skills/SKILL_GLOSSARY.md"

# ── Step 13: Idempotency ──
echo ""
echo "--- Step 13: Idempotency ---"
check "second install is idempotent" bash -c "AGENT_OS_TEST=1 AGENT_OS_TEST_HOME='$CLEANROOM_HOME' AGENT_OS_HOME='$STAGE' HOME='$LAUNCHER_HOME' bash '$STAGE/install.sh' 2>&1"
check "idempotent config preserved" bash -c 'test -f "'"$CLEANROOM_HOME"'/.config/agent-os/config.env" && grep -q "AGENT_OS_HOME" "'"$CLEANROOM_HOME"'/.config/agent-os/config.env"'
check "idempotent secrets preserved" bash -c 'test -f "'"$CLEANROOM_HOME"'/.config/agent-os/secrets.env"'

# ── Step 14: CLI availability in clean-room ──
echo ""
echo "--- Step 14: CLI availability ---"
for cmd in memory-st memory-lt memory-recall memory-recall-safe memory-inject memory-promote agent-voice team agent-workflow agent-os agent-os-mcp agent-os-setup; do
  check "bin/$cmd is executable" bash -c "test -x '$STAGE/bin/$cmd'"
done
check "MOE panels installed" test -f "$CLEANROOM_HOME/.config/agent-workflows/panels.toml"
check "MOE aliases installed" test -f "$CLEANROOM_HOME/.config/agent-workflows/model_aliases.toml"
check "agent-os-health.sh is executable" bash -c "test -x '$STAGE/scripts/agent-os-health.sh'"
check "agent-os-verify.sh is executable" bash -c "test -x '$STAGE/scripts/agent-os-verify.sh'"

# ── Step 14b: MCP availability ──
echo ""
echo "--- Step 14b: MCP availability ---"
check "agent-os CLI has mcp subcommand" bash -c "AGENT_OS_HOME='$STAGE' HOME='$CLEANROOM_HOME' PYTHONPATH='$STAGE:${PYTHONPATH:-}' python3 -m agent_os mcp --help 2>&1 | grep -q 'serve.*Start the MCP stdio server'"
check "agent-os-mcp launcher exists" bash -c "test -x '$STAGE/bin/agent-os-mcp'"
check "docs/MCP.md exists" test -f "$STAGE/docs/MCP.md"

# ── Step 15: No original-tree mutation ──
echo ""
echo "--- Step 15: No original-tree mutation ---"
check "STAGE tree unchanged (AGENTS.md exists)" bash -c "test -f '$STAGE/AGENTS.md'"
check "STAGE bin/ unchanged" bash -c "test -d '$STAGE/bin' && test -f '$STAGE/bin/memory-st'"
check "STAGE registry/ unchanged" bash -c "test -d '$STAGE/registry' && test -f '$STAGE/registry/skills.yaml'"
check "STAGE no new .sqlite files" bash -c "test -z \"$(find '$STAGE' -name '*.sqlite' -not -path '*/.ossbuild/*' 2>/dev/null)\""
check "STAGE no new .pyc outside __pycache__" bash -c "test -z \"$(find '$STAGE' -name '*.pyc' -not -path '*/__pycache__/*' -not -path '*/.ossbuild/*' 2>/dev/null)\""
check "DB not created in STAGE tree" bash -c "test ! -f '$STAGE/.local/state/agent-os/memory/short_term.sqlite'"

# ── Step 16: First memory write/recall in clean-room ──
echo ""
echo "--- Step 16: First memory write/recall ---"
check "memory-st init succeeds" bash -c "AGENT_OS_HOME='$STAGE' HOME='$CLEANROOM_HOME' python3 '$STAGE/memory/core/short_term.py' init 2>&1"
check "memory-st write succeeds" bash -c "AGENT_OS_HOME='$STAGE' HOME='$CLEANROOM_HOME' python3 '$STAGE/memory/core/short_term.py' write --run-id cleanroom-test --agent-id test-agent --workspace home --intent LESSON --kind observation --summary 'Clean room first-use test' --content-file /dev/stdin --source-ref cli:test <<< 'First use lesson content'"
check "memory-st query finds written record" bash -c "AGENT_OS_HOME='$STAGE' HOME='$CLEANROOM_HOME' python3 '$STAGE/memory/core/short_term.py' query --text 'first-use' --limit 5 2>&1 | grep -q 'ok.*true'"

# ── Cleanup ──
echo ""
echo "--- Cleanup ---"
echo "  Clean-room directory: $CLEANROOM_DIR (left for inspection)"

# ── Results ──
echo ""
echo "=== Clean-Room Test Results ==="
echo "  Passed: $PASS_COUNT"
echo "  Failed: $FAIL_COUNT"

if [ "$FAIL_COUNT" -eq 0 ]; then
  echo ""
  echo "=== CLEAN-ROOM PASS ==="
  exit 0
else
  echo ""
  echo "=== CLEAN-ROOM FAIL ==="
  exit 1
fi
