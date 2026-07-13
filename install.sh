#!/usr/bin/env bash
# Agent OS Installer
# Idempotent setup. Defaults to local-core memory profile (SQLite only).
# Supports non-interactive test mode: AGENT_OS_TEST=1 ./install.sh
# Optional flags:
#   --with-rtk    Install RTK (Rust Token Killer) CLI proxy (requires curl)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_OS_HOME="${AGENT_OS_HOME:-$SCRIPT_DIR}"
CONFIG_DIR="${HOME}/.config/agent-os"
CONFIG_FILE="${CONFIG_DIR}/config.env"
SECRETS_FILE="${CONFIG_DIR}/secrets.env"
WORKFLOW_CONFIG_DIR="${HOME}/.config/agent-workflows"
TEST_MODE="${AGENT_OS_TEST:-0}"
TEST_HOME="${AGENT_OS_TEST_HOME:-}"
WITH_RTK=0

# Parse flags
for arg in "$@"; do
  case "$arg" in
    --with-rtk) WITH_RTK=1 ;;
    --help|-h)
      echo "Usage: ./install.sh [--with-rtk]"
      echo ""
      echo "  --with-rtk  Install RTK (Rust Token Killer) CLI proxy (requires curl)"
      exit 0
      ;;
    *)
      echo "Unknown option: $arg"
      echo "Usage: ./install.sh [--with-rtk]"
      exit 1
      ;;
  esac
done

pass() { echo "  PASS: $1"; }
fail() { echo "  FAIL: $1"; exit 1; }
info() { echo "  $1"; }
skip() { echo "  SKIP: $1"; }

# In test mode, require an explicitly isolated HOME
if [ "$TEST_MODE" = "1" ]; then
  if [ -z "$TEST_HOME" ]; then
    fail "Test mode requires AGENT_OS_TEST_HOME to be set to an isolated directory"
  fi
  if [ "$TEST_HOME" = "$HOME" ]; then
    fail "Test mode must not use the user's real HOME"
  fi
  HOME="$TEST_HOME"
fi

echo "=== Agent OS Installer ==="
echo "Install target: $AGENT_OS_HOME"
echo "Test mode: $TEST_MODE"
echo ""

# ── Prerequisites ──
echo "--- Checking prerequisites ---"

PYTHON=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1; then
    PYTHON="$candidate"
    break
  fi
done

if [ -z "$PYTHON" ]; then
  fail "Python 3 is required (not found). Install: apt install python3 / brew install python"
fi

PY_VERSION=$($PYTHON --version 2>&1 | awk '{print $2}')
info "Python: $PY_VERSION"
pass "Python found"

if command -v git >/dev/null 2>&1; then
  info "Git: $(git --version 2>&1)"
else
  fail "Git is required (not found). Install: apt install git / brew install git"
fi

if command -v bash >/dev/null 2>&1; then
  info "Bash: ${BASH_VERSION}"
else
  fail "Bash is required (not found)"
fi

if command -v node >/dev/null 2>&1; then
  info "Node.js: $(node --version 2>&1) (optional — needed for ACPx/CodeGraph plugins)"
else
  info "Node.js: not found (optional — needed for ACPx/CodeGraph plugins)"
fi

# ── Verify repo structure ──
echo ""
echo "--- Verifying repo structure ---"
MISSING=0
for item in AGENTS.md BOOT.md scripts bin memory registry skills; do
  if [ ! -e "$AGENT_OS_HOME/$item" ]; then
    echo "  MISSING: $AGENT_OS_HOME/$item"
    MISSING=$((MISSING+1))
  fi
done
if [ "$MISSING" -gt 0 ]; then
  fail "Repo structure incomplete. Run from the Agent OS repo root."
fi
pass "Repo structure complete"

# ── Create config directory ──
echo ""
echo "--- Configuring Agent OS ---"
mkdir -p "$CONFIG_DIR"
pass "Config directory ready: $CONFIG_DIR"

# ── Create config.env if missing ──
if [ ! -f "$CONFIG_FILE" ]; then
  cat > "$CONFIG_FILE" << 'CONFIG_EOF'
# Agent OS Configuration
# Source this file in your shell profile: source ~/.config/agent-os/config.env

# Agent OS home directory (set by installer)
export AGENT_OS_HOME="AGENT_OS_HOME_PLACEHOLDER"

# LLM Provider (required)
# Supported: openai, anthropic, openrouter
export LLM_PROVIDER="openai"

# LLM API Key (required — get from your provider)
# export LLM_API_KEY="your-api-key-here"

# Optional: Knowledge vault path
# export VAULT_PATH="$HOME/vault"
CONFIG_EOF
  # Replace placeholder with actual path
  $PYTHON -c "
import sys
path = sys.argv[1]
home = sys.argv[2]
with open(path) as f:
    content = f.read()
