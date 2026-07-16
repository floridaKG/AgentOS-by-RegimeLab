#!/usr/bin/env bash
# Agent OS Privacy Gate
# Scans all shipped content for prohibited patterns.
# Exits non-zero if any gate fails.
set -euo pipefail

STAGE="${1:-}"
if [[ -z "$STAGE" ]]; then
  echo "usage: $0 <agent-os-root>" >&2
  exit 2
fi
STAGE="$(cd "$STAGE" && pwd)"
echo "=== Agent OS Privacy Gate ==="
echo "Stage: $STAGE"
echo ""

# Require ripgrep (rg) — all text scans depend on it.
if ! command -v rg >/dev/null 2>&1; then
  echo "ERROR: ripgrep (rg) is required but not installed." >&2
  echo "Install it with: sudo apt-get install ripgrep" >&2
  exit 2
fi

GATE_DIR="$STAGE/.ossbuild/privacy-gate"
mkdir -p "$GATE_DIR"

# All rg/find scans below execute from STAGE with relative path '.' so that
# -g exclusions (which are matched against the path given to rg) are reliable.
# Evidence artifacts are written via absolute paths under GATE_DIR.

PASS_COUNT=0
FAIL_COUNT=0

gate() {
  local name="$1"
  shift
  local artifact="$GATE_DIR/${name}.txt"
  local rc=0
  "$@" > "$artifact" 2>&1 || rc=$?
  if [ $rc -eq 0 ]; then
    echo "  PASS: $name"
    rm -f "$artifact"
    PASS_COUNT=$((PASS_COUNT + 1))
  elif [ $rc -eq 1 ]; then
    local count=0
    if [ -s "$artifact" ]; then
      count=$(wc -l < "$artifact" | tr -d ' ')
    fi
    echo "  FAIL_MATCH: $name ($count matches — see $artifact)"
    FAIL_COUNT=$((FAIL_COUNT + 1))
  else
    local count=0
    if [ -s "$artifact" ]; then
      count=$(wc -l < "$artifact" | tr -d ' ')
    fi
    echo "  FAIL_SCAN: $name ($count lines — scanner error, see $artifact)"
    FAIL_COUNT=$((FAIL_COUNT + 1))
  fi
}

# ── Gate 1: Owner identifier scan ──
# PRIVACY_BOUNDARY.md is an explanatory doc that names prohibited patterns for
# maintainers. It is whitelisted because documentation that describes what NOT to
# ship must be able to reference those patterns by name. Seeded content outside
# PRIVACY_BOUNDARY.md and tests/ is still detected.
echo "--- Gate 1: Owner identifiers ---"
# When OWNER_USERNAME is empty (default CI), skip explicit username scans — the
# tree must not hardcode a real maintainer username. Maintainers can set
# OWNER_USERNAME locally or via a repo secret for an extra pass.
_OWNER="${OWNER_USERNAME:-}"
if [[ -n "$_OWNER" ]]; then
  gate "owner_username" bash -c "cd '$STAGE' && rg -i \"$_OWNER\" '.' --hidden --no-ignore -g '!droid-wiki/**' -g '!.git/**' -g '!.ossbuild/**' -g '!.github/**' -g '!tests/**' -g '!PRIVACY_BOUNDARY.md' -g '!scripts/gate-privacy.sh' -g '!scripts/gate-release.sh'; rc=\$?; if [ \$rc -eq 0 ]; then exit 1; elif [ \$rc -eq 1 ]; then exit 0; else exit 2; fi"
  gate "owner_linux_paths" bash -c "cd '$STAGE' && rg \"/home/$_OWNER\" '.' --hidden --no-ignore -g '!droid-wiki/**' -g '!.git/**' -g '!.ossbuild/**' -g '!.github/**' -g '!tests/**' -g '!PRIVACY_BOUNDARY.md'; rc=\$?; if [ \$rc -eq 0 ]; then exit 1; elif [ \$rc -eq 1 ]; then exit 0; else exit 2; fi"
  gate "owner_windows_paths" bash -c "cd '$STAGE' && rg \"/mnt/c/Users/$_OWNER\" '.' --hidden --no-ignore -g '!droid-wiki/**' -g '!.git/**' -g '!.ossbuild/**' -g '!.github/**' -g '!tests/**' -g '!PRIVACY_BOUNDARY.md'; rc=\$?; if [ \$rc -eq 0 ]; then exit 1; elif [ \$rc -eq 1 ]; then exit 0; else exit 2; fi"
  gate "binary_owner_strings" bash -c "cd '$STAGE' && ! find '.' -type f ! -path '*/.ossbuild/*' ! -path '*/.git/*' ! -path '*/.github/*' ! -path '*/tests/*' ! -path '*/droid-wiki/*' ! -name '*.md' ! -name '*.txt' ! -name '*.yaml' ! -name '*.yml' ! -name '*.sh' ! -name '*.py' ! -name '*.sql' ! -name '*.json' ! -name '*.template' ! -name '*.log' ! -name '*.toml' -exec grep -l \"$_OWNER\" {} + 2>/dev/null | grep ."
