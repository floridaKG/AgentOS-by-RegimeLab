#!/usr/bin/env bash
# SWARM workflow: N parallel explorer agents attack a problem, reviewer synthesizes.
# Usage: swarm.sh <task_file> [n_agents]
#
# task_file: file containing the task/question
# n_agents:  number of parallel agents (default 3)
#
# Output: prints path to synthesis file

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
N="${POSITIONALS[1]:-3}"

[ -n "$TASK_FILE" ] || { echo "Usage: swarm.sh <task_file> [n_agents] [--workspace <name>]" >&2; exit 1; }
WF_ID="swarm-$(date +%s)"
WF_DIR="${AGENT_WORKFLOW_TMPDIR:-$HOME/.cache/agent-workflows}/runs/${WF_ID}"
mkdir -p "$WF_DIR"

TASK=$(cat "$TASK_FILE")

echo "[swarm] Workspace: $WF_DIR"
echo "[swarm] Launching $N explorer agents in parallel..."

PIDS=()
for i in $(seq 1 "$N"); do
    PROMPT_FILE="$WF_DIR/prompt_${i}.txt"
    OUT_FILE="$WF_DIR/agent_${i}.txt"
    cat > "$PROMPT_FILE" << EOF
You are explorer agent $i of $N in a parallel swarm. Your job is to investigate the following task from YOUR angle — focus on aspects other agents might miss. Be concrete. No preamble.

Task:
$TASK

Angle for agent $i:
$(case $i in
    1) echo "Focus on data and dependencies: what exists, what is missing, what the implementation needs to touch." ;;
    2) echo "Focus on edge cases, failure modes, and production risks." ;;
    3) echo "Focus on architecture and integration: how this fits into the existing system." ;;
    4) echo "Focus on performance, scaling, and cost implications." ;;
    *) echo "Focus on any remaining concerns not covered by the above angles." ;;
esac)
EOF
    if [ -n "$WS" ]; then
        inject_workspace_context "$WS" "$PROMPT_FILE"
    fi
    (run_role explorer "${WF_ID}-explorer-${i}" "$PROMPT_FILE" "$OUT_FILE") &
    PIDS+=($!)
    echo "[swarm] Agent $i launched (pid $!)"
done

echo "[swarm] Waiting for all agents..."
for pid in "${PIDS[@]}"; do wait "$pid" || true; done
echo "[swarm] All agents done."

# Build synthesis prompt
SYNTHESIS_PROMPT="$WF_DIR/synthesis_prompt.txt"
cat > "$SYNTHESIS_PROMPT" << EOF
You are a synthesis agent. $N explorer agents investigated the following task in parallel from different angles. Read all their findings, identify agreements and disagreements, and produce a final consolidated report.

Original task:
$TASK

EOF

for i in $(seq 1 "$N"); do
    echo "=== Explorer Agent $i ===" >> "$SYNTHESIS_PROMPT"
    cat "$WF_DIR/agent_${i}.txt" >> "$SYNTHESIS_PROMPT"
    echo "" >> "$SYNTHESIS_PROMPT"
done

cat >> "$SYNTHESIS_PROMPT" << 'EOF'
Produce:
1. Key findings (agreed across agents)
2. Disagreements or conflicting findings (flag these clearly)
3. Gaps — things no agent addressed that should be investigated
4. Final recommendation or verdict
EOF

SYNTHESIS_OUT="$WF_DIR/synthesis.txt"
REQUIRE=""
[ "${AGENT_STRICT:-}" = "1" ] && REQUIRE="^PASS:"
if ! run_role reviewer "${WF_ID}-synthesis" "$SYNTHESIS_PROMPT" "$SYNTHESIS_OUT" "$REQUIRE"; then
    synth_bytes=$(stat -c %s "$SYNTHESIS_OUT" 2>/dev/null || echo 0)
    if [ ! -f "$SYNTHESIS_OUT" ] || [ "$synth_bytes" -lt "${MIN_OUTPUT_BYTES:-50}" ]; then
        echo "[swarm] Synthesis failed: output missing or too small (${synth_bytes}B)." >&2
        exit 1
    fi
    if [ -n "$REQUIRE" ] && ! grep -qE "$REQUIRE" "$SYNTHESIS_OUT"; then
        echo "[swarm] Synthesis failed: required marker missing." >&2
        exit 1
    fi
    if grep -qiE "(AGENT_DISCONNECTED|ACP agent disconnected|connection_close|connection refused|ECONNREFUSED|429 too many requests|5[0-9][0-9] (internal server error|service unavailable|bad gateway)|free promotion ended|rate.?limit exceeded|quota exceeded|cannot apply --model|did not advertise that model)" "$SYNTHESIS_OUT" 2>/dev/null; then
        echo "[swarm] Synthesis failed: provider failure signature detected." >&2
        exit 1
    fi
    echo "[swarm] Reviewer returned non-zero, but synthesis output is complete; continuing." >&2
fi

echo "[swarm] Synthesis complete."
echo "[swarm] Result: $SYNTHESIS_OUT"
echo "$SYNTHESIS_OUT"
