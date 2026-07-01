#!/usr/bin/env bash
# recall -- search across all memory tiers
# Usage:
#   recall.sh "<query>"
#   recall.sh --tier=<cockpit|user|project-a|project-b|vault|sessions> "<query>"
#   recall.sh --semantic "<query>"
#   recall.sh --hybrid "<query>"
#   recall.sh --explain "<query>"
set -euo pipefail

# Default paths for memory roots (used by add_root below).
# These default to paths under AGENT_OS_HOME. If a workspace doesn't
# exist on this machine, add_root skips it silently.
AGENT_OS_HOME="${AGENT_OS_HOME:-$HOME/agent-os}"
COCKPIT="${COCKPIT:-$AGENT_OS_HOME}"
COCKPIT_LESSONS="${COCKPIT_LESSONS:-$AGENT_OS_HOME/lessons.md}"
COCKPIT_MEMORY="${COCKPIT_MEMORY:-$AGENT_OS_HOME/memory.md}"
USER_MEM="${USER_MEM:-$AGENT_OS_HOME/state/memory/memory.md}"
PROJECT_A="${PROJECT_A:-$AGENT_OS_HOME/workspace-project-a}"
PROJECT_B="${PROJECT_B:-$AGENT_OS_HOME/workspace-project-b}"
VAULT="${VAULT:-${VAULT_PATH:-$AGENT_OS_HOME/vault}}"

log_usage() {
  local f="$HOME/.cache/agent-workflows/skill-usage.jsonl"
  mkdir -p "$(dirname "$f")" 2>/dev/null || return 0
  local agent="${AI_AGENT:+${AI_AGENT%%_*}}"
  printf '{"timestamp":"%s","skill_id":"%s","agent":"%s","workspace":"%s","success":%s,"duration_s":0,"notes":"%s"}\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "${agent:-cli}" "$PWD" "$2" "$3" >> "$f" 2>/dev/null || true
}

_realpath() {
  local f="$1"
  if command -v realpath >/dev/null 2>&1; then
    realpath "$f"
  else
    echo "$(cd "$(dirname "$f")" && pwd)/$(basename "$f")"
  fi
}
SCRIPT_DIR="$(dirname "$(_realpath "${BASH_SOURCE[0]}")")"

# Source config from standard location (created by install.sh)
if [ -f "${HOME}/.config/agent-os/config.env" ]; then
  source "${HOME}/.config/agent-os/config.env"
elif [ -f "${SCRIPT_DIR}/../config.env" ]; then
  source "${SCRIPT_DIR}/../config.env"
else
  echo "  WARNING: config.env not found at ~/.config/agent-os/config.env"
  echo "  Run install.sh first or create the file manually."
fi

TIER=""
SEMANTIC=0
HYBRID=0
EXPLAIN=0
QUERY=""
LOG_QUERY=""
TMPFILE=""

on_exit() {
  local rc=$?
  if [[ -n "$TMPFILE" ]]; then
    rm -f "$TMPFILE"
  fi
  [[ -n "$LOG_QUERY" ]] || return "$rc"
  local success=0
  if [[ "$rc" -eq 0 ]]; then
    success=1
  fi
  log_usage "recall" "$success" "query:${LOG_QUERY}"
  return "$rc"
}

for arg in "$@"; do
  case "$arg" in
    --tier=*)    TIER="${arg#*=}" ;;
    --semantic)  SEMANTIC=1 ;;
    --hybrid)    HYBRID=1 ;;
    --explain)   EXPLAIN=1 ;;
    --help|-h)
      grep -E '^# ' "$0" | sed 's/^# //'; exit 0 ;;
    *)           QUERY="${QUERY:+$QUERY }$arg" ;;
  esac
done

if [[ -z "$QUERY" ]]; then
  echo "Usage: recall '<query>' [--tier=<name>] [--semantic|--hybrid|--explain]" >&2
  exit 2
fi

LOG_QUERY=$(printf '%s' "${QUERY:0:60}" | tr -d '"')
trap on_exit EXIT

