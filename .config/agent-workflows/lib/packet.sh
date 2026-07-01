#!/usr/bin/env bash
# Workflow packet helpers. Source this file.
# Provides: load_packet <json_path>, emit_packet_scope

load_packet() {
    local pkt="$1"
    [ -f "$pkt" ] && [[ "$pkt" == *.json ]] || return 1
    eval "$(python3 -c "
import json,sys,shlex
p=json.load(open(sys.argv[1]))
for k in ['workflow_name','run_id','workspace','goal_file','objective','scope','boundaries','input_files','output_files','success_criteria','ownership','prompt_hash']:
    v = p.get(k,'')
    print(f'WF_{k.upper()}={shlex.quote(str(v))}')
" "$pkt")"
    export WORKFLOW_NAME="$WF_WORKFLOW_NAME"
    export WF_RUN_ID="$WF_RUN_ID"
    export WF_WORKSPACE="$WF_WORKSPACE"
    export WF_GOAL_FILE="$WF_GOAL_FILE"
    export WF_OBJECTIVE="$WF_OBJECTIVE"
    export WF_SCOPE="$WF_SCOPE"
    export WF_BOUNDARIES="$WF_BOUNDARIES"
    export WF_INPUT_FILES="$WF_INPUT_FILES"
    export WF_OUTPUT_FILES="$WF_OUTPUT_FILES"
    export WF_SUCCESS_CRITERIA="$WF_SUCCESS_CRITERIA"
    export WF_OWNERSHIP="$WF_OWNERSHIP"
    export WF_PROMPT_HASH="$WF_PROMPT_HASH"
    return 0
}

emit_packet_scope() {
    if [ -n "${WF_OBJECTIVE:-}" ]; then
        printf '\n--- Packet scope (do not echo back) ---\n'
        printf 'Objective: %s\n' "$WF_OBJECTIVE"
        [ -n "$WF_SCOPE" ] && printf 'Scope: %s\n' "$WF_SCOPE"
        [ -n "$WF_BOUNDARIES" ] && printf 'Boundaries: %s\n' "$WF_BOUNDARIES"
        [ -n "$WF_SUCCESS_CRITERIA" ] && printf 'Success criteria: %s\n' "$WF_SUCCESS_CRITERIA"
    fi

    # Append memory context from Pinecone agent-vault (non-fatal)
    if command -v memory-lt &>/dev/null && [ -n "${WF_OBJECTIVE:-}" ]; then
        local mem_json
        # Search both the vault-content namespace (default) and schema namespaces
        mem_json=$(timeout 8 memory-lt search-vector \
            --namespace all --text "$WF_OBJECTIVE" --limit 5 2>/dev/null || true)
        if [ -n "$mem_json" ]; then
            local mem_text
            mem_text=$(echo "$mem_json" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    if not data.get('ok'):
        sys.exit(0)
    results = data.get('results', [])
    for r in results[:3]:
        s = r.get('summary', '')[:300]
        ns = r.get('namespace', '?')
        if s:
            print(f'  [{ns}] {s}')
except:
    pass
" 2>/dev/null || true)
            if [ -n "$mem_text" ]; then
                printf '\n--- Memory context (Pinecone agent-vault) ---\n'
                printf '%s\n' "$mem_text"
            fi
        fi
    fi
}
