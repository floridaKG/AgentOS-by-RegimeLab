#!/usr/bin/env bash
# acp_mock_test.sh — Deterministic ACP dispatch test using mock mode
#
# This test validates the ACP task creation, dispatch, completion, failure,
# and timeout contracts WITHOUT requiring paid provider calls or acpx.
# It exercises the state machine in the ACP scripts directly.
#
# Usage:
#   bash tests/smoke/acp_mock_test.sh <agent-os-root>
#
# Prerequisites: Python 3, bash. No paid API keys or acpx required.

set -euo pipefail

STAGE="${1:-}"
if [[ -z "$STAGE" ]]; then
  echo "usage: $0 <agent-os-root>" >&2
  exit 2
fi
STAGE="$(cd "$STAGE" && pwd)"
echo "=== Agent OS ACP Mock Dispatch Test ==="
echo "Stage: $STAGE"
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

# Clean temp HOME for the test
CLEAN_HOME=$(mktemp -d)
export HOME="$CLEAN_HOME"
export AGENT_OS_HOME="$STAGE"
mkdir -p "$HOME/.config/agent-os"

# ── Step 1: Verify ACP infrastructure exists ──
echo "--- Step 1: ACP infrastructure structure ---"
check "acp_send.py exists" test -f "$STAGE/.config/agent-workflows/acp/acp_send.py"
check "acp_completion.py exists" test -f "$STAGE/.config/agent-workflows/acp/acp_completion.py"
check "acp-task binary exists" test -f "$STAGE/bin/acp-task"
check "acp-daemon binary exists" test -f "$STAGE/bin/acp-daemon"
check "acp-health binary exists" test -f "$STAGE/bin/acp-health"
check "roles.toml exists" test -f "$STAGE/.config/agent-workflows/roles.toml"
check "roles.toml has supported providers" bash -c "grep -q 'opencode\|codex\|claude' '$STAGE/.config/agent-workflows/roles.toml'"
check "roles.toml does NOT have unsupported providers" bash -c "! grep -qE 'droid|pi|hermes|cline' '$STAGE/.config/agent-workflows/roles.toml'"

# ── Step 2: Mock envelope creation ──
echo ""
echo "--- Step 2: Mock envelope creation ---"

SEND_OUTPUT=$(python3 "$STAGE/.config/agent-workflows/acp/acp_send.py" \
  send executor home "Mock smoke test task" \
  --body "This is a mock test. Respond with ACK." \
  --json 2>&1 || true)

check "acp_send.py produces valid JSON" bash -c "echo '$SEND_OUTPUT' | python3 -c 'import sys,json; json.load(sys.stdin)' 2>/dev/null"

RUN_ID=$(echo "$SEND_OUTPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('run_id',''))" 2>/dev/null || echo "")
check "acp_send.py returns a run_id" bash -c "test -n '$RUN_ID'"

check "Envelope file exists" test -f "$STAGE/.local/state/agent-os/acp/runs/$RUN_ID/envelope.json"

