#!/usr/bin/env bash
# ESCALATE workflow: fast free agent attempts task, escalates to paid if stuck.
# Usage: escalate.sh <task_file>
#
# Free agent must end response with either:
#   SOLVED: <brief summary>
#   NEEDS_HELP: <specific question for escalation agent>
#
# Output: prints path to result file

set -euo pipefail
source "$(dirname "$0")/lib/run.sh"
source "$(dirname "$0")/lib/workspace.sh"

WS=""
POSITIONALS=()
while [ $# -gt 0 ]; do
    case "$1" in
        --workspace)
            WS="${2:-}"
            shift 2
            ;;
        --workspace=*)
            WS="${1#*=}"
            shift
            ;;
        --)
            shift
            while [ $# -gt 0 ]; do
                POSITIONALS+=("$1")
                shift
            done
            break
            ;;
        *)
            POSITIONALS+=("$1")
            shift
            ;;
    esac
done

TASK_FILE="${POSITIONALS[0]:-}"
[ -n "$TASK_FILE" ] || { echo "Usage: escalate.sh <task_file> [--workspace <name>]" >&2; exit 1; }
WF_ID="escalate-$(date +%s)"
WF_DIR="${AGENT_WORKFLOW_TMPDIR:-$HOME/.cache/agent-workflows}/runs/${WF_ID}"
mkdir -p "$WF_DIR"

TASK=$(cat "$TASK_FILE")

echo "[escalate] Workspace: $WF_DIR"
echo "[escalate] Dispatching to free agent (executor)..."

cat > "$WF_DIR/prompt_free.txt" << EOF
Attempt the following task. Work through it step by step.

If you complete it successfully, end your response with exactly:
SOLVED: <one sentence summary of what you did>

If you reach a point where you need deeper reasoning, more context, or are genuinely uncertain, stop and end with exactly:
NEEDS_HELP: <specific question that a more powerful reasoning agent should answer>

Do not guess. If uncertain, escalate.

Task:
$TASK
EOF
if [ -n "$WS" ]; then
    inject_workspace_context "$WS" "$WF_DIR/prompt_free.txt"
fi

FREE_OUT="$WF_DIR/free_agent.txt"
run_role executor "${WF_ID}-free" "$WF_DIR/prompt_free.txt" "$FREE_OUT"

echo "[escalate] Free agent responded."

if grep -q "^NEEDS_HELP:" "$FREE_OUT"; then
    QUESTION=$(grep "^NEEDS_HELP:" "$FREE_OUT" | sed 's/^NEEDS_HELP: //')
    echo "[escalate] Escalating to paid agent (escalation) — question: $QUESTION"

    cat > "$WF_DIR/prompt_paid.txt" << EOF
A task was partially completed by a junior agent. It got stuck and needs your help on a specific question. Answer the question, then complete the original task.

Original task:
$TASK

Junior agent's work so far:
$(cat "$FREE_OUT")

Specific question needing your answer:
$QUESTION

Complete the task fully.
EOF
    if [ -n "$WS" ]; then
        inject_workspace_context "$WS" "$WF_DIR/prompt_paid.txt"
    fi

    PAID_OUT="$WF_DIR/paid_agent.txt"
    run_role escalation "${WF_ID}-paid" "$WF_DIR/prompt_paid.txt" "$PAID_OUT"

    echo "[escalate] Paid agent responded."
    RESULT_OUT="$WF_DIR/result.txt"
    cat "$FREE_OUT" "$PAID_OUT" > "$RESULT_OUT"
    echo "[escalate] ESCALATED — result: $RESULT_OUT"
    echo "$RESULT_OUT"
else
    echo "[escalate] SOLVED by free agent — result: $FREE_OUT"
    echo "$FREE_OUT"
fi
