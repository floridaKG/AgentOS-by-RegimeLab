#!/usr/bin/env bash
# manifest-truth-gate.sh — Validate manifest allowlist matches shipped files
# and deferred scripts are not advertised.
# Exit 0 = pass, exit 1 = fail.
set -euo pipefail

STAGING_DIR="${1:-.}"
TOTAL=0
FAILS=0

MANIFEST_PATH="${STAGING_DIR}/EXPORT_MANIFEST.yaml"
if [ ! -f "$MANIFEST_PATH" ]; then
  MANIFEST_PATH="${STAGING_DIR}/.ossbuild/EXPORT_MANIFEST.yaml"
fi
echo "  Manifest: $MANIFEST_PATH"
echo ""

# ── 1. Manifest allowlist scripts must exist on disk ──
echo "  [1] Manifest allowlist vs shipped scripts..."
ALLOWLIST_FAILS=0
python3 -c "
import yaml, pathlib, sys
root = pathlib.Path('$STAGING_DIR')
manifest_path = pathlib.Path('$STAGING_DIR') / '.ossbuild/EXPORT_MANIFEST.yaml'
if not manifest_path.exists():
    manifest_path = pathlib.Path('$STAGING_DIR') / 'EXPORT_MANIFEST.yaml'
manifest = yaml.safe_load(manifest_path.read_text()) or {}
scripts = manifest.get('allowlist', {}).get('scripts', {}).get('files', [])
missing = []
for s in scripts:
    p = root / 'scripts' / s
    if not p.exists():
        missing.append(s)
if missing:
    for m in missing:
        print(f'    FAIL: scripts/{m} listed in manifest but does not exist')
    sys.exit(1)
print('    PASS: all manifest script entries exist')
" && TOTAL=$((TOTAL+1)) || { TOTAL=$((TOTAL+1)); FAILS=$((FAILS+1)); }

# ── 2. Deferred archive scripts must not be in manifest ──
echo "  [2] Deferred scripts not in manifest..."
DEFERRED_FAILS=0
python3 -c "
import yaml, pathlib, sys
root = pathlib.Path('$STAGING_DIR')
manifest_path = pathlib.Path('$STAGING_DIR') / '.ossbuild/EXPORT_MANIFEST.yaml'
if not manifest_path.exists():
    manifest_path = pathlib.Path('$STAGING_DIR') / 'EXPORT_MANIFEST.yaml'
manifest = yaml.safe_load(manifest_path.read_text()) or {}
scripts = manifest.get('allowlist', {}).get('scripts', {}).get('files', [])
archive_dir = root / '.ossbuild' / 'archive'
if not archive_dir.exists():
    print('    PASS: no archive directory')
    sys.exit(0)
archived = set()
for p in archive_dir.rglob('*.py'):
    archived.add(p.name)
for p in archive_dir.rglob('*.sh'):
    archived.add(p.name)
overlap = [s for s in scripts if s in archived]
if overlap:
    for s in overlap:
        print(f'    FAIL: scripts/{s} is both in manifest and in .ossbuild/archive (deferred)')
    sys.exit(1)
print('    PASS: no deferred scripts in manifest')
" && TOTAL=$((TOTAL+1)) || { TOTAL=$((TOTAL+1)); FAILS=$((FAILS+1)); }

# ── 3. Registry tool paths must exist ──
echo "  [3] Registry tool paths exist..."
python3 -c "
import yaml, pathlib, sys
root = pathlib.Path('$STAGING_DIR')
data = yaml.safe_load((root / 'registry/tools.yaml').read_text()) or {}
missing = []
for entry in data.get('tools', []):
    path = str(entry.get('binary', ''))
    prefix = '\$AGENT_OS_HOME/'
    if path.startswith(prefix):
        candidate = root / path[len(prefix):]
        if not candidate.exists():
            missing.append(str(candidate.relative_to(root)))
if missing:
    for m in missing:
        print(f'    FAIL: {m} listed in registry but does not exist')
    sys.exit(1)
print('    PASS: all registry tool paths exist')
" && TOTAL=$((TOTAL+1)) || { TOTAL=$((TOTAL+1)); FAILS=$((FAILS+1)); }

# ── 4. INDEX.md no dangling paths ──
echo "  [4] INDEX.md paths resolve..."
python3 -c "
import pathlib, re, sys
root = pathlib.Path('$STAGING_DIR')
text = (root / 'INDEX.md').read_text()
paths = sorted(set(re.findall(r'\\\$AGENT_OS_HOME/([A-Za-z0-9_./-]+)', text)))
missing = []
for path in paths:
    cleaned = path.rstrip('.,)\`')
    if not (root / cleaned).exists():
        missing.append(cleaned)
