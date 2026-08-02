#!/usr/bin/env bash
# agent-os-boot.sh — Phase 2 boot wrapper
# Sources config, verifies secrets, runs sync-check, prints health banner.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source config from standard location (created by install.sh)
if [ -f "${HOME}/.config/agent-os/config.env" ]; then
  source "${HOME}/.config/agent-os/config.env"
elif [ -f "${SCRIPT_DIR}/../config.env" ]; then
  source "${SCRIPT_DIR}/../config.env"
else
  echo "  WARNING: config.env not found at ~/.config/agent-os/config.env"
  echo "  Run install.sh first or create the file manually."
fi

echo ""
echo "═════════════════════════════════════════════════════"
echo "        🛡️  Agent OS — Boot Sequence"
echo "═════════════════════════════════════════════════════"

# ── First-run detection ────────────────────────────────────
if [ -n "${AGENT_OS_HOME:-}" ] && [ ! -f "${AGENT_OS_HOME}/.local/state/agent-os/setup-complete" ]; then
  echo ""
  echo "  ⚡ FIRST RUN: Agent OS is installed but not configured."
  echo "     Follow docs/AGENT_SETUP.md to complete setup (rtk, ACPx, agents, roles)."
  echo "     Quick diagnostic: agent-os setup --check"
fi

# ── Secrets check ─────────────────────────────────────────────
if [[ -f "${HOME}/.config/agent-os/secrets.env" ]]; then
  set -a; source "${HOME}/.config/agent-os/secrets.env" 2>/dev/null || true; set +a
  _key="${PINECONE_API_KEY:-}"
  if [[ -z "$_key" ]]; then
    echo "  ⚠  Secrets file exists but PINECONE_API_KEY not exported"
  elif [[ "$_key" == *"your-"* || "$_key" == *"-here"* || "$_key" == *"placeholder"* ]]; then
    echo "  ✗  PINECONE_API_KEY is still a placeholder — update ~/.config/agent-os/secrets.env"
  elif [[ "$_key" != pcsk_* ]]; then
    echo "  ⚠  PINECONE_API_KEY set but doesn't look like a valid key (expected pcsk_...)"
  else
    echo "  ✓  Secrets loaded (PINECONE_API_KEY valid)"
  fi
else
  echo "  ⚠  ~/.config/agent-os/secrets.env not found"
fi

# ── Health preview ──────────────────────────────────────────
echo ""
"${SCRIPT_DIR}/agent-os-health.sh" 2>/dev/null || true

echo ""
echo "═════════════════════════════════════════════════════"
echo "  Session started. Helpful commands: agent-os-boot, digest, recall"
echo "  Update: /lesson, agent-os-verify"
echo "  Exit:  /lesson"
echo "═════════════════════════════════════════════════════"
echo ""
