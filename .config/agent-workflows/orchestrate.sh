#!/usr/bin/env bash
# ORCHESTRATOR workflow: explore -> architect -> execute -> review -> fix loop
# Usage: orchestrate.sh <goal_file>
# Output: prints path to final reviewed result

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

GOAL_FILE="${POSITIONALS[0]:-}"
MAX_FIX_ITERATIONS="${POSITIONALS[1]:-2}"
[ -n "$GOAL_FILE" ] || { echo "Usage: orchestrate.sh <goal_file> [max_fix_iterations] [--workspace <name>]" >&2; exit 1; }
[ "${AGENT_FAST:-}" = "1" ] && MAX_FIX_ITERATIONS=1
WF_ID="orch-$(date +%s)"
WF_DIR="${AGENT_WORKFLOW_TMPDIR:-$HOME/.cache/agent-workflows}/runs/${WF_ID}"
mkdir -p "$WF_DIR"

GOAL=$(cat "$GOAL_FILE")

echo ""
echo "========================================"
echo "[orchestrate] ID: $WF_ID"
echo "[orchestrate] Workspace: $WF_DIR"
echo "========================================"

# PHASE 1: EXPLORE
echo ""
echo "[PHASE 1] EXPLORE — 3 parallel explorer agents..."

write_explore_prompt() {
    local i="$1"
    local focus
    case $i in
        1) focus="What already exists: relevant files, services, data pipelines, APIs this goal touches." ;;
        2) focus="Potential blockers: missing dependencies, data gaps, conflicting code, production constraints." ;;
        3) focus="Integration surface: files to create or modify, existing patterns to follow." ;;
    esac
    cat > "$WF_DIR/explore_prompt_${i}.txt" << EOF
You are explorer agent $i of 3. Navigate from ~/AGENT_OS.md first, then gather context for this goal.

Goal:
$GOAL

Your focus: $focus

Be specific — file paths, function names, actual values where relevant.
EOF
    if [ -n "$WS" ]; then
        inject_workspace_context "$WS" "$WF_DIR/explore_prompt_${i}.txt"
    fi
}

for i in 1 2 3; do
    write_explore_prompt "$i"
    (run_role explorer "${WF_ID}-explore-${i}" "$WF_DIR/explore_prompt_${i}.txt" "$WF_DIR/context_${i}.txt") &
done
wait
echo "[PHASE 1] Done."

# PHASE 2: ARCHITECT
echo ""
echo "[PHASE 2] ARCHITECT — big-pickle building plan..."

cat > "$WF_DIR/architect_prompt.txt" << EOF
You are the architect. Use explorer findings to produce an execution-ready implementation plan.

Goal:
$GOAL

=== Explorer 1: Existing Code ===
$(cat "$WF_DIR/context_1.txt")

=== Explorer 2: Blockers ===
$(cat "$WF_DIR/context_2.txt")

=== Explorer 3: Integration Surface ===
$(cat "$WF_DIR/context_3.txt")

Output a markdown plan with:
1. Files to create (purpose)
2. Files to modify (what changes)
3. Numbered implementation steps (specific enough for executor agents)
4. Acceptance criteria
5. Blockers to resolve before execution
EOF
if [ -n "$WS" ]; then
    inject_workspace_context "$WS" "$WF_DIR/architect_prompt.txt"
fi

run_role architect "${WF_ID}-architect" "$WF_DIR/architect_prompt.txt" "$WF_DIR/plan.md"
echo "[PHASE 2] Plan written."

# PHASE 3: EXECUTE
echo ""
echo "[PHASE 3] EXECUTE — 2 parallel executor agents..."

PLAN=$(cat "$WF_DIR/plan.md")

for i in 1 2; do
    local_focus="$(case $i in
        1) echo "Core implementation: new files, core logic, service layer." ;;
        2) echo "Supporting work: config, router registration, API client, nav entries, integration glue." ;;
    esac)"
    cat > "$WF_DIR/exec_prompt_${i}.txt" << EOF
HARD RULES FOR SPAWNED AGENTS (read before anything else):
- NEVER run rm, rmdir, mv-to-delete, or shred. The runtime blocks these at the shell.
- To replace a file: write to <path>.tmp then rename over the target.
- To "delete" a processed file: rename it into an archive/ directory.
- If you think you need rm, emit a HELP packet instead; cleanup is the orchestrator's job.
- No git add, commit, push, checkout, reset, stash, branch. Read-only git is fine.
- Absolute paths only. Never ~/. Agent OS resolves ~ unexpectedly.
- End every report with STUMBLES: and CONFIRMED: sections.

You are executor agent $i of 2. Follow the plan exactly. Do not add features beyond the plan.

Goal: $GOAL

Plan:
$PLAN

Your stream: $local_focus

List every file you created or modified when done.
EOF
    if [ -n "$WS" ]; then
        inject_workspace_context "$WS" "$WF_DIR/exec_prompt_${i}.txt"
    fi
    (run_role executor "${WF_ID}-exec-${i}" "$WF_DIR/exec_prompt_${i}.txt" "$WF_DIR/exec_result_${i}.txt") &
done
wait
echo "[PHASE 3] Execution complete."

# PHASE 4: REVIEW
echo ""
echo "[PHASE 4] REVIEW — deepseek-r1 reviewing..."

cat > "$WF_DIR/review_prompt.txt" << EOF
You are a code reviewer. Review the execution results against the plan and goal.

