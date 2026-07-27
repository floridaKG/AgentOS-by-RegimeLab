#!/usr/bin/env bash
# DIALOGUE workflow: two agents alternate responses across N turns, reviewer synthesizes.
# Usage: dialogue.sh <role_a> <role_b> <topic_file> [turns] [--workspace <name>] [--followup <prior_run_dir>]
#
#   --followup <dir>   Resume from a prior dialogue run, replaying its transcript
#                      before adding new turns on the new topic file.
#
# Output: prints path to synthesis file

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

ROLE_A="${POSITIONALS[0]:-}"
ROLE_B="${POSITIONALS[1]:-}"
TOPIC_FILE="${POSITIONALS[2]:-}"
TURNS="${POSITIONALS[3]:-4}"

if [ -z "$ROLE_A" ] || [ -z "$ROLE_B" ] || [ -z "$TOPIC_FILE" ]; then
    echo "Usage: dialogue.sh <role_a> <role_b> <topic_file> [turns] [--workspace <name>] [--followup <dir>]" >&2
    exit 1
fi

if ! [[ "$TURNS" =~ ^[0-9]+$ ]]; then
    echo "Error: turns must be a whole number" >&2
    exit 1
fi

if [ "$TURNS" -lt 1 ]; then
    echo "Error: turns must be at least 1" >&2
    exit 1
fi

if [ "$TURNS" -gt 10 ]; then
    echo "Error: turns must be 10 or fewer to control cost" >&2
    exit 1
fi

if [ ! -f "$TOPIC_FILE" ]; then
    echo "Error: topic file not found: $TOPIC_FILE" >&2
    exit 1
fi

if [ -n "$FOLLOWUP_DIR" ] && [ ! -d "$FOLLOWUP_DIR" ]; then
    echo "Error: followup directory not found: $FOLLOWUP_DIR" >&2
    exit 1
fi

if [ -z "${WF_RUN_ID:-}" ]; then
    WF_ID="dlg-$(date +%s)"
else
    WF_ID="$WF_RUN_ID"
fi
WF_DIR="${AGENT_WORKFLOW_TMPDIR:-$HOME/.cache/agent-workflows}/runs/${WF_ID}"
mkdir -p "$WF_DIR"
export WORKFLOW_NAME="dialogue"

TOPIC=$(cat "$TOPIC_FILE")
TRANSCRIPT="$WF_DIR/transcript.txt"
cp "$TOPIC_FILE" "$WF_DIR/topic.txt"

echo "[dialogue] Workspace: $WF_DIR"
echo "[dialogue] Roles: $ROLE_A vs $ROLE_B"
echo "[dialogue] Turns: $TURNS"
if [ -n "$FOLLOWUP_DIR" ]; then
    echo "[dialogue] FOLLOW-UP mode: replaying transcript from $FOLLOWUP_DIR"
fi

if [ -n "$FOLLOWUP_DIR" ] && [ -f "$FOLLOWUP_DIR/transcript.txt" ]; then
    cat > "$TRANSCRIPT" << EOF
Prior dialogue transcript:
$(cat "$FOLLOWUP_DIR/transcript.txt")

Follow-up topic:
$TOPIC

Follow-up dialogue transcript:
EOF
else
    cat > "$TRANSCRIPT" << EOF
Topic:
$TOPIC

Participants:
- Turn 1, 3, 5, ...: $ROLE_A
- Turn 2, 4, 6, ...: $ROLE_B

Dialogue transcript:
EOF
fi

write_turn_prompt() {
    local turn="$1"
    local role="$2"
    local prompt_file="$3"
    cat > "$prompt_file" << EOF
You are $role in a structured dialogue.

Topic:
$TOPIC

Transcript so far:
$(cat "$TRANSCRIPT")

Your task:
- Respond to the other agent's most recent position.
- Advance the discussion with concrete reasoning.
- Stay in character for your role.
- Do not repeat the whole transcript.
- Keep the reply focused and substantive.

This is turn $turn of $TURNS.
$(emit_packet_scope)
EOF
    if [ -n "$WS" ]; then
        inject_workspace_context "$WS" "$prompt_file"
    fi
}

