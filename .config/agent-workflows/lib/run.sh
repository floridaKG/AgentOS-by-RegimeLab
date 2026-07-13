#!/usr/bin/env bash
# Centralized agent runner with validation, retry, and fallback chains.
#
# Source this file. Provides:
#   run_role <role> <title> <prompt_file> <out_file> [require_marker]
#
# Behavior:
#   1. Reads ordered chain from roles.toml for <role>.
#   2. Tries each "provider:model" in order.
#   3. Validates output: exists, size >= MIN_OUTPUT_BYTES, contains require_marker if set.
#   4. On failure: falls through to next entry in chain, logs the failure.
#   5. Appends one JSONL row per attempt to ~/.cache/agent-workflows/run-log.jsonl.
#
# Returns 0 on success (out_file is valid), nonzero if entire chain failed.

ROLES_FILE="${ROLES_FILE:-$HOME/.config/agent-workflows/roles.toml}"
RUN_LOG="${RUN_LOG:-$HOME/.cache/agent-workflows/run-log.jsonl}"
MIN_OUTPUT_BYTES="${MIN_OUTPUT_BYTES:-50}"
ROLE_TIMEOUT_S="${ROLE_TIMEOUT_S:-300}"
mkdir -p "$(dirname "$RUN_LOG")"

# ── Source shared acpx dispatch primitive ──────────────────────────────────────
# Provides acpx_dispatch() — shared provider→agent mapping, model selection,
# acpx invocation (session or one-shot), opencode flock+retry, timeout,
# NDJSON parsing.  ACPX_DISPATCH_RICH is left OFF so PATH B stays narrow
# (agent_message_chunk only) — tool_call_update must NOT leak into output
# or _validate false-rejects on failure signatures in tool text.
# Use BASH_SOURCE (this lib's own path), not $0: run.sh is sourced by workflow
# scripts in the parent dir, so $0 points at the workflow script, not lib/.
[ -n "${ACPX_DISPATCH_LOADED:-}" ] || source "$(dirname "${BASH_SOURCE[0]}")/acpx-dispatch.sh"

# ---------------------------------------------------------------------------
# Safety gate: loads safety.toml deny/require_confirm rules
# Provides: check_command_safe <cmd> [workspace]
# ---------------------------------------------------------------------------
SAFETY_SCRIPT="$(dirname "${BASH_SOURCE[0]}")/safety.sh"
[ -f "$SAFETY_SCRIPT" ] && source "$SAFETY_SCRIPT"

# ---------------------------------------------------------------------------
# Workflow packet support (hardening: self-describing runs)
# ---------------------------------------------------------------------------
# These variables are injected by workflow scripts before calling run_role.
# If set, each log line will include them for postmortem reconstruction.
WF_PACKET_FILE="${WF_PACKET_FILE:-}"
WF_GOAL_FILE="${WF_GOAL_FILE:-}"
WF_RUN_ID="${WF_RUN_ID:-}"
WF_WORKSPACE="${WF_WORKSPACE:-}"
WF_OBJECTIVE="${WF_OBJECTIVE:-}"
WF_ALLOWED_PATHS="${WF_ALLOWED_PATHS:-}"
WF_DENIED_PATHS="${WF_DENIED_PATHS:-}"

