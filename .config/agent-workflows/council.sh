#!/usr/bin/env bash
# COUNCIL workflow: 3 agents form independent opinions, moderator surfaces disagreements.
# Agents do NOT see each other's answers before forming their own.
# Usage: council.sh <problem_file> [--workspace <name>] [--followup <prior_run_dir>]
#
#   --followup <dir>   Resume from a prior council run, adding a new question
#                      to the existing opinions. All prior opinions are replayed
#                      as context for the second-round moderator.
#
# Output: prints path to council verdict file

set -euo pipefail
source "$(dirname "$0")/lib/run.sh"
source "$(dirname "$0")/lib/workspace.sh"
source "$(dirname "$0")/lib/packet.sh"

WS=""
FOLLOWUP_DIR=""
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
        --followup)
            FOLLOWUP_DIR="${2:-}"
            shift 2
            ;;
        --followup=*)
            FOLLOWUP_DIR="${1#*=}"
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

PROBLEM_FILE="${POSITIONALS[0]:-}"
[ -n "$PROBLEM_FILE" ] || { echo "Usage: council.sh <problem_file> [--workspace <name>] [--followup <dir>]" >&2; exit 1; }
# Use packet run_id if available, else generate fresh
if [ -z "${WF_RUN_ID:-}" ]; then
    WF_ID="${FOLLOWUP_DIR:-council-$(date +%s)}"
else
    WF_ID="$WF_RUN_ID"
fi
WF_DIR="${AGENT_WORKFLOW_TMPDIR:-$HOME/.cache/agent-workflows}/runs/${WF_ID}"
mkdir -p "$WF_DIR"

PROBLEM=$(cat "$PROBLEM_FILE")

echo "[council] Workspace: $WF_DIR"
echo "[council] Objective: ${WF_OBJECTIVE:-"(not set)"}"

# Follow-up mode: skip independent opinions, reuse prior ones, go straight to round 2
if [ -n "$FOLLOWUP_DIR" ] && [ -d "$FOLLOWUP_DIR" ]; then
    echo "[council] FOLLOW-UP mode — using opinions from $FOLLOWUP_DIR"
    cp "$FOLLOWUP_DIR/opinion_1.txt" "$WF_DIR/opinion_1.txt" 2>/dev/null || true
    cp "$FOLLOWUP_DIR/opinion_2.txt" "$WF_DIR/opinion_2.txt" 2>/dev/null || true
    cp "$FOLLOWUP_DIR/opinion_3.txt" "$WF_DIR/opinion_3.txt" 2>/dev/null || true
    echo "[council] Prior opinions loaded, skipping to follow-up round."
else
    # Fresh run: normal independent opinions (unchanged logic)
    cp "$PROBLEM_FILE" "$WF_DIR/topic.txt"
    echo "[council] Convening council — 3 agents forming independent opinions..."

# Agent 1: Explorer model (pragmatic, ground-level view)
cat > "$WF_DIR/prompt_1.txt" << EOF
You are council member 1. Form an independent opinion on the following question. Be direct. State your position clearly and give your top 3 reasons. No hedging.

Question:
$PROBLEM
$(emit_packet_scope)
EOF
if [ -n "$WS" ]; then
    inject_workspace_context "$WS" "$WF_DIR/prompt_1.txt"
fi

# Agent 2: Architect model (structural, systems view)
cat > "$WF_DIR/prompt_2.txt" << EOF
You are council member 2. Form an independent opinion on the following question. Approach it from a systems and architecture perspective. State your position clearly and give your top 3 reasons. No hedging.

Question:
$PROBLEM
$(emit_packet_scope)
EOF
if [ -n "$WS" ]; then
    inject_workspace_context "$WS" "$WF_DIR/prompt_2.txt"
fi

# Agent 3: Reviewer model (critical, risk-focused view)
cat > "$WF_DIR/prompt_3.txt" << EOF
You are council member 3. Form an independent opinion on the following question. Your role is to find flaws, risks, and edge cases in any proposed solution. State your position clearly. Be the skeptic.

Question:
$PROBLEM
$(emit_packet_scope)
EOF
if [ -n "$WS" ]; then
    inject_workspace_context "$WS" "$WF_DIR/prompt_3.txt"
fi

# Run all three in parallel
(run_role explorer "${WF_ID}-member-1" "$WF_DIR/prompt_1.txt" "$WF_DIR/opinion_1.txt") &
PID1=$!

(run_role architect "${WF_ID}-member-2" "$WF_DIR/prompt_2.txt" "$WF_DIR/opinion_2.txt") &
PID2=$!

(run_role reviewer "${WF_ID}-member-3" "$WF_DIR/prompt_3.txt" "$WF_DIR/opinion_3.txt") &
PID3=$!

wait "$PID1" "$PID2" "$PID3" || true
echo "[council] All members responded."

fi
# END follow-up else block

# Build moderator prompt (shared: fresh run OR follow-up round)
if [ -n "$FOLLOWUP_DIR" ] && [ -d "$FOLLOWUP_DIR" ]; then
    cat > "$WF_DIR/moderator_prompt.txt" << EOF
You are the council moderator. This is a FOLLOW-UP round. The same three council members previously gave opinions. Now they respond to a NEW question. Replay their prior positions and assess their new answers. Your job:

1. Restate each member's position from the first round in 1 sentence
2. Summarize their response to the new question
3. Identify where members AGREE and DISAGREE on the new question
4. Give a final moderator verdict

Original question (round 1):
$(cat "$FOLLOWUP_DIR/topic.txt" 2>/dev/null || echo "(unknown)")

New question (round 2):
$PROBLEM

=== Prior opinion of Member 1 (Pragmatist) ===
$(cat "$WF_DIR/opinion_1.txt")

=== Prior opinion of Member 2 (Architect) ===
$(cat "$WF_DIR/opinion_2.txt")

=== Prior opinion of Member 3 (Skeptic) ===
$(cat "$WF_DIR/opinion_3.txt")

Follow-up question for all three members:
$PROBLEM
EOF
else
    cat > "$WF_DIR/moderator_prompt.txt" << EOF
You are the council moderator. Three independent council members have formed opinions on the following question. They did NOT see each other's answers. Your job is to:

1. Summarize each position in 2-3 sentences
2. Identify where members AGREE
3. Identify where members DISAGREE — these are the most important points
4. Call out any position that is an outlier and explain why it might be right or wrong
5. Give a final moderator verdict: what the council recommends, and what the unresolved tension is if any

Original question:
$PROBLEM

=== Member 1 (Pragmatist) ===
$(cat "$WF_DIR/opinion_1.txt")

=== Member 2 (Architect) ===
$(cat "$WF_DIR/opinion_2.txt")

=== Member 3 (Skeptic) ===
$(cat "$WF_DIR/opinion_3.txt")
$(emit_packet_scope)
EOF
fi

VERDICT_OUT="$WF_DIR/verdict.txt"
REQUIRE=""
[ "${AGENT_STRICT:-}" = "1" ] && REQUIRE="^PASS:"
run_role architect "${WF_ID}-moderator" "$WF_DIR/moderator_prompt.txt" "$VERDICT_OUT" "$REQUIRE"

echo "[council] Verdict ready."
echo "[council] Result: $VERDICT_OUT"
echo "$VERDICT_OUT"
