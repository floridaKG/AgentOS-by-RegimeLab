#!/usr/bin/env bash
# REDTEAM workflow: proposer defends/refines an artifact, attacker finds holes, adjudicator decides.
# Usage: redteam.sh <artifact_file> [turns] [--proposer <role>] [--attacker <role>] [--adjudicator <role>] [--workspace <name>] [--followup <dir>]
#
#   --followup <dir>   Resume from a prior redteam run, replaying its transcript
#                      before adding new turns on the new artifact file.
#
# Output: prints the run directory as the last line of stdout.

set -euo pipefail
source "$(dirname "$0")/lib/run.sh"
source "$(dirname "$0")/lib/workspace.sh"
source "$(dirname "$0")/lib/packet.sh"

usage() {
    echo "Usage: redteam.sh <artifact_file> [turns] [--proposer <role>] [--attacker <role>] [--adjudicator <role>] [--workspace <name>] [--followup <dir>]" >&2
}

WS=""
FOLLOWUP_DIR=""
# Default adversarial pair: distinct reasoning providers (claude opus vs codex).
# proposer != attacker provider is enforced below.
PROPOSER="hard_escalation"
ATTACKER="escalation"
ADJUDICATOR="hard_escalation"
POSITIONALS=()
while [ $# -gt 0 ]; do
    case "$1" in
        --proposer)
            PROPOSER="${2:-}"
            shift 2
            ;;
        --proposer=*)
            PROPOSER="${1#*=}"
            shift
            ;;
        --attacker)
            ATTACKER="${2:-}"
            shift 2
            ;;
        --attacker=*)
            ATTACKER="${1#*=}"
            shift
            ;;
        --adjudicator)
            ADJUDICATOR="${2:-}"
            shift 2
            ;;
        --adjudicator=*)
            ADJUDICATOR="${1#*=}"
            shift
            ;;
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

ARTIFACT_FILE="${POSITIONALS[0]:-}"
TURNS="${POSITIONALS[1]:-4}"

if [ -z "$ARTIFACT_FILE" ]; then
    usage
    exit 1
fi

if [ -z "$PROPOSER" ] || [ -z "$ATTACKER" ] || [ -z "$ADJUDICATOR" ]; then
    echo "Error: proposer, attacker, and adjudicator roles must be non-empty" >&2
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

if [ ! -f "$ARTIFACT_FILE" ]; then
    echo "Error: artifact file not found: $ARTIFACT_FILE" >&2
    exit 1
fi

if [ -n "$FOLLOWUP_DIR" ] && [ ! -d "$FOLLOWUP_DIR" ]; then
    echo "Error: followup directory not found: $FOLLOWUP_DIR" >&2
    exit 1
fi

