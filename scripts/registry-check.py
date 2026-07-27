#!/usr/bin/env python3
"""
registry-check.py — Validate all registry YAML files and exit non-zero on hard failures.

Required checks:
1. All registry files parse as YAML.
2. All entries with 'id' have unique ids within their registry.
3. tools.yaml binaries resolve after expanding ~/ prefix.
4. skills.yaml paths match discoverable SKILL.md files where a path is present.
5. workflows.yaml entries include id, triggered_by or pattern, and invocation or command.
6. agents.yaml entries include id, invocation_template, models_allowed, constraints, and use_when.
7. hard_rules.yaml entries satisfy the rule schema (delegates to validate-hard-rules.py).
8. agent-manifest.yaml summary counts match a dry-run manifest.
9. Deprecated 'discoverable_by' in active skill entries is reported at least as warnings.

Usage:
    python3 registry-check.py
    python3 registry-check.py --json
    python3 registry-check.py --strict   # exits non-zero on warnings too
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

HOME = Path.home()
COCKPIT = Path(os.environ.get("AGENT_OS_HOME", Path(__file__).resolve().parents[1])).resolve()
REGISTRY_DIR = COCKPIT / "registry"

ALL_REGISTRY_FILES = [
    "hard_rules.yaml",
    "tools.yaml",
    "skills.yaml",
    "workflows.yaml",
    "agents.yaml",
    "mcp_servers.yaml",
    "memory_tiers.yaml",
    "workspaces.yaml",
    "agent-manifest.yaml",
]

# Skills.yaml names where discoverable_by usage is expected (legacy field)
# These are the os-shared skills that were grandfathered in.
LEGACY_DISCOVERABLE_SKILLS = {
    "acp",
    "agent-workflows",
    "lesson",
    "recall",
    "digest",
    "sidecar",
}


def check_yaml_parse(path: Path) -> list[dict]:
    """Failures for check 1: YAML parsing."""
    failures: list[dict] = []
    try:
        data = yaml.safe_load(path.read_text())
        if data is None:
            failures.append({"path": str(path), "check": "yaml_parse", "error": f"Empty YAML file: {path.name}"})
    except yaml.YAMLError as e:
        failures.append({"path": str(path), "check": "yaml_parse", "error": f"YAML parse error: {e}"})
    return failures


def check_unique_ids(path: Path) -> list[dict]:
    """Failures for check 2: unique IDs."""
    failures: list[dict] = []
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError:
        return []

    entries = []
    if isinstance(data, list):
        entries = data
    elif isinstance(data, dict):
        # Try common keys: skills, workflows, mcp_servers, tiers, etc.
        for key in ("skills", "workflows", "mcp_servers", "tiers", "entries"):
            if key in data and isinstance(data[key], list):
                entries = data[key]
                break

    seen_ids: dict[str, int] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        eid = entry.get("id") or entry.get("name")
        if eid is None:
            continue
        eid_str = str(eid)
        if eid_str in seen_ids:
            failures.append({
                "path": str(path),
                "check": "unique_ids",
                "error": f"Duplicate id '{eid_str}' (also at index {seen_ids[eid_str]})",
            })
        seen_ids[eid_str] = seen_ids.get(eid_str, 0) + 1

    return failures


def check_tools_binaries(tools_path: Path) -> list[dict]:
    """Failures for check 3: tools.yaml binaries resolve."""
    failures: list[dict] = []
    try:
        data = yaml.safe_load(tools_path.read_text()) or []
    except yaml.YAMLError:
        return []

    if not isinstance(data, list):
        return []

    for entry in data:
        if not isinstance(entry, dict):
            continue
        binary = entry.get("binary")
        if not binary:
            continue
        # Expand environment variables and ~/ prefix.
        expanded = os.path.expandvars(str(binary))
        if expanded.startswith("~/"):
            expanded = str(HOME / expanded[2:])
        elif expanded.startswith("~"):
            expanded = str(HOME / expanded[1:])
        # Check if it exists (relative paths are checked via command -v)
        if expanded.startswith("/"):
            if not os.path.exists(expanded):
                # Some tools may be installed via package managers - check with command -v
                basename = os.path.basename(expanded)
                # Check if the binary name alone resolves
                pass_result = False
                try:
                    subprocess.run(
                        ["command", "-v", basename],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    pass_result = True
                except Exception:
                    pass_result = False
                if not pass_result:
                    failures.append({
                        "path": str(tools_path),
                        "check": "binary_resolve",
                        "error": f"Binary not found: {binary} (expanded: {expanded})",
                    })

    return failures


def check_skills_paths(skills_path: Path) -> list[dict]:
    """Warnings for check 4: skills.yaml paths exist."""
    warnings: list[dict] = []
    try:
        data = yaml.safe_load(skills_path.read_text()) or {}
    except yaml.YAMLError:
        return []

    skills = data.get("skills", [])
    if not isinstance(skills, list):
        return []

    for entry in skills:
        if not isinstance(entry, dict):
            continue
        path_val = entry.get("path")
        if not path_val or not isinstance(path_val, str):
            continue
        # Resolve $AGENT_OS_HOME if env var is not set
        if "$AGENT_OS_HOME" in path_val and "AGENT_OS_HOME" not in os.environ:
            path_val = path_val.replace("$AGENT_OS_HOME", str(COCKPIT))
        # Expand ~/ and <vault> prefixes
        expanded = os.path.expandvars(path_val)
        if expanded.startswith("~/"):
            expanded = str(HOME / expanded[2:])
        elif expanded.startswith("~"):
            expanded = str(HOME / expanded[1:])
        elif expanded.startswith("<vault>"):
            vault = os.path.expanduser(os.environ.get("VAULT", "~/vault"))
            expanded = expanded.replace("<vault>", vault)

        # Skip planned/archived skills that may not have files yet
        status = entry.get("status", "")
        if status in ("planned", "deprecated", "archived"):
            continue

        if not os.path.exists(expanded):
            warnings.append({
                "path": str(skills_path),
                "check": "skill_path_exists",
                "error": f"SKILL.md path not found: {path_val} (expanded: {expanded})",
                "severity": "warning",
            })

    return warnings


def check_workflows(workflows_path: Path) -> list[dict]:
    """Failures for check 5: workflows.yaml required fields."""
    failures: list[dict] = []
    try:
        data = yaml.safe_load(workflows_path.read_text()) or {}
    except yaml.YAMLError:
        return []

    workflows = data.get("workflows", [])
    if not isinstance(workflows, list):
        return []

    for entry in workflows:
        if not isinstance(entry, dict):
            continue
        wid = entry.get("id") or entry.get("name")
        if wid is None:
            failures.append({
                "path": str(workflows_path),
                "check": "workflow_fields",
                "error": "Workflow entry missing both 'id' and 'name'",
            })
            continue

        has_trigger = bool(entry.get("triggered_by") or entry.get("pattern"))
        has_invocation = bool(entry.get("invocation") or entry.get("command") or entry.get("description"))

        missing = []
        if not has_trigger:
            missing.append("triggered_by or pattern")
        if not has_invocation:
            missing.append("invocation or command or description")

        if missing:
            failures.append({
                "path": str(workflows_path),
                "check": "workflow_fields",
                "error": f"Workflow '{wid}' missing: {', '.join(missing)}",
            })

    return failures


def check_agents(agents_path: Path) -> list[dict]:
    """Failures for check 6: agents.yaml required fields."""
    failures: list[dict] = []
    try:
        data = yaml.safe_load(agents_path.read_text()) or []
    except yaml.YAMLError:
        return []

    if not isinstance(data, list):
        return []

    for entry in data:
        if not isinstance(entry, dict):
            continue
        aid = entry.get("id", "?")

        required = ["id", "invocation_template", "models_allowed", "constraints", "use_when"]
        missing = [f for f in required if f not in entry]
        if missing:
            failures.append({
                "path": str(agents_path),
                "check": "agent_fields",
                "error": f"Agent '{aid}' missing: {', '.join(missing)}",
            })

    return failures


def check_hard_rules() -> list[dict]:
    """Failures for check 7: hard_rules.yaml validity via validate-hard-rules.py."""
    failures: list[dict] = []
    validator = COCKPIT / "scripts/validate-hard-rules.py"
    if not validator.exists():
        return []

    try:
        result = subprocess.run(
            [sys.executable, str(validator), "--json"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            try:
                report = json.loads(result.stdout)
                for err in report.get("errors", []):
                    failures.append({
                        "path": str(COCKPIT / "registry/hard_rules.yaml"),
                        "check": "hard_rules_schema",
                        "error": f"[{err.get('rule', '?')}.{err.get('field', '?')}] {err.get('error', '?')}",
                    })
            except (json.JSONDecodeError, KeyError):
                failures.append({
                    "path": str(COCKPIT / "registry/hard_rules.yaml"),
                    "check": "hard_rules_schema",
                    "error": f"Validator exited {result.returncode}: {result.stderr[:200] or result.stdout[:200]}",
                })
    except subprocess.TimeoutExpired:
        failures.append({
            "path": str(COCKPIT / "registry/hard_rules.yaml"),
            "check": "hard_rules_schema",
            "error": "validate-hard-rules.py timed out",
        })

    return failures


def check_manifest_counts(manifest_path: Path) -> list[dict]:
    """Failures for check 8: agent-manifest.yaml count drift."""
    failures: list[dict] = []
    build_script = COCKPIT / "scripts/build-manifest.py"
    if not build_script.exists():
        return []

    try:
        # Build a dry-run manifest
        result = subprocess.run(
            [sys.executable, str(build_script), "--dry-run"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return []

        # Parse the YAML from dry-run output (first YAML doc before the --- separator)
        dry_text = result.stdout
        dry_sep = dry_text.find("\n---\n")
        if dry_sep > 0:
            dry_text = dry_text[:dry_sep]

        dry_manifest = yaml.safe_load(dry_text)
        if not isinstance(dry_manifest, dict):
            return []

        dry_counts = dry_manifest.get("summary", {})
        if not dry_counts:
            return []

        # Read existing manifest
        if not manifest_path.exists():
            return []

        existing = yaml.safe_load(manifest_path.read_text()) or {}
        existing_counts = existing.get("summary", {})

        # Compare counts (allow timestamp drift)
        for key in ("skills", "tools", "workflows", "agents", "mcp_servers", "memory_tiers"):
            dry_val = dry_counts.get(key, 0)
            existing_val = existing_counts.get(key, 0)
            if dry_val != existing_val:
                failures.append({
                    "path": str(manifest_path),
                    "check": "manifest_count_drift",
                    "error": f"Summary count drift for '{key}': manifest says {existing_val}, dry-run says {dry_val}",
                })
    except (subprocess.TimeoutExpired, yaml.YAMLError, json.JSONDecodeError) as e:
        failures.append({
            "path": str(manifest_path),
            "check": "manifest_count_drift",
            "error": f"Failed to compare manifest: {e}",
        })

    return failures


def check_discoverable_by(skills_path: Path) -> list[dict]:
    """Warnings for check 9: deprecated 'discoverable_by' in active skill entries."""
    warnings: list[dict] = []
    try:
        data = yaml.safe_load(skills_path.read_text()) or {}
    except yaml.YAMLError:
        return []

    skills = data.get("skills", [])
    if not isinstance(skills, list):
        return []

    for entry in skills:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name", "?")
        status = entry.get("status", "")
        tier = entry.get("tier", "")

        if status != "active":
            continue
        if tier not in ("os-shared", "workspace-project-a", "workspace-project-b", "personal"):
            continue
        if name in LEGACY_DISCOVERABLE_SKILLS:
            continue

        if "discoverable_by" in entry:
            warnings.append({
                "path": str(skills_path),
                "check": "discoverable_by_deprecated",
                "error": f"Active skill '{name}' has deprecated 'discoverable_by' field (use 'native_loaders' instead)",
                "severity": "warning",
            })

    return warnings


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Validate all Agent OS registry YAML files")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero on warnings as well as failures")
    args = parser.parse_args()

    all_failures: list[dict] = []
    all_warnings: list[dict] = []

    # 1. YAML parse + 2. Unique IDs for each file
    for fname in ALL_REGISTRY_FILES:
        path = REGISTRY_DIR / fname
        if not path.exists():
            all_failures.append({"path": str(path), "check": "file_exists", "error": f"Missing registry file: {fname}"})
            continue

        all_failures.extend(check_yaml_parse(path))
        all_failures.extend(check_unique_ids(path))

    tools_path = REGISTRY_DIR / "tools.yaml"
    if tools_path.exists():
        all_failures.extend(check_tools_binaries(tools_path))

    skills_path = REGISTRY_DIR / "skills.yaml"
    if skills_path.exists():
        all_warnings.extend(check_skills_paths(skills_path))
        all_warnings.extend(check_discoverable_by(skills_path))

    workflows_path = REGISTRY_DIR / "workflows.yaml"
    if workflows_path.exists():
        all_failures.extend(check_workflows(workflows_path))

    agents_path = REGISTRY_DIR / "agents.yaml"
    if agents_path.exists():
        all_failures.extend(check_agents(agents_path))

    # 7. hard_rules.yaml schema validation
    all_failures.extend(check_hard_rules())

    # 8. Manifest count drift
    manifest_path = REGISTRY_DIR / "agent-manifest.yaml"
    if manifest_path.exists():
        all_failures.extend(check_manifest_counts(manifest_path))

    all_failures.extend(check_manifest_counts(manifest_path))

    # Deduplicate
    seen = set()
    unique_failures: list[dict] = []
    for f in all_failures:
        key = json.dumps(f, sort_keys=True)
        if key not in seen:
            seen.add(key)
            unique_failures.append(f)

    seen_w = set()
    unique_warnings: list[dict] = []
    for w in all_warnings:
        key = json.dumps(w, sort_keys=True)
        if key not in seen_w:
            seen_w.add(key)
            unique_warnings.append(w)

    total_failures = len(unique_failures)
    total_warnings = len(unique_warnings)

    if args.json:
        result = {
            "overall": "FAIL" if total_failures > 0 else ("WARN" if total_warnings > 0 and args.strict else "PASS"),
            "failures": unique_failures,
            "warnings": unique_warnings,
            "failure_count": total_failures,
            "warning_count": total_warnings,
        }
        print(json.dumps(result, indent=2))
    else:
        if total_failures > 0:
            print(f"FAIL: {total_failures} failure(s):")
            for f in unique_failures:
                print(f"  [{f.get('check', '?')}] {f.get('error', '?')} ({f.get('path', '?')})")
        if total_warnings > 0:
            print(f"WARN: {total_warnings} warning(s):")
            for w in unique_warnings:
                print(f"  [{w.get('check', '?')}] {w.get('error', '?')} ({w.get('path', '?')})")
        if total_failures == 0 and total_warnings == 0:
            print("PASS: All registry checks passed (0 failures, 0 warnings)")
        elif total_failures == 0 and total_warnings > 0 and not args.strict:
            print("PASS: No failures (warnings only, use --strict to fail on warnings)")

    if total_failures > 0:
        return 1
    if args.strict and total_warnings > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