content = content.replace('AGENT_OS_HOME_PLACEHOLDER', home)
with open(path, 'w') as f:
    f.write(content)
" "$CONFIG_FILE" "$AGENT_OS_HOME"
  chmod 600 "$CONFIG_FILE"
  pass "Created: $CONFIG_FILE"
else
  pass "Config file exists: $CONFIG_FILE (skipped)"
fi

# ── Create secrets.env if missing ──
if [ ! -f "$SECRETS_FILE" ]; then
  cat > "$SECRETS_FILE" << 'SECRETS_EOF'
# Agent OS Secrets (sensitive values)
# Source this after config.env: source ~/.config/agent-os/secrets.env
# For local-core mode, no secrets are required.

# Optional: Pinecone for semantic memory
# export PINECONE_API_KEY="your-pinecone-key"
# export PINECONE_INDEX="agent-vault"

# Optional: Neo4j for graph memory
# export NEO4J_URI="neo4j+s://your-instance.databases.neo4j.io"
# export NEO4J_USER="your-username"
# export NEO4J_PASSWORD="your-password"
SECRETS_EOF
  chmod 600 "$SECRETS_FILE"
  pass "Created: $SECRETS_FILE (chmod 600)"
else
  chmod 600 "$SECRETS_FILE" 2>/dev/null || true
  pass "Secrets file exists: $SECRETS_FILE (skipped)"
fi

# ── Install portable multi-agent configuration ──
echo ""
echo "--- Configuring multi-agent workflows ---"
mkdir -p "$WORKFLOW_CONFIG_DIR/lib" "$WORKFLOW_CONFIG_DIR/acp"
for file in roles.toml panels.toml model_aliases.toml safety.toml; do
  if [ ! -f "$WORKFLOW_CONFIG_DIR/$file" ]; then
    cp "$AGENT_OS_HOME/.config/agent-workflows/$file" "$WORKFLOW_CONFIG_DIR/$file"
    pass "Created: $WORKFLOW_CONFIG_DIR/$file"
  else
    pass "Workflow config exists: $WORKFLOW_CONFIG_DIR/$file (preserved)"
  fi
done
for file in run.sh acpx-dispatch.sh safety.sh workspace.sh packet.sh; do
  cp "$AGENT_OS_HOME/.config/agent-workflows/lib/$file" "$WORKFLOW_CONFIG_DIR/lib/$file"
  chmod +x "$WORKFLOW_CONFIG_DIR/lib/$file"
done
for file in swarm.sh council.sh escalate.sh orchestrate.sh dialogue.sh redteam.sh load-roles.sh; do
  cp "$AGENT_OS_HOME/.config/agent-workflows/$file" "$WORKFLOW_CONFIG_DIR/$file"
  chmod +x "$WORKFLOW_CONFIG_DIR/$file"
done
for file in acp_send.py acp_completion.py; do
  cp "$AGENT_OS_HOME/.config/agent-workflows/acp/$file" "$WORKFLOW_CONFIG_DIR/acp/$file"
done
pass "Multi-agent workflow runtime installed"

# ── Python dependencies ──
echo ""
echo "--- Installing Python dependencies ---"
if [ -f "$AGENT_OS_HOME/requirements.txt" ]; then
  if [ "$TEST_MODE" = "1" ]; then
    skip "Python dependencies (test mode)"
  else
    if [ -n "${VIRTUAL_ENV:-}" ]; then
      $PYTHON -m pip install -r "$AGENT_OS_HOME/requirements.txt" --quiet 2>&1 || \
        echo "  WARN: pip install had issues — you may need: pip install -r requirements.txt"
    else
      $PYTHON -m pip install --user -r "$AGENT_OS_HOME/requirements.txt" --quiet 2>&1 || \
        echo "  WARN: pip install had issues — you may need: pip install --user -r requirements.txt"
    fi
    pass "Python dependencies installed"
  fi
else
  skip "No requirements.txt found"
fi

# ── Verify bin facades ──
echo ""
echo "--- Verifying CLI facades ---"
for cmd in memory-st memory-lt memory-recall memory-recall-safe memory-inject memory-promote agent-voice team agent-workflow; do
  if [ -f "$AGENT_OS_HOME/bin/$cmd" ]; then
    pass "bin/$cmd"
  else
    echo "  MISSING: bin/$cmd"
  fi
done

# ── Verify scripts ──
echo ""
echo "--- Verifying scripts ---"
for script in agent-os-health.sh agent-os-verify.sh registry-check.py; do
  if [ -f "$AGENT_OS_HOME/scripts/$script" ]; then
    pass "scripts/$script"
  else
    echo "  MISSING: scripts/$script"
  fi
done

