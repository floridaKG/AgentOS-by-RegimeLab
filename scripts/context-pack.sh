#!/usr/bin/env bash
# context-pack — bounded context bundle for handoffs and takeover work
# Usage:
#   context-pack.sh "<query>" [--budget=<bytes>] [--tiers=<tier1,tier2>]
set -euo pipefail

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

QUERY=""
BUDGET=8000
TIERS_FILTER=""

for arg in "$@"; do
  case "$arg" in
    --budget=*)  BUDGET="${arg#*=}" ;;
    --tiers=*)   TIERS_FILTER="${arg#*=}" ;;
    --help|-h)
      echo "Usage: context-pack.sh '<query>' [--budget=<bytes>] [--tiers=<tier1,tier2>]"
      echo "  Default budget: 8000 bytes"
      echo "  Available tiers: short-term, cockpit, workspace-project-a, workspace-project-b, workspace-vault, vector"
      exit 0 ;;
    *)           QUERY="${QUERY:+$QUERY }$arg" ;;
  esac
done

if [[ -z "$QUERY" ]]; then
  echo "Usage: context-pack.sh '<query>' [--budget=<bytes>] [--tiers=<tier1,tier2>]" >&2
  exit 2
fi

# ── Collect all results with metadata ───────────────────────────
RESULTS_FILE="$(mktemp)"

# Check if a tier is in the allowed filter
tier_allowed() {
  local tier="$1"
  if [[ -z "$TIERS_FILTER" ]]; then
    return 0
  fi
  echo "$TIERS_FILTER" | tr ',' '\n' | grep -q "^${tier}$"
}

# ── Query short-term (FTS5) ────────────────────────────────────
if tier_allowed "short-term"; then
  MEMORY_ST="$AGENT_OS_HOME/bin/memory-st"
  if [[ -x "$MEMORY_ST" ]]; then
    PY="$COCKPIT/.venv/bin/python"
    [[ -x "$PY" ]] || PY="python3"
    "$MEMORY_ST" query --text "$QUERY" --limit 10 2>/dev/null \
      | "$PY" -c '
import json, sys
data = json.load(sys.stdin)
for row in data.get("results", []):
    summary = (row.get("summary") or "").strip()
    source = row.get("source_ref") or "memory-st"
    created = row.get("created_at") or "unknown"
    kind = row.get("kind") or "unknown"
    if summary:
        score = 1.0 if "'"$QUERY"'" in summary.lower() else 0.7
        print("short-term\tfts5\t{}\t{}\t{}\t{}".format(score, created[:10], source, summary[:200]))
' >> "$RESULTS_FILE" 2>/dev/null || true
  fi
fi

# ── Query cockpit tier ──────────────────────────────────────────
if tier_allowed "cockpit"; then
  for f in "$COCKPIT_LESSONS" "$COCKPIT_MEMORY"; do
    if [[ -f "$f" ]]; then
      if command -v rg >/dev/null 2>&1; then
        rg --no-heading --line-number --color=never --max-count=5 -i -F -- "$QUERY" "$f" 2>/dev/null \
          | while IFS= read -r line; do
            lineno=$(echo "$line" | cut -d: -f1)
            text=$(echo "$line" | cut -d: -f2-)
            freshness=$(stat -c '%y' "$f" 2>/dev/null | cut -d' ' -f1 || echo "unknown")
            echo -e "cockpit\tfts5\t1.0\t$freshness\t$f:$lineno\t$(echo "$text" | head -c 200)"
          done >> "$RESULTS_FILE" 2>/dev/null || true
      else
        grep -n --color=never -i -F -- "$QUERY" "$f" 2>/dev/null \
          | while IFS= read -r line; do
            lineno=$(echo "$line" | cut -d: -f1)
            text=$(echo "$line" | cut -d: -f2-)
            freshness=$(stat -c '%y' "$f" 2>/dev/null | cut -d' ' -f1 || echo "unknown")
            echo -e "cockpit\tfts5\t1.0\t$freshness\t$f:$lineno\t$(echo "$text" | head -c 200)"
          done >> "$RESULTS_FILE" 2>/dev/null || true
      fi
    fi
  done
fi

# ── Query workspace tiers ──────────────────────────────────────
declare -A WORKSPACE_PATHS=(
  ["workspace-project-a"]="$PROJECT_A/docs/MEMORY.md:$PROJECT_A/docs/LESSONS.md"
  ["workspace-project-b"]="$PROJECT_B/docs/MEMORY.md:$PROJECT_B/docs/LESSONS.md"
  ["workspace-vault"]="$VAULT/self/memory.md:$VAULT/findings:$VAULT/insights"
)