# Read chain entries for a role: prints each "provider:model" on its own line.
_role_chain() {
    local role="$1"
    # Prefer an explicit chain = [...] (legacy format).
    local chain
    chain=$(awk -v role="$role" '
        $0 ~ "^\\["role"\\]" { in_role=1; next }
        in_role && /^\[/ { in_role=0 }
        in_role && /^chain/ { collecting=1 }
        collecting {
            if (match($0, /"[^"]+"/)) {
                s = substr($0, RSTART+1, RLENGTH-2)
                print s
            }
            if ($0 ~ /\]/) { collecting=0; in_role=0; exit }
        }
    ' "$ROLES_FILE")
    if [ -n "$chain" ]; then
        printf '%s\n' "$chain"
        return 0
    fi
    # New format: synthesize provider:model from separate keys (matches roles.toml +
    # acp_to_run_agent.sh). Without this every .sh workflow falls through to canned
    # local output and never dispatches an agent.
    local provider model
    provider=$(awk -v role="$role" '
        $0 ~ "^\\["role"\\]" { in_role=1; next }
        in_role && /^\[/ { exit }
        in_role && /^[[:space:]]*provider[[:space:]]*=/ {
            v=$0; sub(/^[^=]*=[[:space:]]*/,"",v); gsub(/"/,"",v); print v; exit }
    ' "$ROLES_FILE")
    model=$(awk -v role="$role" '
        $0 ~ "^\\["role"\\]" { in_role=1; next }
        in_role && /^\[/ { exit }
        in_role && /^[[:space:]]*model[[:space:]]*=/ {
            v=$0; sub(/^[^=]*=[[:space:]]*/,"",v); gsub(/"/,"",v); print v; exit }
    ' "$ROLES_FILE")
    if [ -n "$provider" ] && [ -n "$model" ]; then
        printf '%s:%s\n' "$provider" "$model"
    fi
}

# Strip ANSI escapes.
_strip_ansi() {
    sed 's/\x1b\[[0-9;]*[mGKHF]//g'
}

# Log one attempt as JSONL.
# panel.jsonl row schema (used by team/MOE panel runner):
# {ts, member_idx, provider, model, status, duration_s, bytes, error_class}
_log_attempt() {
    local role="$1" provider="$2" model="$3" status="$4" duration_s="$5" bytes="$6" title="$7"
    local workflow="${WORKFLOW_NAME:-}"
    # Hardened: include packet fields when available for full reconstructability
    printf '{"ts":"%s","workflow":"%s","run_id":"%s","workspace":"%s","goal_file":"%s","objective":"%s","role":"%s","provider":"%s","model":"%s","status":"%s","duration_s":%s,"bytes":%s,"title":"%s","artifact":"%s"}\n' \
        "$(date -u +%FT%TZ)" "$workflow" "$WF_RUN_ID" "$WF_WORKSPACE" "$WF_GOAL_FILE" "$WF_OBJECTIVE" "$role" "$provider" "$model" "$status" "$duration_s" "$bytes" "$title" "" \
        >> "$RUN_LOG"
}

# Validate output file. Echoes a status string and returns 0 if ok.
_validate() {
    local out="$1" require="$2"
    [ -f "$out" ] || { echo "missing"; return 1; }
    local sz; sz=$(stat -c %s "$out" 2>/dev/null || echo 0)
    [ "$sz" -ge "$MIN_OUTPUT_BYTES" ] || { echo "too_small($sz)"; return 1; }
    if [ -n "$require" ] && ! grep -qE "$require" "$out"; then
        echo "marker_missing"; return 1
    fi
    # Semantic hardening: reject DISPATCH/runtime failure signatures only. The old
    # check matched bare "error"/"timeout"/"rate limit", which false-positives on
    # legitimate technical prose (an explorer discussing error handling or timeouts)
    # and made run_role return non-zero on good output (swarm rc=1). Match specific
    # failure phrases that do not occur in normal answers instead.
    if grep -qiE "(AGENT_DISCONNECTED|ACP agent disconnected|connection_close|connection refused|ECONNREFUSED|429 too many requests|5[0-9][0-9] (internal server error|service unavailable|bad gateway)|free promotion ended|rate.?limit exceeded|quota exceeded|cannot apply --model|did not advertise that model)" "$out" 2>/dev/null; then
        echo "provider_failure_detected"; return 1
    fi
    # Provider error PAYLOAD returned with exit 0 (false-success trap): some adapters
    # emit an HTTP error body as the answer text and exit 0, which would otherwise be
    # counted as a successful, "diverse" member. Reject specific provider-error
    # signatures. These phrases do not occur in normal answer prose.
    if grep -qiE "(payment required|no active subscription|insufficient credits|\"status\":[[:space:]]*4[0-9][0-9]|^error: [45][0-9][0-9]([[:space:]]|$)|402 payment|subscribe to start using)" "$out" 2>/dev/null; then
        echo "provider_error_payload"; return 1
    fi
    echo "ok"
    return 0
}

# Run a single (provider, model) attempt. Writes to $out_file on success.
# Dispatches via acpx (the same path as acp_to_run_agent.sh) so the .sh workflows
# share ONE dispatch mechanism and ONE model-id convention with the ACP capability
# layer. Supported agents: claude, codex, opencode.
_run_one() {
    local provider="$1" model="$2" title="$3" prompt_file="$4" out_file="$5"

    # Provider validation — write error to out_file for _validate to catch.
    case "$provider" in
        opencode|codex|claude) ;;
        *)
            echo "ERROR: unknown provider '$provider'" > "$out_file"
            return 0
            ;;
    esac

    # Dispatch via shared primitive. No ACPX_DISPATCH_RICH — PATH B stays
    # narrow (agent_message_chunk only).  Empty session = one-shot.
    # ROLE_TIMEOUT_S = PATH B's uniform 300s cap (NOT role-based caps from A).
    acpx_dispatch "$provider" "$model" "$prompt_file" "$out_file" "$ROLE_TIMEOUT_S" ""

    return 0
}

# Validate packet allowed_paths vs safety.toml workspace denies.
# Returns 0 if safe, 1 if denied.
_check_packet_safe() {
    local workspace="${WF_WORKSPACE:-default}"

    # Check packet-level denied_paths vs allowed_paths overlap
    if [ -n "$WF_ALLOWED_PATHS" ] && [ -n "$WF_DENIED_PATHS" ]; then
        local allowed="$WF_ALLOWED_PATHS"
        local denied="$WF_DENIED_PATHS"
        local IFS=','
        for apath in $allowed; do
            for dpath in $denied; do
                apath="$(echo "$apath" | xargs)"
                dpath="$(echo "$dpath" | xargs)"
                if echo "$apath" | grep -q "^$dpath"; then
                    echo "[safety] PACKET DENIED: allowed_path '$apath' overlaps denied_path '$dpath'" >&2
                    return 1
                fi
            done
        done
    fi

    # If safety.sh is loaded, check command-level denies too
    if declare -f check_command_safe >/dev/null 2>&1; then
        local prompt_text=""
        [ -n "$WF_OBJECTIVE" ] && prompt_text="$WF_OBJECTIVE"
        [ -f "${WF_GOAL_FILE:-}" ] && prompt_text="$prompt_text $(head -c 500 "${WF_GOAL_FILE}" 2>/dev/null)"
        if [ -n "$prompt_text" ]; then
            check_command_safe "$prompt_text" "$workspace" || return $?
        fi
    fi

    return 0
}

# Public entry. Walks the role chain with validation+fallback.
run_role() {
    local role="$1" title="$2" prompt_file="$3" out_file="$4" require="${5:-}"

    # Run safety check before any agent launch
    if ! _check_packet_safe; then
        echo "[run_role] SAFETY BLOCKED: packet or workspace denies match" >&2
        return 3
    fi

    # Auto-inject a strongly-matched skill pack (skill-context emits nothing
    # below its 0.70 threshold), so workflow roles get skills without relying
    # on agents following the AGENTS.md skill-selection convention themselves.
    if command -v skill-context >/dev/null 2>&1 && [ -f "$prompt_file" ]; then
        local _skill_ctx
        _skill_ctx=$(timeout 8 skill-context "$(head -c 500 "$prompt_file")" 2>/dev/null) || _skill_ctx=""
        if [ -n "$_skill_ctx" ]; then
            local _aug_prompt="${prompt_file}.skillctx"
            { printf '%s\n\n' "$_skill_ctx"; cat "$prompt_file"; } > "$_aug_prompt" && prompt_file="$_aug_prompt"
        fi
    fi

    local chain
    chain=$(_role_chain "$role")
    if [ -z "$chain" ]; then
        echo "[run_role] ERROR: no chain for role '$role'" >&2
        return 2
    fi

    local attempt=0
    local entries=()
    mapfile -t entries <<< "$chain"
    for entry in "${entries[@]}"; do
        [ -z "$entry" ] && continue
        attempt=$((attempt + 1))
        local provider="${entry%%:*}"
        local model="${entry#*:}"

        echo "[run_role] role=$role attempt=$attempt $provider:$model" >&2
        local t0=$(date +%s)
        _run_one "$provider" "$model" "$title-a$attempt" "$prompt_file" "$out_file" || true
        local t1=$(date +%s)
        local dur=$((t1 - t0))
        local bytes=$(stat -c %s "$out_file" 2>/dev/null || echo 0)

        local vstatus
        vstatus=$(_validate "$out_file" "$require")
        local vrc=$?

        _log_attempt "$role" "$provider" "$model" "$vstatus" "$dur" "$bytes" "$title-a$attempt"

        if [ "$vrc" -eq 0 ]; then
            echo "[run_role] role=$role OK ($vstatus, ${dur}s, ${bytes}B) via $provider:$model" >&2
            return 0
        fi
        echo "[run_role] role=$role FAIL ($vstatus) on $provider:$model -- falling through" >&2
    done

    echo "[run_role] role=$role EXHAUSTED chain, no valid output" >&2
    return 1
}

# Run a single member (like _run_one but with validation and logging).
# Signature: run_member <provider> <model> <title> <prompt_file> <out_file> [readonly]
#   provider   - one of: opencode, codex, claude
#   model      - model identifier (e.g. deepseek-v4-flash)
#   title      - human-readable label for this attempt
#   prompt_file - path to prompt file
#   out_file   - path where output is written
#   readonly   - optional flag (reserved for future use)
# Returns: 0 on success, non-zero on failure.
# Appends one JSONL row to $RUN_LOG with: provider, model, status, duration_s, bytes, error_class.
run_member() {
    local provider="$1" model="$2" title="$3" prompt_file="$4" out_file="$5"
    local readonly="${6:-}"

    local t0
    t0=$(date +%s)

    # Validate provider is in the allowed enum FIRST
    case "$provider" in
        opencode|codex|claude) ;;
        *)
            echo "ERROR: unknown provider '$provider'. Allowed providers: opencode, codex, claude" >&2
            printf '{"ts":"%s","provider":"%s","model":"%s","status":"failed","duration_s":0,"bytes":0,"error_class":"invalid_provider"}\n' \
                "$(date -u +%FT%TZ)" "$provider" "$model" >> "$RUN_LOG"
            return 1
            ;;
    esac

    _run_one "$provider" "$model" "$title" "$prompt_file" "$out_file" || true
    local t1
    t1=$(date +%s)
    local dur=$((t1 - t0))
    local bytes
    bytes=$(stat -c %s "$out_file" 2>/dev/null || echo 0)

    # Validate output
    local vstatus
    vstatus=$(_validate "$out_file" "")
    local vrc=$?

    local overall_status="failed"
    [ "$vrc" -eq 0 ] && overall_status="succeeded"

    # Append ONE JSONL row to RUN_LOG per member attempt
    printf '{"ts":"%s","provider":"%s","model":"%s","status":"%s","duration_s":%s,"bytes":%s,"error_class":"%s"}\n' \
        "$(date -u +%FT%TZ)" "$provider" "$model" "$overall_status" "$dur" "$bytes" "$vstatus" \
        >> "$RUN_LOG"

    return $vrc
}

# CLI entrypoint for run_member — called by team (Python).
# Usage: bash lib/run.sh run_member_cli <provider> <model> <title> <prompt_file> <out_file> [readonly]
# Outputs: a single JSON line on stdout with {provider,model,status,duration_s,bytes,error_class}
# Returns: 0 on success, non-zero on failure
if [ "${1:-}" = "run_member_cli" ]; then
    shift
    run_member "$@"
    rc=$?
    # Output JSON row to stdout
    tail -1 "$RUN_LOG" 2>/dev/null || true
    exit $rc
fi