role_field() {
    local role="$1"
    local field="$2"
    awk -v role="$role" -v field="$field" '
        $0 ~ "^\\["role"\\]" { in_role=1; next }
        in_role && /^\[/ { in_role=0 }
        in_role && $0 ~ "^[[:space:]]*"field"[[:space:]]*=" {
            value=$0
            sub(/^[^=]*=[[:space:]]*/, "", value)
            gsub(/^"/, "", value)
            gsub(/"$/, "", value)
            print value
            exit
        }
    ' "$ROLES_FILE"
}

role_chain_provider() {
    local role="$1"
    awk -v role="$role" '
        $0 ~ "^\\["role"\\]" { in_role=1; next }
        in_role && /^\[/ { exit }
        in_role && /^chain/ { collecting=1 }
        collecting {
            if (match($0, /"[^"]+"/)) {
                s = substr($0, RSTART+1, RLENGTH-2)
                split(s, parts, ":")
                print parts[1]
                exit
            }
        }
    ' "$ROLES_FILE"
}

role_provider() {
    local role="$1"
    local provider
    provider="$(role_field "$role" "provider")"
    if [ -z "$provider" ]; then
        provider="$(role_chain_provider "$role")"
    fi
    printf '%s\n' "$provider"
}

role_cost() {
    local role="$1"
    role_field "$role" "cost"
}

warn_role_quality() {
    local role="$1"
    local provider="$2"
    local cost="$3"
    if [ "$provider" != "claude" ] && [ "$provider" != "codex" ]; then
        echo "[redteam] Warning: role '$role' resolves to provider '$provider', not claude/codex reasoning." >&2
    fi
    if [ "$cost" = "free" ]; then
        echo "[redteam] Warning: role '$role' is cost=free; red-team quality depends on a sharp attacker/adjudicator." >&2
    fi
}

PROPOSER_PROVIDER="$(role_provider "$PROPOSER")"
ATTACKER_PROVIDER="$(role_provider "$ATTACKER")"
ADJUDICATOR_PROVIDER="$(role_provider "$ADJUDICATOR")"
PROPOSER_COST="$(role_cost "$PROPOSER")"
ATTACKER_COST="$(role_cost "$ATTACKER")"
ADJUDICATOR_COST="$(role_cost "$ADJUDICATOR")"

if [ -z "$PROPOSER_PROVIDER" ]; then
    echo "Error: proposer role '$PROPOSER' does not resolve to a provider in $ROLES_FILE" >&2
    exit 1
fi
if [ -z "$ATTACKER_PROVIDER" ]; then
    echo "Error: attacker role '$ATTACKER' does not resolve to a provider in $ROLES_FILE" >&2
    exit 1
fi
if [ -z "$ADJUDICATOR_PROVIDER" ]; then
    echo "Error: adjudicator role '$ADJUDICATOR' does not resolve to a provider in $ROLES_FILE" >&2
    exit 1
fi
if [ "$PROPOSER_PROVIDER" = "$ATTACKER_PROVIDER" ]; then
    echo "Error: proposer and attacker must resolve to different providers; '$PROPOSER' and '$ATTACKER' both use '$PROPOSER_PROVIDER'." >&2
    exit 1
fi

warn_role_quality "$PROPOSER" "$PROPOSER_PROVIDER" "$PROPOSER_COST"
warn_role_quality "$ATTACKER" "$ATTACKER_PROVIDER" "$ATTACKER_COST"
warn_role_quality "$ADJUDICATOR" "$ADJUDICATOR_PROVIDER" "$ADJUDICATOR_COST"

if [ -z "${WF_RUN_ID:-}" ]; then
    WF_ID="rt-$(date +%Y%m%d-%H%M%S)"
else
    WF_ID="$WF_RUN_ID"
fi
WF_DIR="${AGENT_WORKFLOW_TMPDIR:-$HOME/.cache/agent-workflows}/runs/${WF_ID}"
mkdir -p "$WF_DIR"
export WORKFLOW_NAME="redteam"

ARTIFACT=$(cat "$ARTIFACT_FILE")
TRANSCRIPT="$WF_DIR/transcript.txt"
cp "$ARTIFACT_FILE" "$WF_DIR/artifact.txt"

echo "[redteam] Workspace: $WF_DIR"
echo "[redteam] Roles: proposer=$PROPOSER ($PROPOSER_PROVIDER), attacker=$ATTACKER ($ATTACKER_PROVIDER), adjudicator=$ADJUDICATOR ($ADJUDICATOR_PROVIDER)"
echo "[redteam] Turns: $TURNS"
if [ -n "$FOLLOWUP_DIR" ]; then
    echo "[redteam] FOLLOW-UP mode: replaying transcript from $FOLLOWUP_DIR"
fi

if [ -n "$FOLLOWUP_DIR" ] && [ -f "$FOLLOWUP_DIR/transcript.txt" ]; then
    cat > "$TRANSCRIPT" << EOF
Prior red-team transcript:
$(cat "$FOLLOWUP_DIR/transcript.txt")

Follow-up artifact:
$ARTIFACT

Follow-up red-team transcript:
EOF
else
    cat > "$TRANSCRIPT" << EOF
Artifact under review:
$ARTIFACT

Participants:
- Odd turns: proposer ($PROPOSER) defends/refines and concedes broken parts.
- Even turns: attacker ($ATTACKER) finds holes only.

Red-team transcript:
EOF
fi

write_turn_prompt() {
    local turn="$1"
    local role="$2"
    local side="$3"
    local prompt_file="$4"

    if [ "$side" = "proposer" ]; then
        cat > "$prompt_file" << EOF
You are $role acting as the proposer in a red-team adversarial review.

Artifact:
$ARTIFACT

Transcript so far:
$(cat "$TRANSCRIPT")

Your task:
- Here is the artifact and the attacks so far. Defend what is sound, concede what is genuinely broken, and revise.
- Do not hand-wave.
- Address concrete holes directly.
- Do not repeat the whole transcript.

This is turn $turn of $TURNS.
$(emit_packet_scope)
EOF
    else
        cat > "$prompt_file" << EOF
You are $role acting as the attacker in a red-team adversarial review.

Artifact:
$ARTIFACT

Transcript so far:
$(cat "$TRANSCRIPT")

Your task:
- Your only job is to find holes in the artifact and the proposer's defense: wrong assumptions, security flaws, unhandled edge cases, untested paths, cost/safety violations.
- For each hole give: severity (BLOCKER/MAJOR/MINOR), why it breaks, and a concrete repro or scenario.
- Do not praise.
- Do not propose the fix.
- Do not write balanced summary prose.

This is turn $turn of $TURNS.
$(emit_packet_scope)
EOF
    fi

    if [ -n "$WS" ]; then
        inject_workspace_context "$WS" "$prompt_file"
    fi
}

write_local_turn() {
    local turn="$1"
    local role="$2"
    local side="$3"
    local out_file="$4"

    if [ "$side" = "proposer" ]; then
        cat > "$out_file" << EOF
As $role, I defend only the parts of the artifact that are explicit and testable. I concede that any unstated dependency, missing verification command, or ambiguous owner boundary is genuinely broken until the transcript proves otherwise. Revised position for turn $turn: proceed only with claims tied to concrete files, commands, and acceptance criteria.
EOF
    else
        cat > "$out_file" << EOF
- MAJOR: The artifact may rely on unstated runtime assumptions. Why it breaks: a reviewer cannot reproduce the intended behavior from the artifact alone. Concrete repro: hand the artifact to a fresh agent with no prior context and ask for the exact command sequence; any missing command, path, or expected output blocks execution.
- MINOR: The artifact may not define an explicit negative test. Why it breaks: regressions can pass if only the happy path is checked. Concrete repro: run the validation after intentionally violating one required condition and confirm whether the gate fails.
EOF
    fi
}

write_adjudicator_prompt() {
    local prompt_file="$1"
    cat > "$prompt_file" << EOF
You are $ADJUDICATOR acting as the adjudicator in a red-team adversarial review.

Artifact:
$ARTIFACT

Transcript:
$(cat "$TRANSCRIPT")

Your job:
1. Identify only holes that survived proposer rebuttal.
2. Mark each surviving or refuted hole with severity BLOCKER, MAJOR, or MINOR.
3. Decide a Go / No-Go verdict.
4. Use this exact schema:

## Holes (surviving rebuttal)
| id | severity | hole | proposer rebuttal | verdict (stands/refuted) |
## Go / No-Go
<PASS | PASS-WITH-FIXES | FAIL> + one-paragraph rationale
## Required fixes before proceeding (if any)

Verdict rules:
- PASS means no required fixes remain.
- PASS-WITH-FIXES means required fixes exist but the artifact is not fundamentally invalid.
- FAIL means one or more BLOCKER holes stand or the artifact is unsafe to proceed.
$(emit_packet_scope)
EOF
    if [ -n "$WS" ]; then
        inject_workspace_context "$WS" "$prompt_file"
    fi
}

write_local_verdict() {
    local out_file="$1"
    cat > "$out_file" << EOF
## Holes (surviving rebuttal)
| id | severity | hole | proposer rebuttal | verdict (stands/refuted) |
| RT-1 | MAJOR | The artifact may not be reproducible unless every required command, file path, and expected output is explicit. | The proposer conceded unstated dependencies are broken until proven. | stands |
| RT-2 | MINOR | The artifact may lack a negative test that proves the gate fails when a required condition is violated. | The proposer limited proceeding to concrete acceptance criteria. | stands |
## Go / No-Go
PASS-WITH-FIXES: The artifact can proceed only after the surviving reproducibility and negative-test gaps are closed; no BLOCKER was established in the local fallback review.
## Required fixes before proceeding (if any)
- Add explicit reproduction commands, expected outputs, and ownership boundaries.
- Add at least one negative validation path that proves the review gate catches a known-bad condition.
EOF
}

for turn in $(seq 1 "$TURNS"); do
    role="$PROPOSER"
    side="proposer"
    if [ $((turn % 2)) -eq 0 ]; then
        role="$ATTACKER"
        side="attacker"
    fi

    PROMPT_FILE="$WF_DIR/turn_${turn}_${side}_${role}_prompt.txt"
    OUT_FILE="$WF_DIR/turn_${turn}_${side}_${role}.txt"
    write_turn_prompt "$turn" "$role" "$side" "$PROMPT_FILE"
    # REDTEAM_FORCE_LOCAL=1 skips real dispatch (free, deterministic smoke testing).
    if [ "${REDTEAM_FORCE_LOCAL:-}" = "1" ]; then
        write_local_turn "$turn" "$role" "$side" "$OUT_FILE"
    elif ! run_role "$role" "${WF_ID}-turn-${turn}-${side}-${role}" "$PROMPT_FILE" "$OUT_FILE"; then
        write_local_turn "$turn" "$role" "$side" "$OUT_FILE"
    fi

    cat >> "$TRANSCRIPT" << EOF

=== Turn $turn - $role ($side) ===
$(cat "$OUT_FILE")
EOF
done

ADJUDICATOR_PROMPT="$WF_DIR/adjudicator_prompt.txt"
VERDICT_OUT="$WF_DIR/verdict.md"
write_adjudicator_prompt "$ADJUDICATOR_PROMPT"
if [ "${REDTEAM_FORCE_LOCAL:-}" = "1" ]; then
    write_local_verdict "$VERDICT_OUT"
elif ! run_role "$ADJUDICATOR" "${WF_ID}-adjudicator" "$ADJUDICATOR_PROMPT" "$VERDICT_OUT" "## Go / No-Go"; then
    write_local_verdict "$VERDICT_OUT"
fi

VERDICT="$(awk '
    /^## Go \/ No-Go/ { in_section=1; next }
    in_section && /^## / { exit }
    in_section && /FAIL/ { print "FAIL"; exit }
    in_section && /PASS-WITH-FIXES/ { print "PASS-WITH-FIXES"; exit }
    in_section && /PASS/ { print "PASS"; exit }
' "$VERDICT_OUT")"

EXIT_CODE=1
case "$VERDICT" in
    PASS|PASS-WITH-FIXES)
        EXIT_CODE=0
        ;;
    FAIL)
        EXIT_CODE=2
        ;;
    *)
        echo "[redteam] Error: unable to parse verdict from $VERDICT_OUT" >&2
        EXIT_CODE=3
        ;;
esac

echo "[redteam] Verdict ready."
echo "[redteam] Result: $VERDICT_OUT"
echo "$WF_DIR"
exit "$EXIT_CODE"