for ws_tier in workspace-project-a workspace-project-b workspace-vault; do
  if tier_allowed "$ws_tier"; then
    IFS=':' read -ra WS_FILES <<< "${WORKSPACE_PATHS[$ws_tier]}"
    for f in "${WS_FILES[@]}"; do
      if [[ -f "$f" ]]; then
        grep -rn --color=never -i -F -- "$QUERY" "$f" 2>/dev/null \
          | head -n 5 \
          | while IFS= read -r line; do
            lineno=$(echo "$line" | cut -d: -f1)
            text=$(echo "$line" | cut -d: -f3-)
            freshness=$(stat -c '%y' "$f" 2>/dev/null | cut -d' ' -f1 || echo "unknown")
            echo -e "${ws_tier}\tfts5\t0.4\t$freshness\t${f}:${lineno}\t$(echo "$text" | head -c 200)"
          done >> "$RESULTS_FILE" 2>/dev/null || true
      fi
    done
  fi
done

# ── Query vector tier (Pinecone) ───────────────────────────────
PINECONE_OK=1
if tier_allowed "vector"; then
  if [[ -n "${PINECONE_API_KEY:-}" ]]; then
    PY="$COCKPIT/.venv/bin/python"
    [[ -x "$PY" ]] || PY="python3"
    MEMORY_LT="$AGENT_OS_HOME/bin/memory-lt"
    if [[ -x "$MEMORY_LT" ]]; then
      "$MEMORY_LT" search-vector --namespace all --text "$QUERY" --limit 10 2>/dev/null \
        | "$PY" -c '
import json, sys
data = json.load(sys.stdin)
if not data.get("ok", False):
    sys.exit(1)
for hit in data.get("results", [])[:10]:
    namespace = hit.get("namespace", "unknown")
    score = float(hit.get("score", 0) or 0)
    source = hit.get("source_path") or hit.get("path") or "unknown"
    summary = " ".join((hit.get("summary") or "").split())[:200]
    freshness = hit.get("timestamp", "unknown")
    if isinstance(freshness, str) and len(freshness) > 10:
        freshness = freshness[:10]
    # Map namespace to tier
    tier_map = {"agent-os-docs":"cockpit",os.environ.get('LESSONS_NAMESPACE', 'agent-os-lessons'):"cockpit",
                "project-a":"workspace-project-a","vault":"workspace-vault","skills":"cockpit"}
    tier = tier_map.get(namespace, "vector")
    method = "vector"
    # Score classification
    if score > 0.8:
        norm_score = 0.9
    elif score > 0.6:
        norm_score = 0.6
    else:
        norm_score = 0.4
    print("{}\t{}\t{}\t{}\t{}\t{}".format(tier, method, norm_score, freshness, source, summary))
' >> "$RESULTS_FILE" 2>/dev/null || PINECONE_OK=0
    else
      PINECONE_OK=0
    fi
  else
    PINECONE_OK=0
  fi
fi

# ── Deduplicate: same source+line = keep higher score ───────────
DEDUP_FILE="$(mktemp)"

sort -t$'\t' -k3 -rn "$RESULTS_FILE" 2>/dev/null | awk -F'\t' '!seen[$5]++' > "$DEDUP_FILE" 2>/dev/null || cp "$RESULTS_FILE" "$DEDUP_FILE"

# ── Pack results by score until budget exhausted ────────────────
HEADER_SIZE=0
BODY_SIZE=0
BODY_LINES=()
RESULT_NUM=0
TOTAL_RAW=$(wc -l < "$RESULTS_FILE" | tr -d ' ')

# Build header
HEADER="=== CONTEXT PACK ==="
HEADER="${HEADER}
Query: \"${QUERY}\"
Budget: ${BUDGET} bytes"

if [[ "$PINECONE_OK" -eq 0 ]]; then
  HEADER="${HEADER}
NOTE: Pinecone unavailable, vector tier skipped"
fi

HEADER="${HEADER}
Tiers queried: ${TIERS_FILTER:-short-term,cockpit,workspace-project-a,workspace-project-b,workspace-vault,vector}"

HEADER_SIZE=$(echo -n "$HEADER" | wc -c)

# Read deduped results and pack
while IFS=$'\t' read -r tier method score freshness source text; do
  RESULT_NUM=$((RESULT_NUM + 1))
  BLOCK=""
  BLOCK="${BLOCK}
--- [${RESULT_NUM}] TIER:${tier} METHOD:${method} SCORE:${score} FRESHNESS:${freshness} RELIABILITY:medium ---
${text}"
  BLOCK_SIZE=$(echo -n "$BLOCK" | wc -c)

  if [[ $((BODY_SIZE + BLOCK_SIZE + HEADER_SIZE)) -le $BUDGET ]]; then
    BODY_LINES+=("$BLOCK")
    BODY_SIZE=$((BODY_SIZE + BLOCK_SIZE))
  else
    break
  fi
done < "$DEDUP_FILE"

# Output
USED=$((HEADER_SIZE + BODY_SIZE))
echo "$HEADER"
echo "Used: ${USED} bytes"
echo "Results: ${RESULT_NUM} (deduplicated from ${TOTAL_RAW})"
for block in "${BODY_LINES[@]}"; do
  echo "$block"
done
echo "=== END PACK ==="