else
  echo "  SKIP: owner_username (OWNER_USERNAME unset)"
  echo "  SKIP: owner_linux_paths (OWNER_USERNAME unset)"
  echo "  SKIP: owner_windows_paths (OWNER_USERNAME unset)"
  echo "  SKIP: binary_owner_strings (OWNER_USERNAME unset)"
  PASS_COUNT=$((PASS_COUNT + 4))
fi
gate "owner_vault_path" bash -c "cd '$STAGE' && rg '/mnt/c/vault' '.' --hidden --no-ignore -g '!EXPORT_MANIFEST.yaml' -g '!droid-wiki/**' -g '!.git/**' -g '!.ossbuild/**' -g '!tests/**' -g '!PRIVACY_BOUNDARY.md'; rc=\$?; if [ \$rc -eq 0 ]; then exit 1; elif [ \$rc -eq 1 ]; then exit 0; else exit 2; fi"
# Public clone URL + launch drafts may name the GitHub owner/repo; exclude
# intentional public surfaces (README/SETUP/launch/assets). Still flags private
# service IDs in code/skills.
gate "owner_service_ids" bash -c "cd '$STAGE' && rg -i 'floridakg|hwymwmhshzmhkewusdec|regime-lab\\\\.com' '.' --hidden --no-ignore -g '!droid-wiki/**' -g '!.git/**' -g '!.ossbuild/**' -g '!tests/**' -g '!PRIVACY_BOUNDARY.md' -g '!README.md' -g '!SETUP.md' -g '!LICENSE' -g '!RELEASE_READINESS.md' -g '!SECURITY.md' -g '!docs/codegraph-setup.md' -g '!docs/launch/**' -g '!docs/assets/**' -g '!docs/ARCHITECTURE.md'; rc=\$?; if [ \$rc -eq 0 ]; then exit 1; elif [ \$rc -eq 1 ]; then exit 0; else exit 2; fi"

# ── Gate 2: Private service references ──
# PRIVACY_BOUNDARY.md names private services as exclusions (informational).
# Scans target private runtime paths / module names — not public multi-agent
# provider words that appear in skill docs.

echo ""
echo "--- Gate 2: Private services ---"
# Flag private runtime paths only (not public multi-agent provider names).
# Hindsight is a supported optional adapter — do not ban its public modules.
gate "hermes_private_paths" bash -c "cd '$STAGE' && rg -i '~/?\.hermes|/\\.hermes/|hermes-state|hermes/logs|sync-hermes' '.' --hidden --no-ignore -g '!droid-wiki/**' -g '!.git/**' -g '!.ossbuild/**' -g '!tests/**' -g '!EXPORT_MANIFEST.yaml' -g '!PRIVACY_BOUNDARY.md' -g '!scripts/gate-privacy.sh' -g '!scripts/gate-release.sh'; rc=\$?; if [ \$rc -eq 0 ]; then exit 1; elif [ \$rc -eq 1 ]; then exit 0; else exit 2; fi"
# Brand asset filenames + architecture poster are intentional public Regime Lab
# marks. Still flags accidental private Regime Lab product paths outside allowlist.
gate "regimelab_refs" bash -c "cd '$STAGE' && rg -i 'regimelab|regime-lab' '.' --hidden --no-ignore -g '!EXPORT_MANIFEST.yaml' -g '!droid-wiki/**' -g '!.git/**' -g '!.ossbuild/**' -g '!tests/**' -g '!examples/**' -g '!PRIVACY_BOUNDARY.md' -g '!scripts/gate-privacy.sh' -g '!scripts/gate-release.sh' -g '!README.md' -g '!SETUP.md' -g '!LICENSE' -g '!RELEASE_READINESS.md' -g '!docs/codegraph-setup.md' -g '!SECURITY.md' -g '!docs/launch/**' -g '!docs/assets/**' -g '!docs/ARCHITECTURE.md' -g '!COMMERCIAL_BOUNDARY.md'; rc=\$?; if [ \$rc -eq 0 ]; then exit 1; elif [ \$rc -eq 1 ]; then exit 0; else exit 2; fi"
gate "kwant_refs" bash -c "cd '$STAGE' && rg -i 'kwant' '.' --hidden --no-ignore -g '!EXPORT_MANIFEST.yaml' -g '!droid-wiki/**' -g '!.git/**' -g '!.ossbuild/**' -g '!tests/**' -g '!examples/**' -g '!PRIVACY_BOUNDARY.md' -g '!scripts/gate-privacy.sh' -g '!scripts/gate-release.sh'; rc=\$?; if [ \$rc -eq 0 ]; then exit 1; elif [ \$rc -eq 1 ]; then exit 0; else exit 2; fi"

