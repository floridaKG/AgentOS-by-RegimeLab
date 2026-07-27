#!/usr/bin/env bash
# init-vault.sh — Create or link a knowledge vault for Agent OS
# Usage: scripts/init-vault.sh [--create <path>] [--link <path>]
#        scripts/init-vault.sh --help
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_OS_HOME="${AGENT_OS_HOME:-$(cd "$SCRIPT_DIR/.." && pwd)}"
CONFIG_DIR="${HOME}/.config/agent-os"
CONFIG_FILE="${CONFIG_DIR}/config.env"
SECRETS_FILE="${CONFIG_DIR}/secrets.env"
SKELETON_DIR="${AGENT_OS_HOME}/examples/vault-os"

ACTION="create"
VAULT_PATH=""

# ── Parse arguments ──
usage() {
  cat << EOF
Usage: $(basename "$0") [OPTIONS]

Create or link a knowledge vault for Agent OS.

Options:
  --create <path>   Create a new vault at <path> with Vault-OS skeleton
                    (default: \$HOME/vault)
  --link <path>     Link to an existing vault at <path> (validates it exists)
  --help            Show this help message and exit

Examples:
  $(basename "$0")                         # Create vault at \$HOME/vault
  $(basename "$0") --create ~/my-vault     # Create vault at ~/my-vault
  $(basename "$0") --link ~/existing-kb    # Link to existing vault

The vault path is written to ~/.config/agent-os/config.env as VAULT_PATH.
EOF
  exit 0
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --create)
      ACTION="create"
      VAULT_PATH="${2:-}"
      if [[ -z "$VAULT_PATH" ]]; then
        echo "ERROR: --create requires a path argument"
        echo "  Usage: $(basename "$0") --create <path>"
        exit 1
      fi
      shift 2
      ;;
    --link)
      ACTION="link"
      VAULT_PATH="${2:-}"
      if [[ -z "$VAULT_PATH" ]]; then
        echo "ERROR: --link requires a path argument"
        echo "  Usage: $(basename "$0") --link <path>"
        exit 1
      fi
      shift 2
      ;;
    --help|-h)
      usage
      ;;
    *)
      echo "ERROR: Unknown option: $1"
      echo "  Run '$(basename "$0") --help' for usage."
      exit 1
      ;;
  esac
done

# ── Default to --create $HOME/vault ──
if [[ -z "$VAULT_PATH" ]]; then
  ACTION="create"
  VAULT_PATH="${HOME}/vault"
fi

