#!/usr/bin/env bash
# Agent OS Installer
# Idempotent setup. Defaults to local-core memory profile (SQLite only).
# Supports non-interactive test mode: AGENT_OS_TEST=1 ./install.sh
# Optional flags:
#   --with-rtk       Install RTK (Rust Token Killer) CLI proxy (requires curl)
#   --no-path        Do not modify shell profile PATH
#   --setup-memory   Walk through optional memory backend setup interactively
#   --quickstart     Seed demo memory records so recall returns results immediately
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
NO_PATH=0
WITH_SETUP_MEMORY=0
WITH_QUICKSTART=0

# Parse flags
for arg in "$@"; do
  case "$arg" in
    --with-rtk) WITH_RTK=1 ;;
    --no-path) NO_PATH=1 ;;
    --setup-memory) WITH_SETUP_MEMORY=1 ;;
    --quickstart) WITH_QUICKSTART=1 ;;
    --help|-h)
      echo "Usage: ./install.sh [--with-rtk] [--no-path] [--setup-memory] [--quickstart]"
      echo ""
      echo "  --with-rtk      Install RTK (Rust Token Killer) CLI proxy (requires curl)"
      echo "                 Advanced opt-in: runs a third-party install script over HTTPS."
      echo "  --no-path       Do not append \$AGENT_OS_HOME/bin to ~/.bashrc|~/.zshrc|~/.profile"
      echo "  --setup-memory  Walk through optional memory backend setup (Pinecone, Neo4j, Hindsight)"
      echo "                 Interactive: prompts for each backend, opens signup URLs, writes config."
      echo "  --quickstart    Seed demo memory records so recall returns results immediately"
      echo "                 Writes 5 realistic demo lessons for exploration."
      exit 0
      ;;
    *)
      echo "Unknown option: $arg"
      echo "Usage: ./install.sh [--with-rtk] [--no-path] [--setup-memory] [--quickstart]"
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
for cmd in memory-st memory-lt memory-recall memory-recall-safe memory-inject memory-promote agent-voice team agent-workflow hindsight-bridge hindsight-gc hindsight-health; do
  if [ -f "$AGENT_OS_HOME/bin/$cmd" ]; then
    chmod +x "$AGENT_OS_HOME/bin/$cmd" 2>/dev/null || true
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
elif [ "$NO_PATH" = "1" ]; then
  skip "Shell profile PATH modification (--no-path)"
  echo "  Add manually: export PATH=\"\$AGENT_OS_HOME/bin:\$PATH\""
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
  echo "  RTK is a CLI proxy that reduces LLM token consumption by filtering"
  echo "  command outputs before they reach your AI agent."
  echo "  (Apache 2.0 — github.com/rtk-ai/rtk — external project, not Agent OS)"
  echo "  Requires: curl"
  echo "  Security: --with-rtk downloads and runs a third-party install script over HTTPS."
  echo "  Review upstream before use in locked-down environments."
elif [ "$TEST_MODE" = "1" ]; then
  skip "RTK installation (test mode)"
elif ! command -v curl >/dev/null 2>&1; then
  fail "RTK installation requires curl (not found). Install: apt install curl / brew install curl"
elif command -v rtk >/dev/null 2>&1; then
  pass "RTK already installed: $(rtk --version 2>&1)"
else
  echo "  SECURITY NOTICE: About to download and execute the official RTK install"
  echo "  script from https://raw.githubusercontent.com/rtk-ai/rtk/master/install.sh"
  echo "  This is a third-party supply-chain step (not audited by Agent OS)."
  echo "  Installing RTK from github.com/rtk-ai/rtk..."
  if curl -fsSL https://raw.githubusercontent.com/rtk-ai/rtk/master/install.sh | sh; then
    pass "RTK installed successfully"
  else
    echo "  WARNING: RTK installation failed (non-fatal — continuing without it)"
  fi
fi

# ── Optional: Memory backends (Pinecone, Neo4j, Hindsight) ──
echo ""
echo "--- Optional: Memory backends ---"
if [ "$WITH_SETUP_MEMORY" != "1" ]; then
  echo "  Memory backend setup not requested."
  echo "  To walk through Pinecone / Neo4j / Hindsight setup interactively:"
  echo "    ./install.sh --setup-memory"
  echo "  Or follow the guided doc: docs/OPTIONAL_BACKENDS.md"
