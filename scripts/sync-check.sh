#!/usr/bin/env bash
# sync-check — verify $AGENT_OS_HOME/INDEX.md matches on-disk reality.
# Reports skills, scripts, and MCP tools that exist on disk but are missing from INDEX.md.
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

INDEX="$COCKPIT_INDEX"

if [[ ! -f "$INDEX" ]]; then
  echo "INDEX.md not found at $INDEX" >&2
  exit 1
fi

drift=0
report() {
  local label="$1" name="$2"
  if ! grep -qF "$name" "$INDEX"; then
    echo "  MISSING from INDEX.md: [$label] $name"
    drift=$((drift+1))
  fi
}

echo "── sync-check: comparing INDEX.md against on-disk reality ──"
echo ""

echo "▸ Cockpit skills ($COCKPIT/skills/)"
for d in "$COCKPIT/skills"/*/; do
  [[ -d "$d" ]] || continue
  report "cockpit-skill" "$(basename "$d")"
done

echo "▸ Cockpit scripts ($COCKPIT/scripts/)"
for f in "$COCKPIT/scripts"/*.sh "$COCKPIT/scripts"/*.py; do
  [[ -f "$f" ]] || continue
  report "cockpit-script" "$(basename "$f")"
done

echo "▸ Global Claude skills"
if [[ -d "$GLOBAL_SKILLS" ]]; then
  for d in "$GLOBAL_SKILLS"/*/; do
    [[ -d "$d" ]] || continue
    report "global-skill" "$(basename "$d")"
  done
fi

echo "▸ Vault skills"
if [[ -d "$VAULT/.claude/skills" ]]; then
  for d in "$VAULT/.claude/skills"/*/; do
    [[ -d "$d" ]] || continue
    report "vault-skill" "$(basename "$d")"
  done
fi

echo "▸ Workspace MCP tools (check each configured workspace)"
for ws_dir in "$COCKPIT"/*/tools/mcp/*/server.py; do
  [[ -f "$ws_dir" ]] || continue
  while IFS= read -r tool; do
    [[ -n "$tool" ]] && report "workspace-mcp" "$tool"
  done < <(awk '/^@mcp.tool/{getline; if(/^def /) print}' "$ws_dir" | sed 's/^def \([a-z_]*\).*/\1/')
done

echo ""
if [[ $drift -eq 0 ]]; then
  echo "✓ INDEX.md is in sync with on-disk reality."
else
  echo "✗ Found $drift item(s) on disk NOT in INDEX.md."
  echo "  Open $AGENT_OS_HOME/INDEX.md and add the missing entries, bump last_synced."
fi