#!/usr/bin/env bash
# Controlled bypass fixtures for the authoritative privacy gate.
set -euo pipefail

ROOT="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
FIXTURES="/tmp/agent-os-privacy-fixtures-$$"
mkdir -p "$FIXTURES"
PASS=0
FAIL=0

expect_rejected() {
  local name="$1"
  local fixture="$2"
  local rc=0
  bash "$ROOT/tests/privacy/privacy_gate.sh" "$fixture" >/dev/null 2>&1 || rc=$?
  if [[ $rc -eq 0 ]]; then
    echo "FAIL: $name bypassed the privacy gate"
    FAIL=$((FAIL + 1))
  elif [[ $rc -eq 1 ]]; then
    echo "PASS: $name rejected"
    PASS=$((PASS + 1))
  else
    echo "FAIL: $name caused scanner error rc=$rc"
    FAIL=$((FAIL + 1))
  fi
}

make_fixture() {
  local name="$1"
  local dir="$FIXTURES/$name"
  mkdir -p "$dir"
  printf '%s\n' "$dir"
}

fixture="$(make_fixture owner-path)"
printf 'path: %s\n' "/ho""me/gee""k4/private/file" > "$fixture/leak.yaml"
expect_rejected "owner path" "$fixture"

fixture="$(make_fixture excluded-trees)"
mkdir -p "$fixture/droid-wiki" "$fixture/tests" "$fixture/examples"
printf '%s\n' "pcsk_""abcdefghijklmnopqrstuvwxyz123456" > "$fixture/droid-wiki/leak.txt"
printf '%s\n' "AKIA""ABCDEFGHIJKLMNOP" > "$fixture/tests/leak.txt"
printf '%s\n' "npm_""abcdefghijklmnopqrstuvwxyz1234567890" > "$fixture/examples/leak.txt"
expect_rejected "formerly excluded shipped trees" "$fixture"

fixture="$(make_fixture binary-token)"
printf '\0%s\n' "npm_""abcdefghijklmnopqrstuvwxyz1234567890" > "$fixture/blob.bin"
expect_rejected "secret token embedded in binary" "$fixture"

fixture="$(make_fixture binary-identity)"
printf '\0maintainer@%s\0%s\n' "corp.invalid" "/ho""me/alice/internal" > "$fixture/blob.bin"
expect_rejected "personal identity and home path embedded in binary" "$fixture"

fixture="$(make_fixture credential-file)"
printf '%s\n' '{}' > "$fixture/service-account-prod.json"
expect_rejected "service account filename" "$fixture"

fixture="$(make_fixture root-git)"
mkdir -p "$fixture/.git"
printf '%s\n' 'ref: refs/heads/main' > "$fixture/.git/HEAD"
expect_rejected "root Git metadata" "$fixture"

fixture="$(make_fixture personal-email)"
printf '%s\n' "maintainer@""private.invalid" > "$fixture/contact.txt"
expect_rejected "personal email" "$fixture"

fixture="$(make_fixture symlink)"
printf '%s\n' 'public target' > "$fixture/target.txt"
ln -s target.txt "$fixture/link.txt"
expect_rejected "symbolic link" "$fixture"

fixture="$(make_fixture redaction)"
secret="ghp_""ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890"
printf '%s\n' "$secret" > "$fixture/leak.txt"
expect_rejected "GitHub token" "$fixture"
if grep -Fq "$secret" "$fixture/.ossbuild/privacy-gate/findings.txt"; then
  echo "FAIL: evidence retained the secret value"
  FAIL=$((FAIL + 1))
else
  echo "PASS: evidence is redacted"
  PASS=$((PASS + 1))
fi

fixture="$(make_fixture scanner-error)"
stub_dir="$fixture/stub"
mkdir -p "$stub_dir"
cat > "$stub_dir/python3" <<'STUB'
#!/usr/bin/env bash
exit 2
STUB
chmod +x "$stub_dir/python3"
rc=0
PATH="$stub_dir:$PATH" bash "$ROOT/tests/privacy/privacy_gate.sh" "$fixture" >/dev/null 2>&1 || rc=$?
if [[ $rc -eq 2 ]]; then
  echo "PASS: scanner errors remain distinct"
  PASS=$((PASS + 1))
else
  echo "FAIL: scanner error returned rc=$rc instead of 2"
  FAIL=$((FAIL + 1))
fi

echo "Privacy negative fixtures: $PASS passed, $FAIL failed"
[[ $FAIL -eq 0 ]]
