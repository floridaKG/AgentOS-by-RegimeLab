#!/usr/bin/env bash
# Workspace registry helpers for agent-workflow prompts.
# Source this file.

WORKSPACE_REGISTRY_FILE="${WORKSPACE_REGISTRY_FILE:-$HOME/agent-os/registry/workspaces.yaml}"
WORKSPACE_FALLBACK_DOC="${WORKSPACE_FALLBACK_DOC:-$HOME/AGENT_OS.md}"
WORKSPACE_SKILLS_REGISTRY="${WORKSPACE_SKILLS_REGISTRY:-$HOME/agent-os/registry/skills.yaml}"
WORKSPACE_HARD_RULES_REGISTRY="${WORKSPACE_HARD_RULES_REGISTRY:-$HOME/agent-os/registry/hard_rules.yaml}"

resolve_workspace() {
    local name="$1"
    python3 - "$name" "$WORKSPACE_REGISTRY_FILE" "$WORKSPACE_FALLBACK_DOC" <<'PY'
import re
import sys
from pathlib import Path

name, registry_path, fallback_doc = sys.argv[1:]


def clean_scalar(value: str) -> str:
    value = value.strip()
    if (
        (value.startswith('"') and value.endswith('"'))
        or (value.startswith("'") and value.endswith("'"))
        or (value.startswith("`") and value.endswith("`"))
    ):
        return value[1:-1]
    return value


def parse_registry(path: Path):
    if not path.exists():
        return {}
    data = {}
    current = None
    section = None
    for raw in path.read_text().splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()
        if indent == 0 and line.startswith("- id:"):
            current = clean_scalar(line.split(":", 1)[1])
            data[current] = {}
            section = None
            continue
        if current is None:
            continue
        if indent == 2 and line.endswith(":") and line[:-1] in {"git", "deploy"}:
            section = line[:-1]
            continue
        if indent == 2 and ":" in line:
            key, value = line.split(":", 1)
            data[current][key.strip()] = clean_scalar(value)
            section = None
            continue
        if indent >= 4 and section and ":" in line:
            key, value = line.split(":", 1)
            data[current][f"{section}.{key.strip()}"] = clean_scalar(value)
    return data


def parse_fallback(path: Path):
    if not path.exists():
        return {}
    text = path.read_text()
    result = {}
    root_match = re.search(rf"^\s*-\s*(?:`)?{re.escape(name)}(?:`)?\s*->\s*(.+?)\s*$", text, re.M)
    if root_match:
        result["root"] = clean_scalar(root_match.group(1))
    boot_match = re.search(rf"^\|\s*{re.escape(name)}\s*\|\s*([^|]+?)\s*\|", text, re.M)
    if boot_match:
        result["boot_doc"] = clean_scalar(boot_match.group(1))
    return result


registry = parse_registry(Path(registry_path))
meta = registry.get(name)
if meta and meta.get("root"):
    print(meta["root"])
    raise SystemExit(0)

fallback = parse_fallback(Path(fallback_doc))
if fallback.get("root"):
    print(fallback["root"])
    raise SystemExit(0)

sys.stderr.write(
    f"Error: unknown workspace '{name}'. Looked in {registry_path} and the Workspace Map in {fallback_doc}.\n"
)
raise SystemExit(2)
PY
}

