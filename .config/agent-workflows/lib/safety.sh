#!/usr/bin/env bash
# Safety gate for destructive commands.
# Source this file. Provides: check_command_safe <cmd> [workspace]
# Returns 0 = safe to proceed, 1 = denied, 2 = requires confirmation

SAFETY_CONFIG="${SAFETY_CONFIG:-$HOME/.config/agent-workflows/safety.toml}"

check_command_safe() {
    local cmd="$1" workspace="${2:-default}"

    [ -f "$SAFETY_CONFIG" ] || return 0

    # Check workspace deny list first (hard block)
    local ws_denies
    ws_denies=$(awk -v ws="$workspace" '
        $0 ~ "^\\[workspace\\."ws"\\]" { in_ws=1; next }
        in_ws && /^\[/ { in_ws=0 }
        in_ws && /^deny/ { collecting=1 }
        collecting { match($0, /"([^"]+)"/, a); if (a[1]) print a[1] }
        collecting && /\]/ { collecting=0 }
    ' "$SAFETY_CONFIG")

    while IFS= read -r pattern; do
        [ -z "$pattern" ] && continue
        if echo "$cmd" | grep -qF "$pattern"; then
            echo "[safety] DENIED: '$pattern' matched in workspace '$workspace'" >&2
            if command -v get-smarter >/dev/null 2>&1; then
                get-smarter log "safety denied: $pattern in cmd: ${cmd:0:80}" \
                    --workspace cockpit --severity M --agent harness --task safety-gate
            fi
            return 1
        fi
    done <<< "$ws_denies"

    # Check default require_confirm list
    local confirms
    confirms=$(awk '
        /^\[default\]/ { in_default=1; next }
        in_default && /^\[/ { in_default=0 }
        in_default && /^require_confirm/ { collecting=1 }
        collecting { match($0, /"([^"]+)"/, a); if (a[1]) print a[1] }
        collecting && /\]/ { collecting=0 }
    ' "$SAFETY_CONFIG")

    while IFS= read -r pattern; do
        [ -z "$pattern" ] && continue
        if echo "$cmd" | grep -qF "$pattern"; then
            echo "[safety] REQUIRES CONFIRMATION: '$pattern' matched" >&2
            return 2
        fi
    done <<< "$confirms"

    return 0
}
