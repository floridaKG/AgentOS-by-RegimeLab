#!/usr/bin/env bash
set -euo pipefail

# Agent OS Cold Boot Smoke Test
# Validates that the staged public repo can be installed and initialized
# without touching the owner's private runtime.

STAGE="${1:-${AGENT_OS_STAGE:-}}"
if [[ -z "$STAGE" ]]; then
  echo "usage: $0 <agent-os-root>" >&2
  exit 2
fi
STAGE="$(cd "$STAGE" && pwd)"
echo "=== Agent OS Cold Boot Smoke Test ==="
echo "Stage: $STAGE"
echo ""

PASS_COUNT=0
FAIL_COUNT=0

check() {
  local desc="$1"
  shift
  if "$@" >/dev/null 2>&1; then
    echo "  PASS: $desc"
    PASS_COUNT=$((PASS_COUNT + 1))
  else
    echo "  FAIL: $desc"
    FAIL_COUNT=$((FAIL_COUNT + 1))
  fi
}

echo "--- Structure Checks ---"
check "AGENTS.md at root" test -f "$STAGE/AGENTS.md"
check "BOOT.md at root" test -f "$STAGE/BOOT.md"
check "scripts/ at root" test -d "$STAGE/scripts"
check "memory/core/ exists" test -d "$STAGE/memory/core"

echo ""
echo "--- Skill Checks ---"
for skill in acp recall lesson digest doc-audit skill-optimizer upward-handoff changes-review; do
  check "skill: $skill/SKILL.md" test -f "$STAGE/skills/shared/$skill/SKILL.md"
done

echo ""
echo "--- Memory Architecture Checks ---"
check "memory/README.md exists" test -s "$STAGE/memory/README.md"
check "memory/core/ has files" test -n "$(find "$STAGE/memory/core" -type f 2>/dev/null | head -1)"
check "adapter: pinecone/ADAPTER.md" test -f "$STAGE/memory/adapters/pinecone/ADAPTER.md"
check "adapter: neo4j/ADAPTER.md" test -f "$STAGE/memory/adapters/neo4j/ADAPTER.md"

echo ""
echo "--- Bootstrap Checks ---"
check "README.md exists" test -f "$STAGE/README.md"
check "SETUP.md exists" test -f "$STAGE/SETUP.md"
check "LICENSE exists" test -f "$STAGE/LICENSE"
check ".env.template exists" test -f "$STAGE/.env.template"
check "config.env.template exists" test -f "$STAGE/config.env.template"
check "install.sh syntax" bash -n "$STAGE/install.sh"

echo ""
echo "--- Scrub Checks ---"
check "no owner username" bash -c "cd \"$STAGE\" && ! rg -qi \"${OWNER_USERNAME:-testuser}\" . --hidden --no-ignore -g '!.git/**' -g '!.ossbuild/**' -g '!droid-wiki/**' -g '!tests/**' -g '!PRIVACY_BOUNDARY.md' -g '!scripts/gate-privacy.sh' -g '!scripts/gate-release.sh'"
check "no owner Linux paths" bash -c "cd \"$STAGE\" && ! rg -q \"/home/${OWNER_USERNAME:-testuser}(?:/|\\\\b)\" . --hidden --no-ignore -g '!.git/**' -g '!.ossbuild/**' -g '!droid-wiki/**' -g '!tests/**' -g '!PRIVACY_BOUNDARY.md'"
check "no owner Windows-mount paths" bash -c "cd \"$STAGE\" && ! rg -q \"/mnt/c/Users/${OWNER_USERNAME:-testuser}(?:/|\\\\b)\" . --hidden --no-ignore -g '!.git/**' -g '!.ossbuild/**' -g '!droid-wiki/**' -g '!tests/**' -g '!PRIVACY_BOUNDARY.md'"
check "no owner service identifiers" bash -c "cd \"$STAGE\" && ! rg -qi 'floridakg|regime-lab\\.com|hwymwmhshzmhkewusdec' . --hidden --no-ignore -g '!.git/**' -g '!.ossbuild/**' -g '!droid-wiki/**' -g '!tests/**' -g '!PRIVACY_BOUNDARY.md' -g '!README.md' -g '!SETUP.md' -g '!LICENSE' -g '!RELEASE_READINESS.md' -g '!SECURITY.md' -g '!docs/codegraph-setup.md' -g '!scripts/gate-privacy.sh' -g '!scripts/gate-release.sh'"
check "no .env files" bash -c "! find \"$STAGE\" -name '.env' -print | grep -q ."
check "no .sqlite files" bash -c "! find \"$STAGE\" -name '*.sqlite' -print | grep -q ."
check "no handoffs directory" bash -c "! find \"$STAGE\" -name 'handoffs' -type d -not -path '*/.ossbuild/*' -print | grep -q ."
check "Hindsight is optional (not in core requirements)" bash -c "! grep -Eq '^hindsight-client([<=>]|$)' \"$STAGE/requirements.txt\""

echo ""
echo "--- Portability Checks ---"
check "workspace registry has no fixed owner roots" bash -c "! rg -q '^\\s*root:\\s*/(home|mnt/c/Users)/' \"$STAGE/registry/workspaces.yaml\""
check "health script has no fixed git root" bash -c "! rg -q 'GIT_ROOT=\"/(home|mnt/c/Users)/' \"$STAGE/scripts/agent-os-health.sh\""
check "exported skill paths exist" bash -c '
  python3 - "$1" <<"PY"
import pathlib, sys, yaml
root = pathlib.Path(sys.argv[1])
data = yaml.safe_load((root / "registry/skills.yaml").read_text()) or {}
missing = []
for entry in data.get("skills", []):
    path = str(entry.get("path", ""))
    prefix = "$AGENT_OS_HOME/"
    if path.startswith(prefix):
        candidate = root / path[len(prefix):]
        if not candidate.exists():
            missing.append(str(candidate.relative_to(root)))
if missing:
    print("\n".join(missing))
    raise SystemExit(1)
PY
' _ "$STAGE"
check "all YAML files parse" bash -c '
  python3 - "$1" <<"PY"
import pathlib, sys, yaml
root = pathlib.Path(sys.argv[1])
bad = []
for path in root.rglob("*.yaml"):
    if ".ossbuild" in path.parts:
        continue
    try:
        yaml.safe_load(path.read_text())
    except Exception as exc:
        bad.append(f"{path.relative_to(root)}: {exc}")
if bad:
    print("\n".join(bad))
    raise SystemExit(1)
PY
' _ "$STAGE"
check "INDEX has no absent Agent OS paths" bash -c '
  python3 - "$1" <<"PY"
import pathlib, re, sys
root = pathlib.Path(sys.argv[1])
text = (root / "INDEX.md").read_text()
paths = sorted(set(re.findall(r"\$AGENT_OS_HOME/([A-Za-z0-9_./-]+)", text)))
missing = [path for path in paths if not (root / path.rstrip(".,)`")).exists()]
if missing:
    print("\n".join(missing))
    raise SystemExit(1)
PY
' _ "$STAGE"

echo ""
echo "--- Results ---"
echo "  Passed: $PASS_COUNT"
echo "  Failed: $FAIL_COUNT"

if [ "$FAIL_COUNT" -eq 0 ]; then
  echo ""
  echo "=== COLD BOOT PASS ==="
  exit 0
else
  echo ""
  echo "=== COLD BOOT FAIL ==="
  exit 1
fi