# ── Gate 3: Secret patterns ──
# Documentation and template files legitimately contain placeholder API keys
# (e.g., your-api-key-here). These are excluded from hardcoded_secrets scan.
# The scan still catches real secrets in scripts, configs, and non-doc files.
echo ""
echo "--- Gate 3: Secret patterns ---"
gate "api_keys" bash -c "cd '$STAGE' && rg 'sk-[a-zA-Z0-9]{20,}' '.' --hidden --no-ignore -g '!droid-wiki/**' -g '!.git/**' -g '!.ossbuild/**' -g '!tests/**' -g '!scripts/gate-release.sh'; rc=\$?; if [ \$rc -eq 0 ]; then exit 1; elif [ \$rc -eq 1 ]; then exit 0; else exit 2; fi"
gate "hardcoded_secrets" bash -c "cd '$STAGE' && rg -i 'api_key[[:space:]]*=[[:space:]]*\"[a-zA-Z0-9]' '.' --hidden --no-ignore -g '!droid-wiki/**' -g '!.git/**' -g '!.ossbuild/**' -g '!tests/**' -g '!SETUP.md' -g '!install.sh' -g '!.env.template' -g '!config.env.template'; rc=\$?; if [ \$rc -eq 0 ]; then exit 1; elif [ \$rc -eq 1 ]; then exit 0; else exit 2; fi"

# ── Gate 4: Prohibited file types ──
# .env.template is a legitimate shipped file (environment template for users).
echo ""
echo "--- Gate 4: Prohibited files ---"
gate "env_files" bash -c "cd '$STAGE' && ! find '.' -name '.env' -not -path '*/.ossbuild/*' -not -path '*/tests/*' | grep ."
gate "env_pattern_files" bash -c "cd '$STAGE' && ! find '.' -name '.env.*' -not -name '.env.template' -not -path '*/.ossbuild/*' -not -path '*/tests/*' | grep ."
gate "sqlite_files" bash -c "cd '$STAGE' && ! find '.' -name '*.sqlite' -not -path '*/.ossbuild/*' -not -path '*/tests/*' | grep ."
gate "db_files" bash -c "cd '$STAGE' && ! find '.' -name '*.db' -not -path '*/.ossbuild/*' -not -path '*/tests/*' | grep ."
gate "pem_files" bash -c "cd '$STAGE' && ! find '.' -name '*.pem' -not -path '*/.ossbuild/*' -not -path '*/tests/*' | grep ."
gate "ssh_key_files" bash -c "cd '$STAGE' && ! find '.' -name '*_ed25519' -o -name '*_rsa' | grep ."
gate "credential_files" bash -c "cd '$STAGE' && ! find '.' -name 'credential*.json' -not -path '*/.ossbuild/*' | grep ."
gate "handoffs_dir" bash -c "cd '$STAGE' && ! find '.' -name 'handoffs' -type d -not -path '*/.ossbuild/*' | grep ."
# Fail only on *tracked* bytecode (would ship). Untracked local __pycache__
# from developer runs is gitignored and is cleaned separately.
gate "pycache_files" bash -c "cd '$STAGE' && if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then ! git ls-files -z -- '**/__pycache__/**' '**/*.pyc' | grep -qz .; else ! find '.' \\( -name '__pycache__' -o -name '*.pyc' \\) -not -path '*/.ossbuild/*' -not -path '*/.git/*' | grep .; fi"

# ── Gate 5: No git repository ──
echo ""
echo "--- Gate 5: No git repo ---"
gate "no_git_dir" bash -c "cd '$STAGE' && ! find '.' -mindepth 2 -name '.git' -type d -not -path '*/.ossbuild/*' | grep ."

# ── Gate 6: Registry consistency ──
echo ""
echo "--- Gate 6: Registry consistency ---"
gate "yaml_parse" bash -c "cd '$STAGE' && python3 -c \"
import pathlib, sys, yaml
root = pathlib.Path('.')
bad = []
for path in root.rglob('*.yaml'):
    if '.ossbuild' in path.parts or 'tests' in path.parts:
        continue
    try:
        yaml.safe_load(path.read_text())
    except Exception as exc:
        bad.append(f'{path.relative_to(root)}: {exc}')
if bad:
    print(chr(10).join(bad))
    sys.exit(1)
\""
gate "skill_paths_resolve" bash -c "cd '$STAGE' && python3 -c \"
import pathlib, sys, yaml
root = pathlib.Path('.')
data = yaml.safe_load((root / 'registry/skills.yaml').read_text()) or {}
missing = []
for entry in data.get('skills', []):
    path = str(entry.get('path', ''))
    prefix = '\$AGENT_OS_HOME/'
    if path.startswith(prefix):
        candidate = root / path[len(prefix):]
        if not candidate.exists():
            missing.append(str(candidate.relative_to(root)))
if missing:
    print(chr(10).join(missing))
    sys.exit(1)
\""

# ── Results ──
echo ""
echo "=== Privacy Gate Results ==="
echo "  Passed: $PASS_COUNT"
echo "  Failed: $FAIL_COUNT"

# Write artifact
cat > "$GATE_DIR/summary.txt" << EOF
privacy_gate_pass=$PASS_COUNT
privacy_gate_fail=$FAIL_COUNT
timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)
EOF

if [ "$FAIL_COUNT" -eq 0 ]; then
  echo ""
  echo "=== PRIVACY GATE PASS ==="
  exit 0
else
  echo ""
  echo "=== PRIVACY GATE FAIL ==="
  exit 1
fi
