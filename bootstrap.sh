#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${AGENT_OS_REPO_URL:-https://github.com/floridaKG/AgentOS-by-RegimeLab.git}"
INSTALL_DIR="${AGENT_OS_INSTALL_DIR:-${HOME}/.local/share/agent-os}"
REF="${AGENT_OS_REF:-main}"
FORCE=0

for arg in "$@"; do
  case "$arg" in
    --force) FORCE=1 ;;
    --help|-h)
      cat <<'EOF'
Usage: bootstrap.sh [--force]

Environment:
  AGENT_OS_INSTALL_DIR  Installation directory
  AGENT_OS_REF          Git ref to install (default: main)
  AGENT_OS_REPO_URL     Repository URL
EOF
      exit 0
      ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done

command -v git >/dev/null 2>&1 || {
  echo "Git is required. Install Git and rerun this command." >&2
  exit 1
}

if [ -e "$INSTALL_DIR" ] && [ ! -d "$INSTALL_DIR/.git" ]; then
  if [ "$FORCE" -ne 1 ]; then
    echo "Install directory exists and is not an Agent OS checkout: $INSTALL_DIR" >&2
    echo "Choose another AGENT_OS_INSTALL_DIR or rerun with --force." >&2
    exit 1
  fi
fi

if [ -d "$INSTALL_DIR/.git" ]; then
  if [ "$FORCE" -ne 1 ] && [ -n "$(git -C "$INSTALL_DIR" status --porcelain)" ]; then
    echo "Install checkout has local changes: $INSTALL_DIR" >&2
    echo "Commit or move those changes, or rerun with --force." >&2
    exit 1
  fi
  git -C "$INSTALL_DIR" fetch --depth 1 origin "$REF"
  git -C "$INSTALL_DIR" checkout --detach "FETCH_HEAD"
else
  mkdir -p "$(dirname "$INSTALL_DIR")"
  git clone --depth 1 --branch "$REF" "$REPO_URL" "$INSTALL_DIR"
fi

exec bash "$INSTALL_DIR/install.sh"