if missing:
    for m in missing:
        print(f'    FAIL: INDEX.md references {m} which does not exist')
    sys.exit(1)
print('    PASS: all INDEX.md paths resolve')
" && TOTAL=$((TOTAL+1)) || { TOTAL=$((TOTAL+1)); FAILS=$((FAILS+1)); }

# ── 5. README.md referenced scripts exist ──
echo "  [5] README.md script references resolve..."
python3 -c "
import pathlib, re, sys
root = pathlib.Path('$STAGING_DIR')
text = (root / 'README.md').read_text()
# Find script/ references
refs = re.findall(r'scripts/([A-Za-z0-9_.-]+)', text)
missing = [r for r in refs if not (root / 'scripts' / r).exists()]
if missing:
    for m in missing:
        print(f'    FAIL: README.md references scripts/{m} which does not exist')
    sys.exit(1)
print('    PASS: all README.md script references resolve')
" && TOTAL=$((TOTAL+1)) || { TOTAL=$((TOTAL+1)); FAILS=$((FAILS+1)); }

# ── 6. No .ossbuild in shipped content (except PRIVACY_BOUNDARY.md and README.md) ──
echo "  [6] .ossbuild not referenced in shipped docs..."
OSSBUILD_FAILS=0
while IFS= read -r f; do
  case "$f" in
    */.ossbuild/*|*/tests/*) continue ;;
  esac
  if file -b "$f" 2>/dev/null | grep -q "binary"; then continue; fi
  # Check for patterns that suggest .ossbuild ships as content
  if grep -qP '"\.ossbuild/(?!README)' "$f" 2>/dev/null; then
    echo "    FAIL: $f references .ossbuild/ as shipping content"
    OSSBUILD_FAILS=$((OSSBUILD_FAILS+1))
  fi
done < <(find "$STAGING_DIR" -type f \( -name "*.md" -o -name "*.yaml" \) ! -path "*/.ossbuild/*" ! -path "*/tests/*" 2>/dev/null)
if [[ $OSSBUILD_FAILS -eq 0 ]]; then
  echo "    PASS: no .ossbuild shipping references"
  TOTAL=$((TOTAL+1))
else
  echo "    FAIL: $OSSBUILD_FAILS .ossbuild references found"
  TOTAL=$((TOTAL+1))
  FAILS=$((FAILS+1))
fi

# ── 7a. Bidirectional: all root-level shipped files are covered by manifest ──

echo "  [7a] Bidirectional: root-level shipped files covered by manifest..."
python3 -c "
import yaml, pathlib, sys, fnmatch
root = pathlib.Path('$STAGING_DIR')
manifest_path = pathlib.Path('$STAGING_DIR') / '.ossbuild/EXPORT_MANIFEST.yaml'
if not manifest_path.exists():
    manifest_path = pathlib.Path('$STAGING_DIR') / 'EXPORT_MANIFEST.yaml'
manifest = yaml.safe_load(manifest_path.read_text()) or {}
al = manifest.get('allowlist', {})

# Build declared set from manifest
root_files_declared = set()
for f in al.get('runtime_root', []):
    root_files_declared.add(f)
for f in al.get('agents_md', {}).get('files', []):
    root_files_declared.add(f)

# Also collect denylist patterns for filtering
denylist = al.get('denylist', {}).get('always_blocked', [])

# Check every root-level file
declared_patterns = []
for p in denylist:
    # Convert glob to fnmatch pattern
    declared_patterns.append(p)

undeclared = []
for p in root.iterdir():
    if p.is_dir():
        continue
    name = p.name
    if name.startswith('.'):
        continue  # dotfiles checked via denylist
    if name in root_files_declared:
        continue
    # Check if name matches any declared pattern (e.g. .env.template is handled by denylist exceptions)
    # Root-level files must be explicitly declared in runtime_root or agents_md
    undeclared.append(name)

if undeclared:
    for u in sorted(undeclared):
        print(f'    UNDECLARED root file: {u}')
    print(f'    Total undeclared root files: {len(undeclared)}')
    sys.exit(1)
else:
    print('    PASS: all root-level shipped files are covered')
" && TOTAL=$((TOTAL+1)) || { TOTAL=$((TOTAL+1)); FAILS=$((FAILS+1)); }

# ── 7b. Bidirectional: all tests/ files are covered by manifest ──
echo "  [7b] Bidirectional: tests/ files covered by manifest..."
python3 -c "
import yaml, pathlib, sys
root = pathlib.Path('$STAGING_DIR')
manifest_path = pathlib.Path('$STAGING_DIR') / '.ossbuild/EXPORT_MANIFEST.yaml'
if not manifest_path.exists():
    manifest_path = pathlib.Path('$STAGING_DIR') / 'EXPORT_MANIFEST.yaml'
manifest = yaml.safe_load(manifest_path.read_text()) or {}
al = manifest.get('allowlist', {})

# Build declared tests set from manifest
tests_declared = set()
for f in al.get('tests', {}).get('files', []):
    tests_declared.add(f)

# Check every file under tests/
tests_dir = root / 'tests'
undeclared = []
if tests_dir.exists():
    for p in tests_dir.rglob('*'):
        if p.is_dir():
            continue
        if '__pycache__' in p.parts or p.suffix == '.pyc':
            continue
        rel = str(p.relative_to(tests_dir))
        if rel in tests_declared:
            continue
        undeclared.append(rel)

if undeclared:
    for u in sorted(undeclared):
        print(f'    UNDECLARED test file: {u}')
    print(f'    Total undeclared test files: {len(undeclared)}')
    sys.exit(1)
else:
    print('    PASS: all tests/ files are covered')
" && TOTAL=$((TOTAL+1)) || { TOTAL=$((TOTAL+1)); FAILS=$((FAILS+1)); }

# ── 7c. Bidirectional: all files under shipped roots are covered by manifest ──
echo "  [7c] Bidirectional: shipped-root files covered by manifest..."
python3 -c "
import yaml, pathlib, sys
root = pathlib.Path('$STAGING_DIR')
manifest_path = pathlib.Path('$STAGING_DIR') / '.ossbuild/EXPORT_MANIFEST.yaml'
if not manifest_path.exists():
    manifest_path = pathlib.Path('$STAGING_DIR') / 'EXPORT_MANIFEST.yaml'
manifest = yaml.safe_load(manifest_path.read_text()) or {}
al = manifest.get('allowlist', {})

# Build declared set from manifest
declared = set()
declared_dirs = set()
for f in al.get('runtime_root', []):
    declared.add(f)
for f in al.get('agents_md', {}).get('files', []):
    declared.add(f)
for f in al.get('bin', {}).get('files', []):
    declared.add('bin/' + f)
for f in al.get('registry', {}).get('files', []):
    if f.endswith('/'):
        declared_dirs.add('registry/' + f)
    else:
        declared.add('registry/' + f)
for f in al.get('memory_core', {}).get('files', []):
    if f.endswith('/'):
        declared_dirs.add('memory/' + f)
    else:
        declared.add('memory/' + f)
for f in al.get('scripts', {}).get('files', []):
    declared.add('scripts/' + f)
for f in al.get('docs', {}).get('files', []):
    declared.add('docs/' + f)
for section in ['examples_vault_os', 'examples_superdocs']:
    entry = al.get(section, {})
    src = str(entry.get('source', ''))
    # Determine the staging prefix from source path
    if 'vault-os' in section or 'vault_os' in section:
        prefix = 'examples/vault-os/'
    elif 'superdocs' in section:
        prefix = 'examples/superdocs/'
    else:
        prefix = 'examples/'
    for f in entry.get('files', []):
        if f.endswith('/'):
            # Tree entry: declare the directory prefix
            declared_dirs.add(prefix + f)
        else:
            declared.add(prefix + f)

# Check every file under shipped roots
SHIPPED_ROOTS = ['bin', 'scripts', 'memory', 'registry', 'docs', 'examples']
undeclared = []
for root_dir in SHIPPED_ROOTS:
    d = root / root_dir
    if not d.exists():
        continue
    for p in d.rglob('*'):
        if p.is_dir():
            continue
        rel = str(p.relative_to(root))
        skip = False
        for part in p.parts:
            if part in ('.ossbuild', 'tests', '__pycache__', 'archive'):
                skip = True
                break
        if skip:
            continue
        if root_dir == 'skills':
            continue  # Skills declared by name
        if rel not in declared:
            # Check if file is under a declared directory
            in_declared_dir = False
            for dpath in declared_dirs:
                if rel.startswith(dpath):
                    in_declared_dir = True
                    break
            if not in_declared_dir:
                undeclared.append(rel)

if undeclared:
    for u in sorted(undeclared)[:10]:
        print(f'    UNDECLARED: {u}')
    if len(undeclared) > 10:
        print(f'    ... and {len(undeclared) - 10} more')
    print(f'    Total undeclared: {len(undeclared)}')
    sys.exit(1)
else:
    print('    PASS: all files under shipped roots are covered')
" && TOTAL=$((TOTAL+1)) || { TOTAL=$((TOTAL+1)); FAILS=$((FAILS+1)); }

# ── Summary ──
echo ""
echo "  Manifest Truth Gate: $TOTAL checks, $FAILS failures"
if [[ $FAILS -gt 0 ]]; then
  echo "  RESULT: FAIL"
  exit 1
else
  echo "  RESULT: PASS"
  exit 0
fi
