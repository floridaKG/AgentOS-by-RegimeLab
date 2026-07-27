#!/usr/bin/env bash
set -euo pipefail

AGENT_OS_HOME="${AGENT_OS_HOME:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

echo "=== Agent OS Setup Check ==="
echo "Install: $AGENT_OS_HOME"
echo ""

check_command() {
  local name="$1"
  local hint="$2"
  if command -v "$name" >/dev/null 2>&1; then
    printf '  READY: %-10s %s\n' "$name" "$("$name" --version 2>&1 | head -1)"
  else
    printf '  NEXT:  %-10s %s\n' "$name" "$hint"
  fi
}

check_command python3 "Install Python 3.10 or newer"
check_command node "Install Node.js 18 or newer for ACPx"
check_command npm "Install npm for ACPx"
check_command acpx "Run: npm install -g acpx"

echo ""
echo "Agent profiles:"
for agent in claude codex opencode droid pi hermes cline omp cursor grok; do
  if command -v "$agent" >/dev/null 2>&1; then
    printf '  READY: %s CLI detected\n' "$agent"
  else
    printf '  INFO:  %s is available when its ACPx profile is configured\n' "$agent"
  fi
done

echo ""
echo "Next steps:"
echo "  1. Source: source $HOME/.config/agent-os/config.env"
echo "  2. Configure roles/models: $HOME/.config/agent-workflows/roles.toml"
echo "  3. Authenticate each provider CLI or ACPx profile you want to use."
echo "  4. Verify local core: agent-os doctor"
echo "  5. Verify ACP daemon: acp-health"