else
  echo "  Interactive memory backend setup."
  echo "  You can skip any backend by answering 'n' when prompted."
  echo "  See docs/OPTIONAL_BACKENDS.md for manual setup instructions."
  echo ""

  # ── Pinecone ──
  echo "  ── Pinecone (semantic search) ──"
  if [ "$TEST_MODE" = "1" ]; then
    skip "Pinecone setup (test mode — use docs/OPTIONAL_BACKENDS.md)"
  else
    read -r -p "  Set up Pinecone semantic memory? [y/N] " PINE_ANS
    if [ "$PINE_ANS" = "y" ] || [ "$PINE_ANS" = "Y" ]; then
      echo ""
      echo "  Pinecone provides semantic vector search across sessions."
      echo "  You need a free Pinecone account (pinecone.io) and an API key."
      echo ""
      echo "  Step 1: Open https://www.pinecone.io/ in your browser."
      echo "          Sign up, then create an index with these settings:"
      echo "            Name: agent-vault"
      echo "            Dimensions: 1024"
      echo "            Metric: cosine"
      echo "            Pod type: Starter (free)"
      echo ""
      echo "  Step 2: Go to API Keys in the dashboard and copy your key."
      echo "          Keys start with 'pcsk_' or 'pcu_'."
      echo ""
      read -r -p "  Paste your Pinecone API key (or press Enter to skip): " PINE_KEY
      if [ -n "$PINE_KEY" ]; then
        read -r -p "  Index name [agent-vault]: " PINE_INDEX
        PINE_INDEX="${PINE_INDEX:-agent-vault}"
        # Update config.env — replace placeholder or append
        if grep -q "^# export PINECONE_API_KEY=" "$CONFIG_FILE" 2>/dev/null; then
          sed -i "s|^# export PINECONE_API_KEY=.*|export PINECONE_API_KEY=\"$PINE_KEY\"|" "$CONFIG_FILE"
          sed -i "s|^# export PINECONE_INDEX=.*|export PINECONE_INDEX=\"$PINE_INDEX\"|" "$CONFIG_FILE"
        elif ! grep -q "^export PINECONE_API_KEY=" "$CONFIG_FILE" 2>/dev/null; then
          {
            echo ""
            echo "# Pinecone semantic memory"
            echo "export PINECONE_API_KEY=\"$PINE_KEY\""
            echo "export PINECONE_INDEX=\"$PINE_INDEX\""
          } >> "$CONFIG_FILE"
        else
          echo "  Pinecone already configured in $CONFIG_FILE — skipping"
        fi
        pass "Pinecone configured (index: $PINE_INDEX)"
      else
        skip "Pinecone setup skipped (no key provided)"
      fi
    else
      skip "Pinecone setup skipped"
    fi
  fi

  echo ""

  # ── Neo4j ──
  echo "  ── Neo4j (graph memory) ──"
  if [ "$TEST_MODE" = "1" ]; then
    skip "Neo4j setup (test mode — use docs/OPTIONAL_BACKENDS.md)"
  else
    read -r -p "  Set up Neo4j graph memory? [y/N] " NEO_ANS
    if [ "$NEO_ANS" = "y" ] || [ "$NEO_ANS" = "Y" ]; then
      echo ""
      echo "  Neo4j provides relationship-based graph memory queries."
      echo "  You need a free Neo4j AuraDB instance (neo4j.com)."
      echo ""
      echo "  Step 1: Open https://neo4j.com/cloud/platform/aura-graph-database/"
      echo "          in your browser. Click 'Start Free' and create an account."
      echo "          Then create a free AuraDB instance (any name, any region)."
      echo "          IMPORTANT: Save the generated password — it's shown only once."
      echo ""
      echo "  Step 2: From the Aura console, copy your connection URI."
      echo "          It looks like: neo4j+s://abc123.databases.neo4j.io"
      echo ""
      read -r -p "  Paste your Neo4j connection URI (or press Enter to skip): " NEO_URI
      if [ -n "$NEO_URI" ]; then
        read -r -p "  Username [neo4j]: " NEO_USER
        NEO_USER="${NEO_USER:-neo4j}"
        read -r -p "  Password: " NEO_PASS
        if [ -n "$NEO_PASS" ]; then
          if grep -q "^# export NEO4J_URI=" "$CONFIG_FILE" 2>/dev/null; then
            sed -i "s|^# export NEO4J_URI=.*|export NEO4J_URI=\"$NEO_URI\"|" "$CONFIG_FILE"
            sed -i "s|^# export NEO4J_USER=.*|export NEO4J_USER=\"$NEO_USER\"|" "$CONFIG_FILE"
            sed -i "s|^# export NEO4J_PASSWORD=.*|export NEO4J_PASSWORD=\"$NEO_PASS\"|" "$CONFIG_FILE"
          elif ! grep -q "^export NEO4J_URI=" "$CONFIG_FILE" 2>/dev/null; then
            {
              echo ""
              echo "# Neo4j graph memory"
              echo "export NEO4J_URI=\"$NEO_URI\""
              echo "export NEO4J_USER=\"$NEO_USER\""
              echo "export NEO4J_PASSWORD=\"$NEO_PASS\""
            } >> "$CONFIG_FILE"
          else
            echo "  Neo4j already configured in $CONFIG_FILE — skipping"
          fi
          pass "Neo4j configured ($NEO_URI)"
        else
          skip "Neo4j setup skipped (no password provided)"
        fi
      else
        skip "Neo4j setup skipped (no URI provided)"
      fi
    else
      skip "Neo4j setup skipped"
    fi
  fi

  echo ""

  # ── Hindsight ──
  echo "  ── Hindsight (cross-agent memory sharing) ──"
  if [ "$TEST_MODE" = "1" ]; then
    skip "Hindsight setup (test mode — use docs/OPTIONAL_BACKENDS.md)"
  else
    read -r -p "  Set up Hindsight cross-agent memory? [y/N] " HIND_ANS
    if [ "$HIND_ANS" = "y" ] || [ "$HIND_ANS" = "Y" ]; then
      echo ""
      echo "  Hindsight enables cross-agent memory sharing via a shared bank."
      echo "  Requires: pip install 'hindsight-client>=0.4.22'"
      echo "            A running Hindsight API (hindsight serve &)"
      echo ""
      echo "  See docs/OPTIONAL_BACKENDS.md for the full setup walkthrough."
      echo "  Quick start: pip install 'hindsight-client>=0.4.22'"
      echo "               hindsight serve &  # starts API on http://127.0.0.1:9177"
      echo ""
      read -r -p "  Paste your Hindsight API URL [http://127.0.0.1:9177]: " HIND_URL
      HIND_URL="${HIND_URL:-http://127.0.0.1:9177}"
      read -r -p "  Bank ID [agent-os-shared]: " HIND_BANK
      HIND_BANK="${HIND_BANK:-agent-os-shared}"
      read -r -p "  Profile label [default]: " HIND_PROFILE
      HIND_PROFILE="${HIND_PROFILE:-default}"

      if grep -q "^# export HINDSIGHT_API_URL=" "$CONFIG_FILE" 2>/dev/null; then
        sed -i "s|^# export HINDSIGHT_API_URL=.*|export HINDSIGHT_API_URL=\"$HIND_URL\"|" "$CONFIG_FILE"
        sed -i "s|^# export HINDSIGHT_BANK=.*|export HINDSIGHT_BANK=\"$HIND_BANK\"|" "$CONFIG_FILE"
        sed -i "s|^# export HINDSIGHT_PROFILE=.*|export HINDSIGHT_PROFILE=\"$HIND_PROFILE\"|" "$CONFIG_FILE"
      elif ! grep -q "^export HINDSIGHT_API_URL=" "$CONFIG_FILE" 2>/dev/null; then
        {
          echo ""
          echo "# Hindsight cross-agent memory sharing"
          echo "export HINDSIGHT_API_URL=\"$HIND_URL\""
          echo "export HINDSIGHT_BANK=\"$HIND_BANK\""
          echo "export HINDSIGHT_PROFILE=\"$HIND_PROFILE\""
        } >> "$CONFIG_FILE"
      else
        echo "  Hindsight already configured in $CONFIG_FILE — skipping"
      fi
      pass "Hindsight configured (bank: $HIND_BANK)"
    else
      skip "Hindsight setup skipped"
    fi
  fi
  echo ""
  echo "  To verify your backends after setup:"
  echo "    source ~/.config/agent-os/config.env"
  echo "    bash \$AGENT_OS_HOME/scripts/agent-os-health.sh"