_workspace_meta() {
    local name="$1"
    python3 - "$name" "$WORKSPACE_REGISTRY_FILE" "$WORKSPACE_FALLBACK_DOC" "$WORKSPACE_SKILLS_REGISTRY" "$WORKSPACE_HARD_RULES_REGISTRY" <<'PY'
import re
import shlex
import sys
from pathlib import Path

name, registry_path, fallback_doc, skills_path, rules_path = sys.argv[1:]


def clean_scalar(value: str) -> str:
    value = value.strip()
    if (
        (value.startswith('"') and value.endswith('"'))
        or (value.startswith("'") and value.endswith("'"))
        or (value.startswith("`") and value.endswith("`"))
    ):
        return value[1:-1]
    return value


def parse_registry(path: Path):
    if not path.exists():
        return {}
    data = {}
    current = None
    section = None
    for raw in path.read_text().splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()
        if indent == 0 and line.startswith("- id:"):
            current = clean_scalar(line.split(":", 1)[1])
            data[current] = {}
            section = None
            continue
        if current is None:
            continue
        if indent == 2 and line.endswith(":") and line[:-1] in {"git", "deploy"}:
            section = line[:-1]
            continue
        if indent == 2 and ":" in line:
            key, value = line.split(":", 1)
            data[current][key.strip()] = clean_scalar(value)
            section = None
            continue
        if indent >= 4 and section and ":" in line:
            key, value = line.split(":", 1)
            data[current][f"{section}.{key.strip()}"] = clean_scalar(value)
    return data


def parse_fallback(path: Path):
    if not path.exists():
        return {}
    text = path.read_text()
    result = {}
    root_match = re.search(rf"^\s*-\s*(?:`)?{re.escape(name)}(?:`)?\s*->\s*(.+?)\s*$", text, re.M)
    if root_match:
        result["root"] = clean_scalar(root_match.group(1))
    boot_match = re.search(rf"^\|\s*{re.escape(name)}\s*\|\s*([^|]+?)\s*\|", text, re.M)
    if boot_match:
        result["boot_doc"] = clean_scalar(boot_match.group(1))
    return result


def parse_skills(path: Path, prefix: str):
    if not path.exists():
        return []
    skills = []
    for raw in path.read_text().splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        line = raw.strip()
        if line.startswith("- name:") or line.startswith("- id:"):
            name_value = clean_scalar(line.split(":", 1)[1])
            if name_value.startswith(prefix):
                skills.append(name_value)
    # De-duplicate while preserving order.
    seen = set()
    ordered = []
    for skill in skills:
        if skill not in seen:
            seen.add(skill)
            ordered.append(skill)
    return ordered


def parse_rules(path: Path):
    if not path.exists():
        return []
    rules = []
    current = {}
    for raw in path.read_text().splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()
        if indent == 0 and line.startswith("- id:"):
            if current.get("enforcement") == "blocking" and current.get("rule") and current["rule"] != "TODO":
                rules.append(current["rule"])
            current = {"id": clean_scalar(line.split(":", 1)[1])}
            continue
        if ":" in line:
            key, value = line.split(":", 1)
            current[key.strip()] = clean_scalar(value)
    if current.get("enforcement") == "blocking" and current.get("rule") and current["rule"] != "TODO":
        rules.append(current["rule"])
    return rules


registry = parse_registry(Path(registry_path))
meta = registry.get(name, {})
fallback = parse_fallback(Path(fallback_doc))

root = meta.get("root") or fallback.get("root")
if not root:
    sys.stderr.write(
        f"Error: unknown workspace '{name}'. Looked in {registry_path} and the Workspace Map in {fallback_doc}.\n"
    )
    raise SystemExit(2)

boot_doc = meta.get("boot_doc") or fallback.get("boot_doc") or "TODO"
docs_index = meta.get("docs_index") or "TODO"
skills_prefix = meta.get("skills_prefix") or name
skills = parse_skills(Path(skills_path), skills_prefix)
git_enabled = (meta.get("git.is_repo") or "").lower() in {"yes", "true", "1"}
main_branch = meta.get("git.main_branch") or ""
rollback = "git reset --hard HEAD"
if git_enabled and main_branch and main_branch != "TODO":
    rollback = f"git reset --hard origin/{main_branch}"
hard_rules = parse_rules(Path(rules_path))

def emit(key, value):
    print(f"{key}={shlex.quote(value)}")

emit("ROOT", root)
emit("BOOT_DOC", boot_doc)
emit("DOCS_INDEX", docs_index)
emit("SCRATCH", f"{root.rstrip('/')}/logs/runtime")
emit("AVAILABLE_SKILLS", ",".join(skills))
emit("GIT", "yes" if git_enabled else "no")
emit("ROLLBACK", rollback)
emit("HARD_RULES", "\n".join(hard_rules))
PY
}

inject_workspace_context() {
    local ws="$1"
    local prompt_file="$2"

    [ -f "$prompt_file" ] || return 1
    if grep -q '^# Workspace context (do not modify or echo back)$' "$prompt_file"; then
        return 0
    fi

    local meta
    meta="$(_workspace_meta "$ws")"
    eval "$meta"

    local tmp_file
    tmp_file="${prompt_file}.workspace.$$"

    {
        printf '# Workspace context (do not modify or echo back)\n'
        printf 'Workspace: %s\n' "$ws"
        printf 'Root: %s\n' "$ROOT"
        printf 'Boot doc: %s/%s\n' "$ROOT" "$BOOT_DOC"
        printf 'Docs index: %s/%s\n' "$ROOT" "$DOCS_INDEX"
        printf 'Scratch: %s/\n' "$SCRATCH"
        printf 'Available skills: %s\n' "$AVAILABLE_SKILLS"
        printf 'Git: %s' "$GIT"
        if [ "$GIT" = "yes" ]; then
            printf ' (rollback: %s)\n' "$ROLLBACK"
        else
            printf '\n'
        fi
        printf 'Hard rules:\n'
        while IFS= read -r rule; do
            [ -z "$rule" ] && continue
            printf '  - %s\n' "$rule"
        done <<< "$HARD_RULES"
        printf '\n---\n'
        cat "$prompt_file"
    } > "$tmp_file"

    mv "$tmp_file" "$prompt_file"
}