# Ã¢ÂÂÃ¢ÂÂ Helper: reliability assignment Ã¢ÂÂÃ¢ÂÂ
assign_reliability() {
  local path="$1"
  if [[ "$path" == *agent-os/* ]] || [[ "$path" == */lessons.md ]] || [[ "$path" == */memory.md ]]; then
    echo "high"
  elif [[ "$path" == */project-a/* ]] || [[ "$path" == */project-b/* ]] || [[ "$path" == */vault/* ]]; then
    echo "medium"
  elif [[ "$path" == *external* ]] || [[ "$path" == *import* ]]; then
    echo "low"
  else
    echo "unknown"
  fi
}

# Ã¢ÂÂÃ¢ÂÂ Helper: freshness from file mod date Ã¢ÂÂÃ¢ÂÂ
get_freshness() {
  local path="$1"
  if [[ -f "$path" ]]; then
    stat -c '%y' "$path" 2>/dev/null | cut -d' ' -f1 || echo "unknown"
  else
    echo "unknown"
  fi
}

# Ã¢ÂÂÃ¢ÂÂ Helper: format explain line from grep match Ã¢ÂÂÃ¢ÂÂ
format_explain_grep() {
  local match_line="$1"
  local label="$2"
  local file_path=""
  local lineno=""
  local text=""

  file_path=$(echo "$match_line" | sed 's/^\([^:]*\):[0-9]*:.*$/\1/')
  lineno=$(echo "$match_line" | sed 's/^[^:]*:\([0-9]*\):.*$/\1/')
  text=$(echo "$match_line" | sed 's/^[^:]*:[0-9]*://')

  local tier="$label"
  local freshness="unknown"
  local reliability="unknown"
  if [[ -n "$file_path" ]]; then
    freshness=$(get_freshness "$file_path")
    reliability=$(assign_reliability "$file_path")
  fi
  echo "[TIER:${tier}] [METHOD:fts5] [SCORE:1.0] [FRESHNESS:${freshness}] [RELIABILITY:${reliability}] line ${lineno}: ${text}"
}

if [[ $HYBRID -eq 1 ]]; then
  MEMORY_LT="$AGENT_OS_HOME/bin/memory-lt"
  PY="$COCKPIT/.venv/bin/python"
  [[ -x "$PY" ]] || PY="python3"
  "$MEMORY_LT" search-hybrid --text "$QUERY" --limit 5 \
    | "$PY" -c '
import json, sys
d = json.load(sys.stdin)
if not d.get("ok", False):
    print("[recall] hybrid search failed: {}".format(d.get("error","?")), file=sys.stderr)
    sys.exit(1)
hits = d.get("results", [])
c = d.get("counts", {})
v = c.get("vector", 0); f = c.get("fts", 0); g = c.get("graph", 0)
q = d.get("query", "?")
print("-- recall hybrid: {} merged hits (vector={} fts={} graph={}) --".format(len(hits), v, f, g))
if not hits:
    print("No hybrid matches for {!r}.".format(q))
    sys.exit(0)
for h in hits:
    tiers = ",".join(sorted({t["tier"] for t in h.get("tiers",[])}))
    rrf = h.get("rrf_score", 0.0)
    src = h.get("source_path") or "?"
    summary = " ".join((h.get("summary") or "").split())[:140]
    print("[{}] [rrf={:.5f}] {} :: {}".format(tiers, rrf, src, summary))
'
  exit 0
fi

if [[ $SEMANTIC -eq 1 ]]; then
  PY="$COCKPIT/.venv/bin/python"
  MEMORY_LT="$AGENT_OS_HOME/bin/memory-lt"
  [[ -x "$PY" ]] || PY="python3"
  if [[ -n "${PINECONE_API_KEY:-}" ]]; then
    if "$MEMORY_LT" search-vector --namespace all --text "$QUERY" --limit 10 \
      | "$PY" -c '
import json
import sys
data = json.load(sys.stdin)
if not data.get("ok", False):
    err = data.get("error", "unknown error")
    print("[recall] semantic search failed: {}".format(err), file=sys.stderr)
    sys.exit(1)
hits = data.get("results", [])
if not hits:
    query = data.get("query", "query")
    print("No semantic matches for {!r}.".format(query))
    sys.exit(0)
print("-- recall semantic: {} hits, top {} --".format(len(hits), min(len(hits), 10)))
for hit in hits[:10]:
    namespace = hit.get("namespace", "?")
    score = float(hit.get("score", 0) or 0)
    source = hit.get("source_path") or hit.get("path") or "?"
    summary = " ".join((hit.get("summary") or "").split())
    print("[{}] [{:.3f}] {} :: {}".format(namespace, score, source, summary))
for err in data.get("namespace_errors", []):
    ns = err.get("namespace", "?")
    msg = err.get("error", "unknown error")
    print("[recall] namespace warning ({}): {}".format(ns, msg), file=sys.stderr)
'
    then
      exit 0
    else
      echo "[recall] semantic mode degraded; falling back to grep." >&2
    fi
  else
    echo "[recall] PINECONE_API_KEY not set; falling back to grep." >&2
  fi
fi

# Ã¢ÂÂÃ¢ÂÂ Shared setup for file + cass search Ã¢ÂÂÃ¢ÂÂ
HITS_TOTAL=0
SEARCHED=0
TMPFILE="$(mktemp)"

# Ã¢ÂÂÃ¢ÂÂ Cass session search (fail-open) Ã¢ÂÂÃ¢ÂÂ
PY="${COCKPIT:-$AGENT_OS_HOME/agent-os}/.venv/bin/python"
[[ -x "$PY" ]] || PY="python3"
CASS="$AGENT_OS_HOME/.local/bin/cass"
DID_CASS=0
if [[ "$TIER" == "sessions" ]] || [[ -z "$TIER" ]]; then
  if [[ -x "$CASS" ]]; then
    TMP_BEFORE=$(wc -l < "$TMPFILE" | tr -d ' ')
    "$CASS" search "$QUERY" --robot-format compact --limit 5 2>/dev/null \
      | "$PY" -c '
import json, sys
try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)
hits = data.get("hits", [])
if not hits:
    sys.exit(0)
for h in hits:
    sp = h.get("source_path", "?")
    ln = h.get("line_number", 0)
    sn = " ".join((h.get("snippet") or "").split())[:120]
    sc = float(h.get("score", 0) or 0)
    ts = h.get("created_at")
    if ts:
        import datetime
        try:
            fs = datetime.datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d")
        except Exception:
            fs = "unknown"
    else:
        fs = "unknown"
    print("[TIER:sessions] [METHOD:cass] [SCORE:{:.4f}] [FRESHNESS:{}] [RELIABILITY:medium] {}:{} {}".format(sc, fs, sp, ln, sn))
' >> "$TMPFILE" 2>/dev/null
    TMP_AFTER=$(wc -l < "$TMPFILE" | tr -d ' ')
    if [[ "$TMP_AFTER" -gt "$TMP_BEFORE" ]]; then
      DID_CASS=1
      SEARCHED=1
    fi
  fi
fi

declare -a ROOTS=() LABELS=()

add_root() {
  local label="$1" path="$2"
  if [[ -e "$path" ]]; then
    ROOTS+=("$path"); LABELS+=("$label")
  fi
}

case "$TIER" in
  "")
    add_root "cockpit"   "$COCKPIT_LESSONS"
    add_root "cockpit"   "$COCKPIT_MEMORY"
    add_root "user"      "$USER_MEM"
    add_root "project-b"  "$PROJECT_B/docs/MEMORY.md"
    add_root "project-b"  "$PROJECT_B/docs/LESSONS.md"
    add_root "project-a"  "$PROJECT_A/docs/MEMORY.md"
    add_root "project-a"  "$PROJECT_A/docs/LESSONS.md"
    add_root "vault"     "$VAULT/self/memory.md"
    add_root "vault"     "$VAULT/docs/vault-os/LESSONS.md"
    add_root "vault"     "$VAULT/findings"
    add_root "vault"     "$VAULT/insights"
    ;;
  cockpit) add_root cockpit "$COCKPIT_LESSONS"; add_root cockpit "$COCKPIT_MEMORY" ;;
  user)    add_root user "$USER_MEM" ;;
  project-b)  add_root project-b "$PROJECT_B/docs/MEMORY.md"; add_root project-b "$PROJECT_B/docs/LESSONS.md" ;;
  project-a)  add_root project-a "$PROJECT_A/docs/MEMORY.md"; add_root project-a "$PROJECT_A/docs/LESSONS.md" ;;
  vault)   add_root vault "$VAULT/self/memory.md"; add_root vault "$VAULT/findings"; add_root vault "$VAULT/insights" ;;
  sessions) ;;  # cass-only tier, handled above
  *)       echo "Unknown tier: $TIER" >&2; exit 2 ;;
esac

if [[ ${#ROOTS[@]} -gt 0 ]]; then
for i in "${!ROOTS[@]}"; do
  label="${LABELS[$i]}"; root="${ROOTS[$i]}"
  if [[ $EXPLAIN -eq 1 ]]; then
    grep -nH --color=never -i -F -- "$QUERY" "$root" 2>/dev/null \
      | sed "s|^|[$label] |" >> "$TMPFILE" || true
  else
    if command -v rg >/dev/null 2>&1; then
      rg --no-heading --line-number --color=never --max-count=10 -i -F -- "$QUERY" "$root" 2>/dev/null \
        | sed "s|^|[$label] |" >> "$TMPFILE" || true
    else
      grep -rn --color=never -i -F -- "$QUERY" "$root" 2>/dev/null \
        | sed "s|^|[$label] |" >> "$TMPFILE" || true
    fi
  fi
done
fi

HITS_TOTAL=$(wc -l < "$TMPFILE" | tr -d ' ')
# Exit early only if we have zero results AND cass didn't find anything
if [[ "$HITS_TOTAL" -eq 0 ]] && [[ "$SEARCHED" -eq 0 ]]; then
  echo "No matches for '$QUERY'${TIER:+ in tier=$TIER}."
  exit 0
fi

TIER_SUFFIX=""
if [[ -n "$TIER" ]]; then
  TIER_SUFFIX=" (tier=$TIER)"
fi

if [[ $EXPLAIN -eq 1 ]]; then
  echo "-- recall explain: $HITS_TOTAL hits${TIER_SUFFIX}, top 20 --"
  head -n 20 "$TMPFILE" | while IFS= read -r line; do
    label=$(echo "$line" | sed 's/^\[\([^]]*\)\].*/\1/')
    rest=$(echo "$line" | sed 's/^\[[^]]*\] //')
    format_explain_grep "$rest" "$label"
  done
  if [[ "$HITS_TOTAL" -gt 20 ]]; then
    echo "-- (showing 20 of $HITS_TOTAL, narrow the query or use --tier) --"
  fi
else
  echo "-- recall: $HITS_TOTAL hits${TIER_SUFFIX}, top 20 --"
  head -n 20 "$TMPFILE"
  if [[ "$HITS_TOTAL" -gt 20 ]]; then
    echo "-- (showing 20 of $HITS_TOTAL, narrow the query or use --tier) --"
  fi
fi
