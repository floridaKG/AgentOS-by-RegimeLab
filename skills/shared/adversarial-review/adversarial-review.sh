#!/usr/bin/env bash
# adversarial-review.sh — Single-shot adversarial critique via ACP.
#
# Usage:
#   adversarial-review.sh <target_file | -> <topic> [--workspace WS] [--budget N]
#
#   <target_file>   Path to the file to critique (or - for stdin)
#   <topic>         Domain context topic for context-pack retrieval
#   --workspace WS  Target workspace (configured in roles.toml)
#   --budget N      Context-pack byte budget (default: 8000)
#
# Output: prints the reviewer's verdict and findings to stdout.
# Exit code: 0 = CLEAR, 1 = PROCEED WITH FIXES, 2 = BLOCKED, 3 = error.
#
# Requires: acp-task, context-pack.sh (both on PATH or at AGENT_OS_HOME).

set -euo pipefail

# ── Locate tools relative to AGENT_OS_HOME ──────────────────────────────────

: "${AGENT_OS_HOME:?AGENT_OS_HOME must be set}"
CONTEXT_PACK="${AGENT_OS_HOME}/scripts/context-pack.sh"
ACP_TASK="acp-task"  # Must be on PATH

# ── Defaults ─────────────────────────────────────────────────────────────────

WORKSPACE="home"
BUDGET=8000

# ── Adversarial rubric ──────────────────────────────────────────────────────

RUBRIC='ADVERSARIAL REVIEW RUBRIC

You are an adversarial reviewer. Your job is NOT to be helpful or agreeable.
Your job is to find the strongest case AGAINST the work presented below.

RULES:
1. ASSUME THE WORK IS WRONG. Start from the position that there are serious
   flaws. Your job is to find them, not to confirm the work is good.
2. HUNT FOR THE STRONGEST DISCONFIRMING EVIDENCE. Do not settle for minor
   nitpicks. Find the thing that would actually break the reasoning, invalidate
   the spec, or cause the decision to fail.
3. BE SPECIFIC. "This might have edge cases" is worthless. Name the edge case.
   "This assumption about X is wrong because Y" is what we need.
4. RANK BY SEVERITY. Not all flaws are equal. Use:
   - BLOCKER: Fundamentally breaks the work. Must be fixed before proceeding.
   - MAJOR: Significantly weakens the work. Should be fixed.
   - MINOR: Worth knowing but not blocking.
5. STATE WHAT WOULD CHANGE THE VERDICT. For each finding, note what evidence
   or fix would neutralize it. This prevents infinite adversarial spirals.

OUTPUT FORMAT:
## Verdict
<BLOCKED | PROCEED WITH FIXES | CLEAR> + one-paragraph rationale

## Findings
| # | Severity | Finding | What would neutralize it |
|---|----------|---------|--------------------------|
| 1 | BLOCKER/MAJOR/MINOR | ... | ... |

## Strongest Counter-Argument
The single most compelling case against this work, stated as forcefully as possible.

## What Would Make This Airtight
The 2-3 changes that would most strengthen the work against adversarial critique.'

usage() {
    cat <<'EOF'
Usage: adversarial-review.sh <target_file | -> <topic> [--workspace WS] [--budget N]

Arguments:
  <target_file>   Path to the file to critique, or - to read from stdin
  <topic>         Domain context topic for context-pack retrieval

Options:
  --workspace WS  Target workspace (configured in roles.toml, default: home)
  --budget N      Context-pack byte budget (default: 8000)

Examples:
  adversarial-review.sh /tmp/spec.md "backtest methodology"
  echo "We should use MAE instead of Sharpe." | adversarial-review.sh - "optimization"

Exit codes:
  0  CLEAR
  1  PROCEED WITH FIXES
  2  BLOCKED
  3  Error
EOF
    exit 3
}

# ── Parse arguments ──────────────────────────────────────────────────────────

for _arg in "$@"; do
    case "$_arg" in
        --help|-h) usage; exit 0 ;;
    esac
done

[ $# -lt 2 ] && usage

TARGET=""
TOPIC=""

while [ $# -gt 0 ]; do
    case "$1" in
        --workspace) WORKSPACE="${2:-}"; shift 2 ;;
        --workspace=*) WORKSPACE="${1#*=}"; shift ;;
        --budget) BUDGET="${2:-}"; shift 2 ;;
        --budget=*) BUDGET="${1#*=}"; shift ;;
        --help|-h) usage ;;
        -*)
            echo "Error: unknown option: $1" >&2
            usage
            ;;
        *)
            [ -z "$TARGET" ] && TARGET="$1" && shift && continue
            [ -z "$TOPIC" ] && TOPIC="$1" && shift && continue
            echo "Error: unexpected argument: $1" >&2
            usage
            ;;
    esac
done

[ -z "$TARGET" ] || [ -z "$TOPIC" ] && { echo "Error: target and topic required." >&2; usage; }

# Validate budget is numeric
[[ "$BUDGET" =~ ^[0-9]+$ ]] || { echo "Error: budget must be a number." >&2; exit 3; }

# ── Read target material ────────────────────────────────────────────────────

TARGET_TEXT=""
if [ "$TARGET" = "-" ]; then
    TARGET_TEXT="$(cat)"
elif [ -f "$TARGET" ]; then
    TARGET_TEXT="$(cat "$TARGET")"
else
    echo "Error: target file not found: $TARGET" >&2
    exit 3
fi

[ -z "$TARGET_TEXT" ] && { echo "Error: target is empty." >&2; exit 3; }

# ── Gather context ──────────────────────────────────────────────────────────

echo "[adversarial-review] Gathering context for topic: $TOPIC" >&2
CONTEXT=$("$CONTEXT_PACK" "$TOPIC" --budget="$BUDGET" 2>/dev/null || echo "(no context available)")

# ── Build the dispatch body ─────────────────────────────────────────────────

BODY="$RUBRIC

---

CONTEXT FROM MEMORY TIERS:
$CONTEXT

---

TARGET MATERIAL TO CRITIQUE:
$TARGET_TEXT"

# ── Dispatch adversarial reviewer ───────────────────────────────────────────

echo "[adversarial-review] Dispatching adversarial reviewer..." >&2

RESULT=$("$ACP_TASK" reviewer "$WORKSPACE" "Adversarial review: $TOPIC" \
    --body "$BODY" \
    --context "$TOPIC" \
    --wait 2>&1) || true

# ── Parse verdict ───────────────────────────────────────────────────────────

if [ -z "$RESULT" ]; then
    echo "Error: reviewer returned empty output." >&2
    exit 3
fi

echo "$RESULT"

VERDICT_LINE=$(echo "$RESULT" | grep -iE '^## Verdict' -A1 | tail -1 | tr '[:lower:]' '[:upper:]')

if echo "$VERDICT_LINE" | grep -qi "BLOCKED"; then
    echo "[adversarial-review] Verdict: BLOCKED" >&2
    exit 2
elif echo "$VERDICT_LINE" | grep -qi "PROCEED WITH FIXES"; then
    echo "[adversarial-review] Verdict: PROCEED WITH FIXES" >&2
    exit 1
elif echo "$VERDICT_LINE" | grep -qi "CLEAR"; then
    echo "[adversarial-review] Verdict: CLEAR" >&2
    exit 0
else
    echo "[adversarial-review] Verdict: UNPARSABLE" >&2
    exit 0
fi