Goal: $GOAL

Plan:
$PLAN

=== Executor 1 ===
$(cat "$WF_DIR/exec_result_1.txt")

=== Executor 2 ===
$(cat "$WF_DIR/exec_result_2.txt")

Check: acceptance criteria met, bugs/security issues, missing pieces, pattern adherence.

End with exactly one of:
PASS: <one sentence summary>
ISSUES: <comma-separated list of specific issues>
EOF
if [ -n "$WS" ]; then
    inject_workspace_context "$WS" "$WF_DIR/review_prompt.txt"
fi

REQUIRE=""
[ "${AGENT_STRICT:-}" = "1" ] && REQUIRE="^PASS:"
run_role reviewer "${WF_ID}-review" "$WF_DIR/review_prompt.txt" "$WF_DIR/review.txt" "$REQUIRE"
echo "[PHASE 4] Review done."

# PHASE 5: FIX LOOP
FIX_ITER=0
while grep -q "^ISSUES:" "$WF_DIR/review.txt" && [ "$FIX_ITER" -lt "$MAX_FIX_ITERATIONS" ]; do
    FIX_ITER=$((FIX_ITER + 1))
    ISSUES=$(grep "^ISSUES:" "$WF_DIR/review.txt" | sed 's/^ISSUES: //')
    echo ""
    echo "[PHASE 5] FIX iteration $FIX_ITER — issues: $ISSUES"

    IFS=',' read -ra ISSUE_LIST <<< "$ISSUES"
    FIX_PIDS=()
    for idx in "${!ISSUE_LIST[@]}"; do
        ISSUE=$(echo "${ISSUE_LIST[$idx]}" | xargs)
        cat > "$WF_DIR/fix_${FIX_ITER}_${idx}.txt" << EOF
HARD RULES FOR SPAWNED AGENTS (read before anything else):
- NEVER run rm, rmdir, mv-to-delete, or shred. The runtime blocks these at the shell.
- To replace a file: write to <path>.tmp then rename over the target.
- To "delete" a processed file: rename it into an archive/ directory.
- If you think you need rm, emit a HELP packet instead; cleanup is the orchestrator's job.
- No git add, commit, push, checkout, reset, stash, branch. Read-only git is fine.
- Absolute paths only. Never ~/. Agent OS resolves ~ unexpectedly.
- End every report with STUMBLES: and CONFIRMED: sections.

You are a fix agent. Fix only this issue, do not touch unrelated code.

Goal: $GOAL
Plan: $PLAN
Issue: $ISSUE

Confirm what you changed.
EOF
    if [ -n "$WS" ]; then
        inject_workspace_context "$WS" "$WF_DIR/fix_${FIX_ITER}_${idx}.txt"
    fi
        (run_role executor "${WF_ID}-fix-${FIX_ITER}-${idx}" "$WF_DIR/fix_${FIX_ITER}_${idx}.txt" "$WF_DIR/fix_result_${FIX_ITER}_${idx}.txt") &
        FIX_PIDS+=($!)
    done
    for pid in "${FIX_PIDS[@]}"; do wait "$pid" || true; done

    # Extract actual file paths from fix output and read their contents
    FIX_FILE_CONTENTS=""
    for idx in "${!ISSUE_LIST[@]}"; do
        FIX_RESULT="$WF_DIR/fix_result_${FIX_ITER}_${idx}.txt"
        while IFS= read -r candidate; do
            [ -z "$candidate" ] && continue
            resolved=""
            if [ -f "$candidate" ]; then
                resolved="$candidate"
            elif [ -f "$PWD/$candidate" ]; then
                resolved="$PWD/$candidate"
            fi
            if [ -n "$resolved" ] && ! grep -qF "$resolved" <<< "$FIX_FILE_CONTENTS" 2>/dev/null; then
                FIX_FILE_CONTENTS="$FIX_FILE_CONTENTS
=== $resolved ===
$(cat "$resolved")
"
            fi
        done < <(grep -oP '\b(?:/[a-zA-Z0-9_./-]+|[a-zA-Z0-9_./-]+)\.[a-zA-Z0-9]+\b' "$FIX_RESULT" 2>/dev/null || true)
    done

    # Re-review with actual file contents (not fix agent's claims)
    cat > "$WF_DIR/re_review_${FIX_ITER}.txt" << EOF
Re-review after fixes. Confirm whether issues are resolved.
Original issues: $ISSUES
Fix results: $FIX_FILE_CONTENTS
End with: PASS: <summary>  or  ISSUES: <remaining issues>
EOF
    run_role reviewer "${WF_ID}-re-review-${FIX_ITER}" "$WF_DIR/re_review_${FIX_ITER}.txt" "$WF_DIR/review.txt" "$REQUIRE"
    echo "[FIX] Re-review done (iter $FIX_ITER)."
done

echo ""
echo "========================================"
FINAL_STATUS=$(grep -E "^(PASS|ISSUES):" "$WF_DIR/review.txt" | head -1 || echo "UNKNOWN")
echo "[orchestrate] Final: $FINAL_STATUS"
echo "[orchestrate] Artifacts: $WF_DIR"
echo "[orchestrate] Plan: $WF_DIR/plan.md"
echo "[orchestrate] Review: $WF_DIR/review.txt"
echo "========================================"
echo "$WF_DIR/review.txt"