STATE=$(python3 -c "
import json
env = json.load(open('$STAGE/.local/state/agent-os/acp/runs/$RUN_ID/envelope.json'))
print(env.get('state',''))
" 2>/dev/null || echo "")
check "Envelope state is queued" bash -c "test '$STATE' = 'queued'"

# ── Step 3: Verify dry-run dispatch mode exists in acp-daemon ──
echo ""
echo "--- Step 3: Dry-run dispatch detection ---"

# Verify that acp-daemon handles missing acpx gracefully (dry-run mode)
check "acp-daemon has dry-run fallback for missing acpx" bash -c "grep -q 'acpx not found' '$STAGE/bin/acp-daemon'"
check "acp-daemon has _do_dry_run_dispatch function" bash -c "grep -q '_do_dry_run_dispatch' '$STAGE/bin/acp-daemon'"
check "acp-provider-smoke has acpx-availability check" bash -c "grep -q 'command -v acpx' '$STAGE/bin/acp-provider-smoke'"

# ── Step 4: Verify completion contract ──
echo ""
echo "--- Step 4: Completion contract ---"

COMPLETION_OUTPUT=$(python3 "$STAGE/.config/agent-workflows/acp/acp_completion.py" "$RUN_ID" --json 2>&1 || true)
check "acp_completion.py returns valid JSON for run" bash -c "echo '$COMPLETION_OUTPUT' | python3 -c 'import sys,json; json.load(sys.stdin)' 2>/dev/null"

# ── Step 5: Verify failure contract ──
echo ""
echo "--- Step 5: Failure contract ---"

FAIL_OUTPUT=$(python3 "$STAGE/.config/agent-workflows/acp/acp_send.py" \
  send explorer home "Deliberate mock failure test" \
  --body "This task will fail by design." \
  --json 2>&1 || true)

FAIL_RUN_ID=$(echo "$FAIL_OUTPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('run_id',''))" 2>/dev/null || echo "")

if [[ -n "$FAIL_RUN_ID" ]]; then
  # Walk the state machine: queued → claimed → running → failed
  python3 "$STAGE/.config/agent-workflows/acp/acp_send.py" \
    transition "$FAIL_RUN_ID" claimed --reason "Claimed for failure test" 2>/dev/null || true
  python3 "$STAGE/.config/agent-workflows/acp/acp_send.py" \
    transition "$FAIL_RUN_ID" running --reason "Running failure test" 2>/dev/null || true
  python3 "$STAGE/.config/agent-workflows/acp/acp_send.py" \
    transition "$FAIL_RUN_ID" failed --reason "Mock failure test" 2>/dev/null || true

  FAIL_COMPLETION=$(python3 "$STAGE/.config/agent-workflows/acp/acp_completion.py" "$FAIL_RUN_ID" --json 2>&1 || true)
  FAIL_STATE=$(echo "$FAIL_COMPLETION" | python3 -c "import sys,json; print(json.load(sys.stdin).get('state',''))" 2>/dev/null || echo "")
  check "Failed run reports failed state" bash -c "test '$FAIL_STATE' = 'failed'"
fi

# ── Step 6: Verify timeout contract ──
echo ""
echo "--- Step 6: Timeout contract ---"

TIMEOUT_OUTPUT=$(python3 "$STAGE/.config/agent-workflows/acp/acp_send.py" \
  send reviewer home "Mock timeout test" \
  --body "This tests the timeout contract." \
  --json 2>&1 || true)

TIMEOUT_RUN_ID=$(echo "$TIMEOUT_OUTPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('run_id',''))" 2>/dev/null || echo "")

if [[ -n "$TIMEOUT_RUN_ID" ]]; then
  # Walk the state machine: queued → claimed → running → failed (timeout)
  # This mirrors what acp-daemon does on subprocess.TimeoutExpired
  python3 "$STAGE/.config/agent-workflows/acp/acp_send.py" \
    transition "$TIMEOUT_RUN_ID" claimed --reason "Claimed for timeout test" 2>/dev/null || true
  python3 "$STAGE/.config/agent-workflows/acp/acp_send.py" \
    transition "$TIMEOUT_RUN_ID" running --reason "Running timeout test" 2>/dev/null || true
  python3 "$STAGE/.config/agent-workflows/acp/acp_send.py" \
    transition "$TIMEOUT_RUN_ID" failed --reason "worker_timeout (600s)" 2>/dev/null || true

  TO_COMPLETION=$(python3 "$STAGE/.config/agent-workflows/acp/acp_completion.py" "$TIMEOUT_RUN_ID" --json 2>&1 || true)
  TO_STATE=$(echo "$TO_COMPLETION" | python3 -c "import sys,json; print(json.load(sys.stdin).get('state',''))" 2>/dev/null || echo "")
  TO_CLASS=$(echo "$TO_COMPLETION" | python3 -c "import sys,json; print(json.load(sys.stdin).get('classification',''))" 2>/dev/null || echo "")
  check "Timed-out run reports failed state" bash -c "test '$TO_STATE' = 'failed'"
  check "Timed-out run classifies as timeout" bash -c "test '$TO_CLASS' = 'timeout'"
fi

# ── Step 7: Verify agents.yaml only has supported agents ──
echo ""
echo "--- Step 7: Agent registry validation ---"
AGENTS_YAML="$STAGE/registry/agents.yaml"
check "agents.yaml has claude" bash -c "grep -q \"id: claude\" '$AGENTS_YAML'"
check "agents.yaml has codex" bash -c "grep -q \"id: codex\" '$AGENTS_YAML'"
check "agents.yaml has opencode" bash -c "grep -q \"id: opencode\" '$AGENTS_YAML'"
check "agents.yaml does NOT have cline" bash -c "! grep -q \"id: cline\" '$AGENTS_YAML'"
check "agents.yaml does NOT have droid" bash -c "! grep -q \"id: droid\" '$AGENTS_YAML'"
check "agents.yaml does NOT have pi" bash -c "! grep -q \"id: pi\" '$AGENTS_YAML'"
check "agents.yaml has status field" bash -c "grep -q 'status:' '$AGENTS_YAML'"
check "agents.yaml has configuration field" bash -c "grep -q 'configuration:' '$AGENTS_YAML'"

# ── Step 8: Verify VALID_ROLES don't contain unsupported agents ──
echo ""
echo "--- Step 8: ACP VALID_ROLES audit ---"
check "acp_send.py VALID_ROLES no droid" bash -c "! grep -q '\"droid\"' '$STAGE/.config/agent-workflows/acp/acp_send.py'"
check "acp-task no droid in VALID_ROLES" bash -c "! grep -q '\"droid\"' '$STAGE/bin/acp-task'"
check "run.sh provider enum does not include droid" bash -c "! grep -q '|droid|pi|cline' '$STAGE/.config/agent-workflows/lib/run.sh'"
check "acpx-dispatch.sh does not map droid/pi" bash -c "! grep -q 'droid)    agent=\"droid\"' '$STAGE/.config/agent-workflows/lib/acpx-dispatch.sh'"

# ── Cleanup ──
echo ""
echo "--- Cleanup ---"
rm -rf "$CLEAN_HOME" 2>/dev/null || true
echo "  Clean-room HOME removed: $CLEAN_HOME"

# ── Results ──
echo ""
echo "=== ACP Mock Test Results ==="
echo "  Passed: $PASS_COUNT"
echo "  Failed: $FAIL_COUNT"

if [[ $FAIL_COUNT -eq 0 ]]; then
  echo ""
  echo "=== ACP MOCK TEST PASS ==="
  exit 0
else
  echo ""
  echo "=== ACP MOCK TEST FAIL ==="
  exit 1
fi
