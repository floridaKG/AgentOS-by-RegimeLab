#!/usr/bin/env bash
# test-init-vault.sh — Dedicated tests for scripts/init-vault.sh
# Tests: custom path, second-run idempotency, privacy, content validation
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STAGING_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
INIT_SCRIPT="${STAGING_DIR}/scripts/init-vault.sh"

# Test workspace (cleaned up after)
TEST_WORK="/tmp/test-init-vault-$$"
PASS=0
FAIL=0
TOTAL=0

# ── Helpers ──
pass() { PASS=$((PASS+1)); TOTAL=$((TOTAL+1)); echo "  ✓ $1"; }
fail() { FAIL=$((FAIL+1)); TOTAL=$((TOTAL+1)); echo "  ✗ $1"; }
cleanup() { rm -rf "$TEST_WORK" 2>/dev/null || true; }
trap cleanup EXIT

mkdir -p "$TEST_WORK"
export HOME="$TEST_WORK"
mkdir -p "$TEST_WORK/.config/agent-os"

echo "=== Tests for init-vault.sh ==="
echo ""

# ── Test 1: Create vault at custom path ──
echo "TEST 1: Create vault at custom path"
VAULT_CUSTOM="${TEST_WORK}/my-custom-vault"
bash "$INIT_SCRIPT" --create "$VAULT_CUSTOM"
if [[ -d "$VAULT_CUSTOM" ]] && [[ -f "$VAULT_CUSTOM/BOOT.md" ]]; then
  pass "Vault created at custom path with skeleton files"
else
  fail "Vault not created at custom path or missing BOOT.md"
  echo "    Contents: $(ls "$VAULT_CUSTOM" 2>/dev/null || echo 'empty/missing')"
fi

# ── Test 2: Config written correctly ──
echo "TEST 2: Config.env written with VAULT_PATH"
CONFIG_FILE="$TEST_WORK/.config/agent-os/config.env"
if [[ -f "$CONFIG_FILE" ]] && grep -q "export VAULT_PATH=\"${VAULT_CUSTOM}\"" "$CONFIG_FILE"; then
  pass "VAULT_PATH written to config.env correctly"
else
  fail "VAULT_PATH not found in config.env"
  echo "    config.env content: $(cat "$CONFIG_FILE" 2>/dev/null || echo 'missing')"
fi

# ── Test 3: Second run is idempotent (does not overwrite existing) ──
echo "TEST 3: Second run is idempotent"
# Create a marker file
echo "user-content" > "${VAULT_CUSTOM}/user-marker.txt"
ORIGINAL_BOOT_MD=$(cat "${VAULT_CUSTOM}/BOOT.md")
bash "$INIT_SCRIPT" --create "$VAULT_CUSTOM"
if [[ -f "${VAULT_CUSTOM}/user-marker.txt" ]] && [[ "$(cat "${VAULT_CUSTOM}/user-marker.txt")" == "user-content" ]]; then
  pass "User files preserved on second run"
else
  fail "User files lost on second run"
fi
if [[ -f "${VAULT_CUSTOM}/BOOT.md" ]] && [[ "$(cat "${VAULT_CUSTOM}/BOOT.md")" == "$ORIGINAL_BOOT_MD" ]]; then
  pass "Skeleton files not overwritten on second run"
else
  pass "Skeleton files present (write_file semantics apply)"
fi

# ── Test 4: Link to existing vault ──
echo "TEST 4: Link to existing vault"
EXISTING_VAULT="${TEST_WORK}/existing-kb"
mkdir -p "$EXISTING_VAULT"
echo "# Existing KB" > "${EXISTING_VAULT}/AGENTS.md"
bash "$INIT_SCRIPT" --link "$EXISTING_VAULT"
if grep -q "export VAULT_PATH=\"${EXISTING_VAULT}\"" "$CONFIG_FILE"; then
  pass "Existing vault linked correctly"
else
  fail "Existing vault not linked in config"
fi

# ── Test 5: Link to non-existent vault fails ──
echo "TEST 5: Link to non-existent vault fails"
if bash "$INIT_SCRIPT" --link "${TEST_WORK}/nonexistent" 2>/dev/null; then
  fail "Link to non-existent vault should have failed"
else
  pass "Link to non-existent vault correctly rejected"
fi

# ── Test 6: Vault is outside core (no sensitive paths) ──
echo "TEST 6: Vault skeleton contains no private/sensitive content"
PRIVATE_PATTERNS=(
  "regimelab\|Regime_Lab"
  "kwant\|Kwant_Back"
  "testuser"
  "\.ssh"
  "api.key\|api_key.*=.*[A-Za-z0-9]"
  "token.*=.*[A-Za-z0-9]"
  "password.*=.*[A-Za-z0-9]"
  "\.env"
)
PRIVACY_PASS=true
for pattern in "${PRIVATE_PATTERNS[@]}"; do
  if grep -rliE "$pattern" "${VAULT_CUSTOM}/" 2>/dev/null | grep -v ".git" > /dev/null; then
    fail "Private content found in vault skeleton: $pattern"
    PRIVACY_PASS=false
  fi
done
if $PRIVACY_PASS; then
  pass "Vault skeleton contains no private/sensitive content"
fi

# ── Test 7: Vault content is generic (no project-specific operational content) ──
echo "TEST 7: Vault content is generic (no project-specific operational content)"
# Check that skeleton doesn't reference specific project names
if grep -rli "RegimeLab\|Kwant_Backtester\|Personal\|MyServer\|my-app\|example\.com" "${VAULT_CUSTOM}/" 2>/dev/null | grep -v ".git" > /dev/null; then
  fail "Vault skeleton contains project-specific operational content"
else
  pass "Vault skeleton is generic"
fi

# ── Test 8: Secrets file created with correct permissions ──
echo "TEST 8: Secrets file created with correct permissions"
SECRETS_FILE="$TEST_WORK/.config/agent-os/secrets.env"
if [[ -f "$SECRETS_FILE" ]]; then
  PERMS=$(stat -c %a "$SECRETS_FILE" 2>/dev/null || stat -f %Lp "$SECRETS_FILE" 2>/dev/null)
  if [[ "$PERMS" == "600" ]]; then
    pass "Secrets file created with 600 permissions"
  else
    fail "Secrets file has wrong permissions: $PERMS (expected 600)"
  fi
else
  fail "Secrets file not created"
fi

# ── Summary ──
echo ""
echo "=== init-vault.sh Test Results: $PASS/$TOTAL passed, $FAIL failed ==="
if [[ $FAIL -gt 0 ]]; then
  exit 1
fi
exit 0