fi

# ── Optional: Quickstart demo records ──
echo ""
echo "--- Optional: Quickstart demo records ---"
if [ "$WITH_QUICKSTART" != "1" ]; then
  echo "  Quickstart not requested."
  echo "  To seed demo memory records for exploration:"
  echo "    ./install.sh --quickstart"
  echo "  Or see: docs/GETTING_STARTED.md"
else
  if [ "$TEST_MODE" = "1" ]; then
    skip "Quickstart seeding (test mode — use docs/GETTING_STARTED.md)"
  else
    echo "  Seeding 5 demo memory records so recall returns results immediately..."
    MEMORY_PY="$AGENT_OS_HOME/memory/core/short_term.py"
    DEMO_DIR="${HOME}/.local/state/agent-os/memory"
    mkdir -p "$DEMO_DIR"

    # Seed records via Python to avoid shell escaping issues
    python3 -c "
import subprocess, sys, os
agent_os_home = os.environ.get('AGENT_OS_HOME', '')
mem_py = os.path.join(agent_os_home, 'memory', 'core', 'short_term.py')
records = [
    {
        'summary': 'Login endpoint rate-limits at 5 failed attempts per IP, 15min cooldown',
        'content': 'The /api/auth/login endpoint rate-limits after 5 consecutive failed attempts from the same IP address. The cooldown period is 15 minutes. Implementation is in src/middleware/rate_limiter.py, configured via RATE_LIMIT_MAX_ATTEMPTS and RATE_LIMIT_WINDOW_MINUTES env vars. The rate limit counter resets on successful login.',
    },
    {
        'summary': 'Database migration lock prevents writes during schema changes',
        'content': 'When running database migrations, the migration framework acquires an exclusive lock on the affected tables. During this lock window (typically 2-5 seconds), write operations fail with a \"database is locked\" error. The application must handle this gracefully: retry with exponential backoff or queue writes for replay. See the migration runner in src/db/migrate.py and the write queue in src/db/write_queue.py.',
    },
    {
        'summary': 'Config reload requires SIGHUP, not restart — preserves in-flight requests',
        'content': 'The application supports hot config reload via SIGHUP signal. Sending SIGHUP to the main process PID causes it to re-read config.env and apply changes without dropping active connections. This is preferred over restart because it preserves in-flight requests. The PID file is at /var/run/app.pid. See src/config/reloader.py for the signal handler implementation.',
    },
    {
        'summary': 'Cache warming takes ~90 seconds on cold start, API returns 503 during warmup',
        'content': 'On cold start (empty cache), the application spends approximately 90 seconds warming the Redis cache from the primary database. During this window, the health check endpoint returns 200 but the API endpoints return 503 Service Unavailable. Load balancers should be configured to check /api/ready (not /api/health) before routing traffic. The warmup progress can be monitored at /api/cache/status.',
    },
    {
        'summary': 'Webhook signature verification fails if request body is read more than once',
        'content': 'The webhook signature verification middleware reads the raw request body to compute the HMAC-SHA256 signature. If any upstream middleware or route handler also reads request.body, the verification will fail because the body stream is already consumed. The fix is to buffer the body in the verification middleware and attach it as request.rawBody for downstream consumers. See src/middleware/webhook_verify.py.',
    },
]
for i, rec in enumerate(records):
    content_file = f'/tmp/agent_os_quickstart_{i}.txt'
    with open(content_file, 'w') as f:
        f.write(rec['content'])
    result = subprocess.run(
        ['python3', mem_py, 'write',
         '--run-id', f'quickstart-{i+1:03d}',
         '--agent-id', 'demo',
         '--workspace', 'demo',
         '--intent', 'LESSON',
         '--kind', 'observation',
         '--summary', rec['summary'],
         '--content-file', content_file,
         '--source-ref', 'quickstart:demo'],
        capture_output=True, text=True, timeout=15
    )
    if result.returncode == 0:
        print(f'    Seeded record {i+1}/5: {rec[\"summary\"][:60]}...')
    else:
        print(f'    WARNING: record {i+1} failed: {result.stderr[:120]}')
    os.unlink(content_file)
