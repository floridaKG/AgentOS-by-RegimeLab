#!/usr/bin/env bash
# release_gate.sh — Redirect to the authoritative release gate
# The canonical gate is: scripts/gate-release.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STAGING_DIR="${STAGING_DIR:-$(cd "$SCRIPT_DIR/../.." && pwd)}"

echo "=== Redirecting to authoritative release gate ==="
echo "  Canonical: scripts/gate-release.sh"
echo ""
exec bash "$STAGING_DIR/scripts/gate-release.sh" "$@"
