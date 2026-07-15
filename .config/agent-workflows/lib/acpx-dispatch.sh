#!/usr/bin/env bash
# acpx-dispatch.sh — shared acpx primitive for ACP dispatch.
[ -n "${ACPX_DISPATCH_LOADED:-}" ] && return 0
ACPX_DISPATCH_LOADED=1
# Source this file. Provides:
#   acpx_dispatch <provider> <model> <prompt_file> <raw_out> <timeout_s> [session_name]
#   acpx_timeout_for_role <role>
#
# Exit codes from acpx_dispatch:
#   0  = produced output (raw_out has agent's reply text)
#   2  = provider not handled by acpx (caller may provide another adapter)
#   >0 = dispatch failed (acpx error, timeout)
#
# Artifacts written per dispatch:
#   <raw_out>      — assembled agent text (parsed from NDJSON)
#   <raw_out>.err  — acpx stderr (provider errors, diagnostic output).
#                    PATH A's classifier (acp_output_validate.py) reads this
#                    to detect false-success / provider failures.  Callers
#                    that don't need it can discard it themselves.
#
# Environment:
#   ACPX_DISPATCH_RICH  — set to 1 to enable tool_call_update merge + event logging
#                         + raw NDJSON archive (default: 0 = narrow, agent_message_chunk only)
#                         Critical no-regression gate — see acp-dispatch-unification spec.
#   ACPX_DISPATCH_LOCK_DIR — lock directory (default: $HOME/.local/state/agent-os/locks)
#   ACPX_DISPATCH_TMP_DIR  — temp dir; a .tmp/ subdir is created under it
#                            (default: $HOME/.local/state/agent-os/acp)
#   ACPX_DISPATCH_PROBE_TTL_S — model-probe cache TTL in seconds (default: 600)

ACPX_DISPATCH_LOCK_DIR="${ACPX_DISPATCH_LOCK_DIR:-$HOME/.local/state/agent-os/locks}"
ACPX_DISPATCH_TMP_DIR="${ACPX_DISPATCH_TMP_DIR:-$HOME/.local/state/agent-os/acp}"

