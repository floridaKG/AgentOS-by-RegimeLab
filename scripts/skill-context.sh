#!/usr/bin/env bash
# skill-context — rank a task text against the skills registry and, when the
# top hit is strong, emit its packed actionable section for prompt injection.
#
# Used by deterministic dispatch paths (agent-workflow lib/run.sh,
# sidecar) so skill adoption doesn't depend on agents remembering the
# AGENTS.md skill-selection convention.
#
# Threshold is stricter (0.60) than the manual-load rule (0.50): skill-rank is
# lexical and auto-injecting a wrong skill is worse than injecting nothing.
# Calibrated 2026-06-10: realistic long prompts dilute scores (a correct
# pinecone-search match scored 0.64; a wrong upward-handoff match 0.54).
# Emits nothing (exit 0) below threshold or on any error.
#
# Usage: skill-context "<task text>" [budget_bytes]
set -uo pipefail

TASK="${1:-}"
BUDGET="${2:-3000}"
THRESHOLD="${SKILL_CONTEXT_THRESHOLD:-0.60}"
[ -z "$TASK" ] && exit 0

RANK_JSON=$(skill-rank "$TASK" --top 1 --json 2>/dev/null) || exit 0

read -r NAME SCORE_OK < <(printf '%s' "$RANK_JSON" | python3 -c '
import json, sys
try:
    top = json.load(sys.stdin)[0]
    print(top["name"], 1 if top["score"] >= float(sys.argv[1]) else 0)
except Exception:
    print("", 0)
' "$THRESHOLD" 2>/dev/null || true)
[ -z "${NAME:-}" ] || [ "${SCORE_OK:-0}" != "1" ] && exit 0

PACK=$(skill-pack "$NAME" --budget "$BUDGET" 2>/dev/null) || exit 0
[ -z "$PACK" ] && exit 0

printf '<relevant_skill name="%s" note="auto-injected by skill-context; matched the task text">\n%s\n</relevant_skill>\n' "$NAME" "$PACK"