# ── Initialize memory directory ──
echo ""
echo "--- Initializing memory ---"
mkdir -p "${HOME}/.local/state/agent-os/memory"
pass "Memory directory ready: ${HOME}/.local/state/agent-os/memory"

# ── Auto-add bin/ to PATH in shell profile ──
echo ""
echo "--- Adding bin/ to PATH ---"
if [ "$TEST_MODE" = "1" ]; then
  skip "Shell profile PATH modification (test mode)"
elif [[ -f "${HOME}/.bashrc" ]] && ! grep -q 'AGENT_OS_HOME/bin' "${HOME}/.bashrc" 2>/dev/null; then
  {
    echo ""
    echo "# Agent OS PATH"
    echo "export PATH=\"\$AGENT_OS_HOME/bin:\$PATH\""
  } >> "${HOME}/.bashrc"
  echo "  Added \$AGENT_OS_HOME/bin to PATH in ~/.bashrc"
  echo "  (Run 'source ~/.bashrc' or open a new terminal to activate)"
elif [[ -f "${HOME}/.bashrc" ]] && grep -q 'AGENT_OS_HOME/bin' "${HOME}/.bashrc" 2>/dev/null; then
  echo "  PATH already configured in ~/.bashrc (skipped)"
elif [[ -f "${HOME}/.zshrc" ]] && ! grep -q 'AGENT_OS_HOME/bin' "${HOME}/.zshrc" 2>/dev/null; then
  {
    echo ""
    echo "# Agent OS PATH"
    echo "export PATH=\"\$AGENT_OS_HOME/bin:\$PATH\""
  } >> "${HOME}/.zshrc"
  echo "  Added \$AGENT_OS_HOME/bin to PATH in ~/.zshrc"
elif [[ -f "${HOME}/.profile" ]] && ! grep -q 'AGENT_OS_HOME/bin' "${HOME}/.profile" 2>/dev/null; then
  {
    echo ""
    echo "# Agent OS PATH"
    echo "export PATH=\"\$AGENT_OS_HOME/bin:\$PATH\""
  } >> "${HOME}/.profile"
  echo "  Added \$AGENT_OS_HOME/bin to PATH in ~/.profile"
else
  echo "  Could not auto-add to PATH. Add this line to your shell profile:"
  echo "    export PATH=\"\$AGENT_OS_HOME/bin:\$PATH\""
fi

 # ── Optional: RTK (Rust Token Killer) ──
 echo ""
 echo "--- Optional: RTK (Rust Token Killer) ---"
 if [ "$WITH_RTK" != "1" ]; then
   echo "  RTK not requested. To install: ./install.sh --with-rtk"
   echo "  RTK is a CLI proxy that reduces LLM token consumption by 60-90%"
   echo "  by filtering command outputs before they reach your AI agent."
   echo "  (Apache 2.0 — github.com/rtk-ai/rtk — external project, not created by Agent OS)"
   echo "  Requires: curl"
 elif [ "$TEST_MODE" = "1" ]; then
   skip "RTK installation (test mode)"
 elif ! command -v curl >/dev/null 2>&1; then
   fail "RTK installation requires curl (not found). Install: apt install curl / brew install curl"
 elif command -v rtk >/dev/null 2>&1; then
   pass "RTK already installed: $(rtk --version 2>&1)"
 else
   echo "  Installing RTK from github.com/rtk-ai/rtk..."
   echo "  (Official install script — full attribution in docs/rtk-usage-guide.md)"
   if curl -fsSL https://raw.githubusercontent.com/rtk-ai/rtk/master/install.sh | sh; then
     pass "RTK installed successfully"
   else
     echo "  WARNING: RTK installation failed (non-fatal — continuing without it)"
   fi
 fi

# ── Summary ──
echo ""
echo "=== Installation Summary ==="
echo "  AGENT_OS_HOME: $AGENT_OS_HOME"
echo "  Config: $CONFIG_FILE"
echo "  Secrets: $SECRETS_FILE"
echo "  Memory profile: local-core (SQLite only)"
echo "  CLI facades: bin/ ($(ls "$AGENT_OS_HOME/bin/" 2>/dev/null | wc -l) commands)"

echo ""
echo "=== Next Steps ==="
echo "1. Add your LLM API key to $SECRETS_FILE"
echo "2. Source the config: source $CONFIG_FILE"
echo "3. (Optional) Add bin/ to PATH: auto-configured in ~/.bashrc (or check shell profile)"
echo "4. Verify: bash $AGENT_OS_HOME/scripts/agent-os-health.sh"
echo "5. Read AGENTS.md to get started"
echo ""
echo "=== Optional Setup ==="
echo "  RTK (token savings):   re-run with: ./install.sh --with-rtk"
echo "  Knowledge vault:       bash scripts/init-vault.sh --create ~/my-vault"
echo "  SuperDocs:             bash scripts/init-superdocs.sh --project my-project"
echo ""