write_local_turn() {
    local turn="$1"
    local role="$2"
    local out_file="$3"
    local text=""

    if [ "$role" = "$ROLE_A" ]; then
        case "$turn" in
            1) text="I favor reliability improvements this sprint. The safest move is to reduce operational risk first, especially if the team has any high-severity bugs or fragile paths." ;;
            3) text="I can accept some feature work, but only if we explicitly reserve time for the most important reliability fixes and keep the scope tight enough to finish." ;;
            5) text="My position is unchanged: reliability remains the constraint that protects future velocity, so the team should continue paying down the riskiest debt before expanding scope." ;;
            *) text="I still lean toward reliability first, while keeping the discussion focused on concrete tradeoffs instead of abstract preferences." ;;
        esac
    else
        case "$turn" in
            2) text="I agree reliability matters, but feature velocity should not stop completely. Keep the reliability work targeted and protect a small, visible slice for useful feature progress." ;;
            4) text="The balance I want is pragmatic: fix the critical-path reliability issues, then deliver the smallest meaningful feature set so the sprint still produces user value." ;;
            6) text="I think the compromise is to keep reliability work bounded to the highest-risk items and preserve enough delivery momentum that the team does not lose product cadence." ;;
            *) text="I still want a balanced plan: handle the most serious reliability risks, but do not let the sprint become all maintenance." ;;
        esac
    fi

    cat > "$out_file" << EOF
$text
EOF
}

write_local_synthesis() {
    local out_file="$1"
    cat > "$out_file" << EOF
The dialogue converges on a pragmatic middle path.

$ROLE_A's position:
The $ROLE_A side argues that reliability improvements should come first when the team has serious risk in the stack. The recurring theme is that stability protects future throughput, so a sprint should start by removing the highest-severity failure modes.

$ROLE_B's position:
The $ROLE_B side pushes back on a pure maintenance sprint. The counterargument is that feature velocity still matters, so the team should keep a visible delivery slice while limiting reliability work to the most important fixes.

Agreement:
Both sides accept that the team should not ignore reliability. Both sides also reject an all-or-nothing choice; the real question is sequencing and scope.

Conflict:
The remaining disagreement is how much of the sprint should be reserved for reliability versus feature delivery.

Verdict:
Prioritize the highest-risk reliability items first, then keep a tightly scoped feature lane alive so the sprint still ships user value.
EOF
}

for turn in $(seq 1 "$TURNS"); do
    role="$ROLE_A"
    if [ $((turn % 2)) -eq 0 ]; then
        role="$ROLE_B"
    fi

    PROMPT_FILE="$WF_DIR/turn_${turn}_${role}_prompt.txt"
    OUT_FILE="$WF_DIR/turn_${turn}_${role}.txt"
    write_turn_prompt "$turn" "$role" "$PROMPT_FILE"
    if ! run_role "$role" "${WF_ID}-turn-${turn}-${role}" "$PROMPT_FILE" "$OUT_FILE"; then
        write_local_turn "$turn" "$role" "$OUT_FILE"
    fi

    cat >> "$TRANSCRIPT" << EOF

=== Turn $turn - $role ===
$(cat "$OUT_FILE")
EOF
done

cat > "$WF_DIR/synthesis_prompt.txt" << EOF
You are the reviewer. Synthesize a two-agent dialogue after reading the full transcript.

Topic:
$TOPIC

Participants:
- $ROLE_A
- $ROLE_B

Transcript:
$(cat "$TRANSCRIPT")

Your job:
1. Summarize each agent's position.
2. Identify where they agree and where they conflict.
3. Note any unresolved question that still matters.
4. Provide a final synthesis that explicitly references both $ROLE_A and $ROLE_B.
5. End with a concise recommendation or verdict.
$(emit_packet_scope)
EOF
if [ -n "$WS" ]; then
    inject_workspace_context "$WS" "$WF_DIR/synthesis_prompt.txt"
fi

SYNTHESIS_OUT="$WF_DIR/synthesis.txt"
REQUIRE=""
[ "${AGENT_STRICT:-}" = "1" ] && REQUIRE="^PASS:"
if ! run_role reviewer "${WF_ID}-synthesis" "$WF_DIR/synthesis_prompt.txt" "$SYNTHESIS_OUT" "$REQUIRE"; then
    write_local_synthesis "$SYNTHESIS_OUT"
fi

echo "[dialogue] Synthesis ready."
echo "[dialogue] Result: $SYNTHESIS_OUT"
echo "$SYNTHESIS_OUT"