" 2>&1

    echo ""
    echo "  Demo records seeded. Try it:"
    echo "    source ~/.config/agent-os/config.env"
    echo "    recall \"what happens during database migrations\""
    echo ""
    echo "  See docs/GETTING_STARTED.md for the full first-run walkthrough."
  fi
fi

# ── Summary ──
echo ""
echo "=== Installation Summary ==="
echo "  AGENT_OS_HOME: $AGENT_OS_HOME"
echo "  Config: $CONFIG_FILE"
echo "  Secrets: $SECRETS_FILE"
echo "  Memory profile: local-core (SQLite only)"
if [ "$WITH_SETUP_MEMORY" = "1" ]; then
  echo "  Memory backends: interactive setup completed (see docs/OPTIONAL_BACKENDS.md)"
fi
echo "  CLI facades: bin/ ($(ls "$AGENT_OS_HOME/bin/" 2>/dev/null | wc -l) commands)"

echo ""
echo "=== Next Steps ==="
echo "1. Add your LLM API key to $SECRETS_FILE"
echo "2. Source the config: source $CONFIG_FILE"
echo "3. Read the getting started guide: docs/GETTING_STARTED.md"
echo "4. (Optional) Seed demo records: ./install.sh --quickstart"
echo "5. Add bin/ to PATH: auto-configured in ~/.bashrc (or check shell profile)"
echo "6. Verify: bash $AGENT_OS_HOME/scripts/agent-os-health.sh"
echo ""
echo "=== Optional Setup ==="
echo "  ACPx (agent launcher): npm install -g acpx"
echo "    Without ACPx, ACP dispatch runs in dry-run mode (records what would run)."
echo "    Requires Node.js 18+: https://nodejs.org/"
echo "  Memory backends:       ./install.sh --setup-memory"
echo "    Guided:              docs/OPTIONAL_BACKENDS.md"
echo "  RTK (token savings):   re-run with: ./install.sh --with-rtk"
echo "  Knowledge vault:       bash scripts/init-vault.sh --create ~/my-vault"
echo "  SuperDocs:             bash scripts/init-superdocs.sh --project my-project"
echo ""