# ── Normalize to absolute path ──
if [[ "$VAULT_PATH" != /* ]]; then
  VAULT_PATH="$(pwd)/$VAULT_PATH"
fi

echo "=== Agent OS Vault Init ==="
echo "  Action:  $ACTION"
echo "  Target:  $VAULT_PATH"
echo "  Config:  $CONFIG_FILE"
echo ""

# ── Ensure config directory exists ──
mkdir -p "$CONFIG_DIR"
echo "  Config directory: ready"

# ── Check if config.env already has VAULT_PATH ──
if [[ -f "$CONFIG_FILE" ]] && grep -q '^export VAULT_PATH=' "$CONFIG_FILE" 2>/dev/null; then
  echo "  WARNING: $CONFIG_FILE already contains VAULT_PATH"
  echo "    Existing: $(grep '^export VAULT_PATH=' "$CONFIG_FILE")"
  echo "    Will be updated to: export VAULT_PATH=\"$VAULT_PATH\""
  # Remove the old line so we can replace it
  tmp_cfg=$(mktemp)
  grep -v '^export VAULT_PATH=' "$CONFIG_FILE" > "$tmp_cfg"
  mv "$tmp_cfg" "$CONFIG_FILE"
fi

# ── Execute action ──
if [[ "$ACTION" == "create" ]]; then
  if [[ -d "$VAULT_PATH" ]]; then
    echo ""
    echo "  WARNING: Vault directory already exists at $VAULT_PATH"
    echo "    Contents: $(ls "$VAULT_PATH" 2>/dev/null | head -5 | tr '\n' ' ')"
    echo "    Skipping skeleton copy. Writing config with existing path."
    echo ""
  else
    # ── Create vault directory ──
    mkdir -p "$VAULT_PATH"
    echo "  Created vault directory: $VAULT_PATH"

    # ── Check for skeleton ──
    if [[ -d "$SKELETON_DIR" ]]; then
      # Copy skeleton files preserving structure
      cp -r "$SKELETON_DIR"/. "$VAULT_PATH/"
      echo "  Copied Vault-OS skeleton from $SKELETON_DIR"

      # Count what was copied
      _file_count=$(find "$VAULT_PATH" -type f | wc -l)
      echo "    Files: $_file_count"
    else
      echo "  WARNING: Skeleton not found at $SKELETON_DIR"
      echo "    Vault created empty. Populate manually or re-run after install."
    fi
  fi

elif [[ "$ACTION" == "link" ]]; then
  # ── Validate existing vault ──
  if [[ ! -d "$VAULT_PATH" ]]; then
    echo "  ERROR: Vault path does not exist: $VAULT_PATH"
    echo "    Create it first, or use --create instead."
    exit 1
  fi
  echo "  Verified vault exists: $VAULT_PATH"

  # Check for AGENTS.md (good sign it's a real vault)
  if [[ -f "$VAULT_PATH/AGENTS.md" ]]; then
    echo "  Found AGENTS.md (valid vault detected)"
  elif [[ -f "$VAULT_PATH/BOOT.md" ]]; then
    echo "  Found BOOT.md (vault skeleton detected)"
  else
    echo "  WARNING: No AGENTS.md or BOOT.md found in $VAULT_PATH"
    echo "    This may not be a Vault-OS directory. Continuing anyway."
  fi
fi

# ── Write VAULT_PATH to config.env ──
{
  echo ""
  echo "# Vault path (set by init-vault.sh)"
  echo "export VAULT_PATH=\"$VAULT_PATH\""
} >> "$CONFIG_FILE"

echo "  Wrote VAULT_PATH to $CONFIG_FILE"

# ── Ensure secrets.env exists with correct perms ──
if [[ ! -f "$SECRETS_FILE" ]]; then
  cat > "$SECRETS_FILE" << 'SECRETS_EOF'
# Agent OS Secrets (sensitive values)
# Source this after config.env: source ~/.config/agent-os/secrets.env
# For local-core mode, no secrets are required.

# Optional: Pinecone for semantic memory
# export PINECONE_API_KEY=<your-pinecone-api-key>
# export PINECONE_INDEX="agent-vault"

# Optional: Neo4j for graph memory
# export NEO4J_URI="neo4j+s://your-instance.databases.neo4j.io"
# export NEO4J_USER="your-username"
# export NEO4J_PASSWORD="your-password"
SECRETS_EOF
  chmod 600 "$SECRETS_FILE"
  echo "  Created secrets file: $SECRETS_FILE (chmod 600)"
else
  # Ensure existing secrets file is restricted
  chmod 600 "$SECRETS_FILE" 2>/dev/null || true
fi

# ── Summary ──
echo ""
echo "=== Vault Init Complete ==="
echo "  Vault path:  $VAULT_PATH"
echo "  Config:      $CONFIG_FILE"
echo ""
echo "=== Next Steps ==="
echo "1. Source the config:  source $CONFIG_FILE"
echo "2. Explore your vault:  ls $VAULT_PATH"
echo "3. Read the vault boot:  cat $VAULT_PATH/BOOT.md"
if [[ "$ACTION" == "create" ]]; then
  echo "4. Add content: place sources in $VAULT_PATH/capture/"
fi
echo "5. Run health check:  bash $AGENT_OS_HOME/scripts/agent-os-health.sh"
echo ""