# ── acpx_dispatch ────────────────────────────────────────────────────────────
# Dispatch a single agent via acpx. Caller-parameterized: timeout and rich-parse
# are passed/gated so neither path's behavior regresses.
acpx_dispatch() {
    local provider="$1"
    local model="$2"
    local prompt_file="$3"
    local raw_out="$4"
    local timeout_s="$5"
    local session_name="${6:-}"
    local agent=""

    # ── Provider → agent mapping ──────────────────────────────────────────
    agent=$(_acpx_agent_for_provider "$provider") || return 2

    echo "ACP_ADAPTER: calling acpx $agent exec (provider=$provider, requested_model=${model:-default})" >&2

    # ── Build base acpx args ──────────────────────────────────────────────
    # Both paths pass --format json --approve-all. Ported from PATH A ~line 127,
    # PATH B ~line 103.
    local args=(--format json --approve-all)

    # ── Model selection ────────────────────────────────────────────────────
    # acp-flag agents (claude/codex): catalog probe before passing --model.
    #   Ported from PATH A ~line 131-143 — safer than PATH B's blind pass.
    #   The probe validates the model is advertised, falls back to agent default
    #   on mismatch, logs warnings for operator awareness.
    # pi: --model only for opencode-go/* session model ids.
    # omp: startup model is passed through OMP_ACP_MODEL; its native ACP
    # server lacks session/set_model, so the wrapper applies it before spawn.
    # opencode: config-only, no --model flag.
    # model_to_apply = the validated model id (empty → use agent default).
    # HOW it is applied depends on session vs one-shot (see invocation below):
    #   one-shot exec  → global `--model <id>` flag (works)
    #   named session  → `acpx <agent> set model <id> -s <name>` — because the
    #     global `--model` flag with `prompt -s` is LOSSY: it spawns a NEW
    #     underlying session instead of resuming the named one (verified live
    #     2026-06-17). Every agent supports session-level `set model`.
    local model_to_apply=""
    if [ -n "$model" ]; then
        case "$provider" in
            claude|codex|cline|droid|grok)
                # Catalog probe: validate model is advertised before applying it.
                # acpx emits the catalog as JSON ("availableModels":[{"modelId":...}]),
                # NOT "Available models:" — parse modelId entries (fixed 2026-06-17;
                # the old grep never matched, so validation silently no-op'd).
                local advertised
                advertised=$(timeout 45 acpx --model __probe__ "$agent" exec "probe" 2>&1 || true)
                if ! printf '%s' "$advertised" | grep -qE 'availableModels|"modelId"'; then
                    if [ "${ACPX_STRICT_MODEL:-0}" = "1" ]; then
                        echo "acpx_dispatch: ERROR model probe inconclusive for $agent; refusing unverified model '$model'" >&2
                        return 1
                    fi
                    echo "acpx_dispatch: model probe inconclusive for $agent; applying '$model' best-effort" >&2
                    model_to_apply="$model"
                elif printf '%s' "$advertised" | grep -qF "\"modelId\":\"${model}\""; then
                    model_to_apply="$model"
                else
                    echo "acpx_dispatch: ERROR model '$model' not advertised by $agent; refusing silent default substitution" >&2
                    return 1
                fi
                ;;
            pi)
                # Pi accepts provider-qualified ACP model ids for every
                # configured provider. Bare ids are ambiguous and must fail
                # instead of silently running Pi's default model.
                if [[ "$model" == */* ]]; then
                    model_to_apply="$model"
                else
                    echo "acpx_dispatch: ERROR Pi model '$model' is not provider-qualified; use provider/model" >&2
                    return 1
                fi
                ;;
            omp)
                # omp-acp-wrapper consumes this at child-process startup. Do
                # not pass --model to acpx: OMP's native server does not expose
                # the generic ACP model extension.
                model_to_apply="$model"
                ;;
            # opencode: config-only, no model flag
        esac
    fi

    # ── Temp file for raw NDJSON output ───────────────────────────────────
    local tmp_dir="${ACPX_DISPATCH_TMP_DIR}/.tmp"
    mkdir -p "$tmp_dir" || return 1
    local raw_ndjson
    raw_ndjson=$(mktemp "$tmp_dir/acpx_dispatch_XXXXXX.ndjson") || return 1

    # ── Build acpx command ────────────────────────────────────────────────
    # Named session (persistent, set model) vs one-shot exec (--model flag).
    if [ -n "$session_name" ]; then
        # Ensure named session exists before using it
        acpx "$agent" sessions show "$session_name" >/dev/null 2>&1 || \
            acpx "$agent" sessions new --name "$session_name" >/dev/null 2>&1
        # Apply the model to the session itself (NOT via --model — see note above).
        if [ -n "$model_to_apply" ] && [ "$provider" != "omp" ]; then
            acpx "$agent" set model "$model_to_apply" -s "$session_name" >/dev/null 2>&1 \
                || echo "acpx_dispatch: WARN could not set model '$model_to_apply' on session '$session_name'" >&2
        fi
        args+=("$agent" "prompt" "-s" "$session_name")
    else
        # One-shot: the global --model flag works with exec.
        [ -n "$model_to_apply" ] && [ "$provider" != "omp" ] && args=(--model "$model_to_apply" "${args[@]}")
        args+=("$agent" "exec")
    fi
    args+=(-f "$prompt_file")

    # ── Execute with opencode concurrency lock + retry ─────────────────────
    # opencode sessions collide (AGENT_DISCONNECTED) under parallel workflows.
    # Serialize via flock on opencode.lock. Retry transient disconnects x3
    # with 1-3s jitter.
    # Ported from PATH B ~line 112-120. PATH A lacked this; shared lib gives
    # both paths the benefit.
    local lock_dir="${ACPX_DISPATCH_LOCK_DIR}"
    mkdir -p "$lock_dir" || true
    local attempt=0 max_attempts=3
    # Capture acpx's real exit code so callers can detect timeout (124/137) and
    # acpx failures. The subshell's exit status IS the acpx/timeout status; we
    # lift it out via `|| acpx_rc=$?` rather than swallowing it with `|| true`.
    local acpx_rc=0

    while [ "$attempt" -lt "$max_attempts" ]; do
        attempt=$((attempt + 1))
        acpx_rc=0
        (
            if [ "$provider" = "opencode" ]; then
                flock 9
            fi
            # AI_AGENT export for codegraph/rtk tool attribution wrappers.
            # Both paths export this before the acpx call.
            # Ported from PATH A ~line 155, PATH B ~line 117.
            OMP_ACP_MODEL="${model_to_apply:-}" AI_AGENT="$agent" timeout -k 30 "$timeout_s" \
                acpx "${args[@]}" > "$raw_ndjson" 2>"${raw_out}.err"
        ) 9>"$lock_dir/opencode.lock" || acpx_rc=$?

        # Retry only on AGENT_DISCONNECTED with no usable output
        # Ported from PATH B ~line 119-120.
        if grep -q 'AGENT_DISCONNECTED' "$raw_ndjson" 2>/dev/null && \
           ! grep -q 'agent_message_chunk' "$raw_ndjson" 2>/dev/null; then
            sleep $(( (RANDOM % 3) + 1 ))
            continue
        fi
        break
    done

    # ═══════════════════════════════════════════════════════════════════════
    # OUTPUT PARSING
    # ═══════════════════════════════════════════════════════════════════════
    #
    # Narrow (always on): extract agent_message_chunk text parts.
    #   Ported from PATH B ~line 122-131 (the minimal parsing both paths
    #   must share). Single python3 invocation — not a bash while-read loop.
    #
    # Rich (opt-in via ACPX_DISPATCH_RICH=1, default OFF):
    #   - tool_call_update merge (fallback for tool-heavy agents)
    #   - Event/usage logging (tool_call, usage_update, stopReason)
    #   - Raw NDJSON archive to archive/adapter-temp/
    #   Ported from PATH A ~line 168-220.
    #   This is the CRITICAL NO-REGRESSION GATE from the adversarial review:
    #   PATH B's _validate() greps for AGENT_DISCONNECTED/connection refused/
    #   quota exceeded patterns. If tool_call_update text (which routinely
    #   carries those strings) leaked into PATH B's output, _validate would
    #   false-reject successful dispatches. Therefore the merge + archive +
    #   event logging are opt-in only, default OFF.

    # ── Narrow parse: agent_message_chunk (always on) ─────────────────────
    python3 -c '
import json, sys

def extract(raw_path, out_path):
    parts = []
    try:
        with open(raw_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    o = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if o.get("method") == "session/update":
                    u = o.get("params", {}).get("update", {})
                    if u.get("sessionUpdate") == "agent_message_chunk":
                        c = u.get("content", {})
                        if c.get("type") == "text":
                            parts.append(c.get("text", ""))
        with open(out_path, "w") as f:
            f.write("".join(parts))
    except FileNotFoundError:
        with open(out_path, "w") as f:
            f.write("")
    except Exception:
        with open(out_path, "w") as f:
            f.write("")

if __name__ == "__main__":
    extract(sys.argv[1], sys.argv[2])
' "$raw_ndjson" "$raw_out" 2>/dev/null || true

    # ── Rich parse: opt-in via ACPX_DISPATCH_RICH=1 ───────────────────────
    if [ "${ACPX_DISPATCH_RICH:-0}" = "1" ]; then
        # tool_call_update merge: collect text from tool result content blocks
        # as fallback when agent_message_chunk is insufficient.
        # Ported from PATH A ~line 168-178.
        local out_size
        out_size=$(stat -c %s "$raw_out" 2>/dev/null || echo 0)
        if [ "$out_size" -lt 10 ]; then
            python3 -c '
import json, sys

def merge_tool_content(raw_path, out_path):
    parts = []
    try:
        with open(raw_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    o = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if o.get("method") == "session/update":
                    u = o.get("params", {}).get("update", {})
                    if u.get("sessionUpdate") == "tool_call_update":
                        for block in u.get("content", []):
                            c = block.get("content", {})
                            if c.get("type") == "text":
                                t = c.get("text", "")
                                if t.strip():
                                    parts.append(t)
        existing = ""
        try:
            with open(out_path) as f:
                existing = f.read()
        except FileNotFoundError:
            pass
        with open(out_path, "w") as f:
            f.write(existing + "".join(parts))
    except Exception:
        pass

if __name__ == "__main__":
    merge_tool_content(sys.argv[1], sys.argv[2])
' "$raw_ndjson" "$raw_out" 2>/dev/null || true
        fi

        # Archive raw NDJSON for audit trail
        # Ported from PATH A ~line 216-220.
        local archive_dir="$HOME/.local/state/agent-os/acp/archive/adapter-temp"
        mkdir -p "$archive_dir" 2>/dev/null || true
        cp -a "$raw_ndjson" "$archive_dir/$(basename "$raw_ndjson").$(date +%Y%m%d%H%M%S)" 2>/dev/null || true

        # Event/usage logging to stderr (tool_call, usage_update, stopReason)
        # Ported from PATH A ~line 193-214.
        python3 -c '
import json, sys

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        o = json.loads(line)
    except json.JSONDecodeError:
        continue
    if o.get("method") == "session/update":
        u = o.get("params", {}).get("update", {})
        st = u.get("sessionUpdate", "")
        if st == "tool_call":
            print("  [tool_call] %s (%s)" % (u.get("title","?"), u.get("kind","?")), file=sys.stderr)
        elif st == "usage_update":
            used = u.get("used", 0)
            size = u.get("size", 0)
            print("  [usage] %s/%s tokens" % (used, size), file=sys.stderr)
    elif o.get("method") == "session/prompt":
        result = o.get("result", {})
        if result.get("stopReason"):
            print("  [stop] %s" % result["stopReason"], file=sys.stderr)
' < "$raw_ndjson" 2>/dev/null || true
    fi

    # Archive raw NDJSON for orchestrator/reaper cleanup.
    # NEVER use rm — AGENTS.md non-negotiable.  Rename into archive/ so the
    # reaper handles lifecycle; callers that need the raw stream can also read
    # it from the archive location.
    local archive_dir="$HOME/.local/state/agent-os/acp/archive/dispatch-raw"
    mkdir -p "$archive_dir" 2>/dev/null || true
    mv -f "$raw_ndjson" "$archive_dir/$(basename "$raw_ndjson")" 2>/dev/null || true

    # Propagate acpx's real exit code (124 timeout / 137 SIGKILL / acpx errors)
    # so PATH A's timeout checks + classifier see the truth. 0 = success.
    return "$acpx_rc"
}

_acpx_agent_for_provider() {
    case "$1" in
        opencode|codex|claude|droid|pi|omp|cursor|cline|grok) printf '%s\n' "$1" ;;
        *) return 2 ;;
    esac
}

# ── acpx_timeout_for_role ────────────────────────────────────────────────────
# Print role-capped timeout in seconds.
# Ported from PATH A ~line 48-55.
# Honor ACP_WORKER_TIMEOUT override when set and valid.
acpx_timeout_for_role() {
    local role="$1"
    local timeout=300  # default

    case "$role" in
        executor|explorer|reviewer|code_reviewer|pi)
            timeout=180 ;;
        escalation|hard_escalation)
            timeout=1800 ;;
    esac

    # ACP_WORKER_TIMEOUT override always wins when set externally
    if [ -n "${ACP_WORKER_TIMEOUT:-}" ] && [[ "$ACP_WORKER_TIMEOUT" =~ ^[0-9]+$ ]]; then
        timeout="$ACP_WORKER_TIMEOUT"
    fi

    echo "$timeout"
}
