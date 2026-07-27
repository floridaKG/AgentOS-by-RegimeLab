#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CI_PENDING="$ROOT/.github/workflows/ci.yml.pending-auth"
CI_ENABLED="$ROOT/.github/workflows/ci.yml"
EXAMPLE_CI="$ROOT/examples/superdocs/.github/workflows/governance-check.yml"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

if [[ -f "$CI_PENDING" && -f "$CI_ENABLED" ]]; then
  fail "both pending and enabled CI workflows exist"
elif [[ -f "$CI_PENDING" ]]; then
  CI="$CI_PENDING"
elif [[ -f "$CI_ENABLED" ]]; then
  CI="$CI_ENABLED"
else
  fail "CI workflow is missing"
fi

grep -q '^permissions:$' "$CI" || fail "CI lacks explicit permissions"
grep -q '^  contents: read$' "$CI" || fail "CI is not read-only"
grep -q 'persist-credentials: false' "$CI" || fail "checkout credentials would persist"
grep -q 'fetch-depth: 0' "$CI" || fail "history scan would run against a shallow checkout"
grep -q 'tests/smoke/release_gate.sh' "$CI" || fail "CI does not run the complete release gate"
grep -q 'tests/privacy/privacy_gate.sh' "$CI" || fail "CI does not run the privacy gate"
grep -q 'tests/privacy/history_gate.sh' "$CI" || fail "CI does not scan reachable Git history"
grep -q 'tests/security/test_runtime_security.py' "$CI" || fail "CI does not run runtime security regressions"
grep -q 'git archive HEAD' "$CI" || fail "CI does not test a Git-free release candidate"
grep -q 'timeout-minutes:' "$CI" || fail "CI jobs are unbounded"
grep -q '^concurrency:$' "$CI" || fail "CI lacks concurrency cancellation"

if grep -Eq 'uses: [^[:space:]]+@(v[0-9]+|main|master)([[:space:]#]|$)' "$CI" "$EXAMPLE_CI"; then
  fail "workflow action is not pinned to an immutable commit"
fi

if grep -Eq '(curl|wget).*(https?://)|https?://.*\|[[:space:]]*(sh|bash)' "$EXAMPLE_CI"; then
  fail "example workflow downloads or pipes remote code"
fi
grep -q 'Commit a reviewed checker to this repository' "$EXAMPLE_CI" || \
  fail "example workflow does not fail closed when its checker is absent"

for pattern in 'secrets.env' 'service-account*.json' '.npmrc' '.netrc' '*.key' '*.p8' '*.keystore' 'kubeconfig'; do
  grep -Fqx "$pattern" "$ROOT/.gitignore" || fail ".gitignore missing $pattern"
done

grep -q '^PyYAML==[0-9]' "$ROOT/requirements.txt" || fail "PyYAML is not exactly pinned"
grep -q 'Add your LLM API key to \$SECRETS_FILE' "$ROOT/install.sh" || \
  fail "installer does not route provider credentials to secrets.env"
grep -q 'AGENT_OS_TEST_HOME' "$ROOT/install.sh" || \
  fail "installer test mode does not require an explicitly isolated HOME"
if AGENT_OS_TEST=1 AGENT_OS_TEST_HOME="$HOME" HOME="$HOME" \
  bash "$ROOT/install.sh" >/dev/null 2>&1; then
  fail "installer test mode accepts the user's real HOME"
fi

if grep -Eq 'git (add|commit|rm)|agent-os-docs|/home/[^[:space:]]+' \
  "$ROOT/skills/shared/doc-audit/SKILL.md"; then
  fail "doc-audit contains private paths or prohibited Git writes"
fi

if grep -RIEq '^Active contributors:' "$ROOT/droid-wiki" \
  --include='*.md' --include='*.json' --include='*.txt' \
  --exclude='captions.en.vtt'; then
  fail "wiki contains internal contributor identifiers"
fi

echo "PASS: CI and documentation hardening"
