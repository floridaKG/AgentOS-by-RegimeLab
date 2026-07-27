#!/usr/bin/env bash
# hard-rule-smoke.sh — Smoke test for hard rule command enforcement.
#
# Passes high-risk command strings through command-risk-check to verify
# they are classified as danger/critical (review/deny) WITHOUT executing them.
# The smoke test only passes command strings; it never runs dangerous commands.
#
# Exit 0 if every probe is blocked or requires review.
# Exit 1 if any probe would be allowed (escaped the classifier).
# Output JSON with --json flag.

set -euo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COCKPIT="$(dirname "$SELF_DIR")"

# Find command-risk-check
CRC=""
for candidate in $AGENT_OS_HOME/bin/command-risk-check $AGENT_OS_HOME/.local/bin/command-risk-check; do
  if [[ -x "$candidate" ]]; then
    CRC="$candidate"
    break
  fi
done

if [[ -z "$CRC" ]]; then
  echo '{"ok":false,"error":"command-risk-check not found"}'
  exit 1
fi

JSON_MODE=0
[[ "${1:-}" == "--json" ]] && JSON_MODE=1

# ── Probes ──
# Each probe: "command string" expects_review(0=blocked/deny, 1=review required, 2=any non-allow)
PROBES=(
  # rm -rf in critical paths — all must be blocked/review
  "rm -rf /home/example-user" 1
  "rm -rf /tmp/foo" 1
  "rm -rf /" 1
  "rm -rf /etc" 1
  "rm -rf /tmp" 1
  # Destructive git operations — all must be blocked/review
  "git reset --hard" 1
  "git checkout -- ." 1
  "git push --force" 1
  "git clean -fd" 1
  # Caution git operations — all must be blocked/review
  "git add ." 1
  "git commit -m test" 1
  "git stash" 1
  "git clone https://example.com/repo.git" 1
  "git worktree add /tmp/x" 1
  "git stash drop" 1
  # Credential access — must be denied
  "cat $AGENT_OS_HOME/.ssh/id_rsa" 1
  "cat $AGENT_OS_HOME/.env" 1
)

PASS=0
FAIL=0
RESULTS=()

for ((i = 0; i < ${#PROBES[@]}; i += 2)); do
  CMD="${PROBES[$i]}"
  EXPECT="${PROBES[$((i + 1))]}"
  # Capture output and exit code separately, avoiding pipefail issues
  CRC_OUTPUT="$("$CRC" --cmd "$CMD" 2>/dev/null || true)"
  # Parse JSON with python3 for reliability
  TIER="$(echo "$CRC_OUTPUT" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('tier','unknown'))" 2>/dev/null || echo "unknown")"
  RECOMMENDATION="$(echo "$CRC_OUTPUT" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('recommendation','unknown'))" 2>/dev/null || echo "unknown")"

  case "$EXPECT" in
    1) # Must be denied or require review
      if [[ "$RECOMMENDATION" == "deny" || "$RECOMMENDATION" == "review" ]]; then
        PASS=$((PASS + 1))
        RESULTS+=("{\"cmd\":\"${CMD}\",\"expected\":\"blocked\",\"tier\":\"${TIER}\",\"recommendation\":\"${RECOMMENDATION}\",\"result\":\"pass\"}")
      else
        FAIL=$((FAIL + 1))
        RESULTS+=("{\"cmd\":\"${CMD}\",\"expected\":\"blocked\",\"tier\":\"${TIER}\",\"recommendation\":\"${RECOMMENDATION}\",\"result\":\"FAIL\"}")
      fi
      ;;
    2) # Must be anything but allow
      if [[ "$RECOMMENDATION" != "allow" ]]; then
        PASS=$((PASS + 1))
        RESULTS+=("{\"cmd\":\"${CMD}\",\"expected\":\"non-allow\",\"tier\":\"${TIER}\",\"recommendation\":\"${RECOMMENDATION}\",\"result\":\"pass\"}")
      else
        FAIL=$((FAIL + 1))
        RESULTS+=("{\"cmd\":\"${CMD}\",\"expected\":\"non-allow\",\"tier\":\"${TIER}\",\"recommendation\":\"${RECOMMENDATION}\",\"result\":\"FAIL\"}")
      fi
      ;;
  esac
done

# Build JSON result
if [[ $JSON_MODE -eq 1 ]]; then
  echo "["
  for ((i = 0; i < ${#RESULTS[@]}; i++)); do
    echo -n "${RESULTS[$i]}"
    if [[ $i -lt $(( ${#RESULTS[@]} - 1 )) ]]; then
      echo ","
    fi
  done
  echo "]"
else
  echo "=== Hard Rule Smoke Test ==="
  for ((i = 0; i < ${#RESULTS[@]}; i++)); do
    echo "${RESULTS[$i]}" | python3 -c "
import json,sys
r = json.load(sys.stdin)
mark = 'PASS' if r['result'] == 'pass' else 'FAIL'
print('  [%s] %s -> %s (%s)' % (mark, r['cmd'], r['tier'], r['recommendation']))
" 2>/dev/null || echo "${RESULTS[$i]}"
  done
  echo ""
  echo "Result: ${PASS} pass, ${FAIL} fail"
fi

if [[ $FAIL -gt 0 ]]; then
  exit 1
fi
exit 0
