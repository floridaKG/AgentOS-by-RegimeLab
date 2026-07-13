#!/usr/bin/env python3
"""
Skill Health Review — LLM-driven staleness check for Agent OS skills.

Walks three non-bundled skill roots, asks a cheap LLM to flag staleness per
skill, and writes a triage report. Stamps last_reviewed in frontmatter so
repeat sweeps can skip recent work.

Spec: $AGENT_OS_HOME/docs/specs/active/2026-06-13-skill-health-review.md
"""

import argparse
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_AOH = os.environ.get("AGENT_OS_HOME") or os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STATE_DIR = Path.home() / ".local" / "state" / "agent-os" / "skill-health"
REPORTS_DIR = STATE_DIR / "runs"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
RUN_LOG = STATE_DIR / "runs.jsonl"
PATCHES_DIR = STATE_DIR / "patches"

DEFAULT_MODEL = "opencode/deepseek-v4-flash-free"
DEFAULT_COOLDOWN_DAYS = 30

_state_dir = os.environ.get('AGENT_STATE_DIR', '.agent-os')
BUNDLED_PATHS = [
    Path.home() / _state_dir / "agent" / "skills",
    Path.home() / ".codex" / "skills" / ".system",
    Path.home() / ".codex" / "plugins" / "cache",
]

SKILL_ROOTS = [
    Path.home() / _state_dir / "skills",
    Path.home() / "agent-os" / "skills" / "shared",
]

# Workspace roots to scan for skills (walked recursively for SKILL.md)
WORKSPACE_ROOTS = [
    Path(os.environ.get('PROJECT_A', f"{_AOH}/workspace-project-a")),
    Path(os.environ.get('PROJECT_B', f"{_AOH}/workspace-project-b")),
    Path(os.path.expanduser(os.environ.get("VAULT", "~/vault"))),  # configurable via env
]

SYSTEM_SNAPSHOT_PATHS = [
    Path.home() / "bin",
    Path.home() / _state_dir / "skills",
    Path.home() / "agent-os" / "skills" / "shared",
    Path.home() / "AGENTS.md",
]

REVIEW_PROMPT_TEMPLATE = """\
Review this Agent OS skill against current reality. The skill is part of the Agent OS multi-agent system. Consider whether the file paths, tools, and patterns it references are current and accurate.

Return ONLY a JSON object (no markdown fences, no extra text) with this shape:
{{
  "verdict": "ok" | "review" | "fix",
  "issues": [
    {{
      "category": "a" | "b" | "c" | "d" | "e",
      "detail": "one sentence explaining the issue"
    }}
  ],
  "summary": "one-line summary of findings"
}}

Categories:
a = file paths referenced don't exist
b = tools/binaries mentioned aren't installed
c = recommends a pattern that's been superseded
d = contradicts another skill in the same set
e = omits something a reader needs to know to use it correctly

If no issues: {{"verdict": "ok", "issues": [], "summary": "No issues found"}}

--- SYSTEM STATE (file listings) ---
{system_state}

--- SKILL FILE ({skill_path}) ---
{skill_content}
"""

# ---------------------------------------------------------------------------
# Frontmatter helpers
# ---------------------------------------------------------------------------

FRONTMATTER_RE = re.compile(
    r"^(---\s*\n)(.*?\n)(---\s*\n)", re.DOTALL
)


def parse_frontmatter(content: str) -> Tuple[Dict[str, str], str]:
    """Return (frontmatter_dict, body). If no frontmatter, return ({}, content)."""
    m = FRONTMATTER_RE.match(content)
    if not m:
        return {}, content

    raw = m.group(2)
    fm: Dict[str, str] = {}
    for line in raw.splitlines():
        if ":" in line:
            key, val = line.split(":", 1)
            fm[key.strip()] = val.strip()
    body = content[m.end():]
    return fm, body


def set_last_reviewed(content: str, today: str) -> str:
    """Insert or update last_reviewed in frontmatter. Returns full file content."""
    m = FRONTMATTER_RE.match(content)
    if m:
        raw = m.group(2)
        lines = raw.splitlines()
        updated = False
        new_lines = []
        for line in lines:
            if line.startswith("last_reviewed:"):
                new_lines.append(f"last_reviewed: {today}")
                updated = True
            else:
                new_lines.append(line)
        if not updated:
            new_lines.append(f"last_reviewed: {today}")
        new_fm = "\n".join(new_lines)
        return m.group(1) + new_fm + "\n" + m.group(3) + content[m.end():]
    else:
        # No frontmatter — prepend a block
        return f"---\nlast_reviewed: {today}\n---\n{content}"


# ---------------------------------------------------------------------------
# Skill walking
# ---------------------------------------------------------------------------

def is_bundled(path: Path) -> bool:
    """Check if a path is under generated/system bundled skill roots."""
    resolved = path.resolve()
    for bundled_path in BUNDLED_PATHS:
        try:
            resolved.relative_to(bundled_path.resolve())
            return True
        except ValueError:
            continue
    return False


def walk_skills(roots: List[Path]) -> List[Path]:
    """Walk roots non-recursively for skill directories containing SKILL.md or DESCRIPTION.md."""
    skills = []
    for root in roots:
        if not root.exists():
            continue
        for entry in sorted(root.iterdir()):
            if not entry.is_dir():
                continue
            if is_bundled(entry):
                continue
            # Look for SKILL.md or DESCRIPTION.md
            for name in ("SKILL.md", "DESCRIPTION.md"):
                fpath = entry / name
                if fpath.exists():
                    skills.append(fpath)
                    break
    return skills


def walk_workspace_skills(workspace_roots: List[Path]) -> List[Path]:
    """Walk workspace roots for SKILL.md files."""
    skills = []
    for ws_root in workspace_roots:
        if not ws_root.exists():
            continue
        # Check for a skills/ subdirectory
        skills_dir = ws_root / "skills"
        if skills_dir.exists():
            for fpath in skills_dir.rglob("SKILL.md"):
                skills.append(fpath)
        # Also check direct SKILL.md in workspace root
        root_skill = ws_root / "SKILL.md"
        if root_skill.exists():
            skills.append(root_skill)
    return skills


def discover_all_skills(extra_roots: Optional[List[Path]] = None) -> List[Path]:
    """Discover all in-scope skills."""
    all_skills = []
    all_skills.extend(walk_skills(SKILL_ROOTS))
    all_skills.extend(walk_workspace_skills(WORKSPACE_ROOTS))
    if extra_roots:
        all_skills.extend(walk_skills(extra_roots))
    # Deduplicate by resolved path
    seen = set()
    unique = []
    for s in all_skills:
        resolved = s.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(s)
    return unique


# ---------------------------------------------------------------------------
# System state snapshot
# ---------------------------------------------------------------------------

def build_system_state() -> str:
    """Build a compact system state snapshot for the LLM prompt."""
    lines = []
    for p in SYSTEM_SNAPSHOT_PATHS:
        if not p.exists():
            continue
        if p.is_dir():
            entries = sorted([e.name for e in p.iterdir() if e.is_file()][:50])
            lines.append(f"[{p}]")
            lines.extend(f"  {e}" for e in entries)
        elif p.is_file():
            lines.append(f"[{p}]")
            try:
                text = p.read_text(errors="replace")[:2000]
                lines.append(text)
            except Exception:
                lines.append("  (unreadable)")

    # Add model freshness info for category "b" expansion (SH-3 integration)
    try:
        oc_result = subprocess.run(
            ["opencode", "models"],
            capture_output=True, text=True, timeout=15,
        )
        if oc_result.returncode == 0:
            oc_models = [l.strip() for l in oc_result.stdout.splitlines()
                         if l.strip() and not l.startswith(("Available", "-"))]
            lines.append("[opencode models — live catalog]")
            # Include key model families rather than all 650+
            key_models = [m for m in oc_models if any(
                m.startswith(p) for p in ("opencode/", "opencode-go/", "google/gemini", "custom:")
            )]
            lines.extend(f"  {m}" for m in key_models[:40])
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# LLM call
# ---------------------------------------------------------------------------

def _extract_balanced_json(text: str) -> Optional[str]:
    """Return the first complete brace-balanced {...} substring, or None.

    String- and escape-aware so braces inside quoted values don't throw the
    depth count off. Handles nested objects/arrays (the real review payload
    nests issues: [{...}]), which the prior flat regexes could not.
    """
    return next(_iter_balanced_json(text), None)


def _iter_balanced_json(text: str):
    """Yield complete brace-balanced {...} substrings in order."""
    start_at = 0
    while True:
        start = text.find("{", start_at)
        if start == -1:
            return
        depth = 0
        in_str = False
        escaped = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    yield text[start:i + 1]
                    start_at = i + 1
                    break
        else:
            return


def call_llm(skill_path: Path, skill_content: str, system_state: str,
             model: str, timeout: int = 120) -> Dict[str, Any]:
    """Call opencode run with the skill content and parse the JSON response."""
    prompt = REVIEW_PROMPT_TEMPLATE.format(
        system_state=system_state,
        skill_path=str(skill_path),
        skill_content=skill_content[:15000],  # cap to avoid token overflow
    )

    try:
        result = subprocess.run(
            [
                "opencode", "run",
                "--model", model,
                "--format", "json",
            ],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {
            "verdict": "unreviewed",
            "issues": [{"category": "b", "detail": f"LLM call timed out after {timeout}s"}],
            "summary": "LLM call timed out",
        }
    except Exception as e:
        return {
            "verdict": "unreviewed",
            "issues": [{"category": "b", "detail": f"LLM call failed: {e}"}],
            "summary": f"LLM call error: {e}",
        }

    if result.returncode != 0:
        stderr = result.stderr.strip()[:500] if result.stderr else "no stderr"
        return {
            "verdict": "unreviewed",
            "issues": [{"category": "b", "detail": f"LLM exited {result.returncode}: {stderr}"}],
            "summary": f"LLM call failed (exit {result.returncode})",
        }

    # Parse the JSON events from opencode --format json
    # Collect all text events (LLM may emit multiple, with tool calls in between)
    all_texts = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
            if event.get("type") == "text":
                text = event.get("part", {}).get("text", "")
                if text:
                    all_texts.append(text)
        except json.JSONDecodeError:
            continue

    # Use the last text event (final answer)
    extracted_text = all_texts[-1] if all_texts else result.stdout.strip()

    # Try to find JSON in the extracted text
    # Strategy 1: try parsing as-is
    # Strategy 2: extract from markdown fences
    # Strategy 3: find JSON object in the text via regex
    cleaned = extracted_text.strip()

    # Strip markdown fences if present
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        # Find opening and closing fences
        start = 0
        end = len(lines)
        for i, l in enumerate(lines):
            if l.strip().startswith("```"):
                if start == 0:
                    start = i + 1
                else:
                    end = i
                    break
        cleaned = "\n".join(lines[start:end]).strip()

    # Try parsing
    try:
        parsed = json.loads(cleaned)
        if "verdict" not in parsed:
            parsed["verdict"] = "unreviewed"
        if "issues" not in parsed:
            parsed["issues"] = []
        if "summary" not in parsed:
            parsed["summary"] = "No summary provided"
        return parsed
    except json.JSONDecodeError:
        pass

    # Strategy: brace-balanced extraction. The real payload nests
    # (issues: [{...}]), so the old `\{[^{}]*\}` / `\{.*?\}` regexes could
    # never match it — they stop at the first inner brace. Scan from the
    # first '{', tracking depth and string/escape state, and parse the first
    # complete top-level object.
    for candidate in _iter_balanced_json(extracted_text):
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                if "verdict" not in parsed:
                    continue
                if "issues" not in parsed:
                    parsed["issues"] = []
                if "summary" not in parsed:
                    parsed["summary"] = "No summary provided"
                return parsed
        except json.JSONDecodeError:
            continue

    return {
        "verdict": "unreviewed",
        "issues": [{"category": "e", "detail": f"LLM returned non-JSON: {extracted_text[:300]}"}],
        "summary": "JSON parse failure",
    }


# ---------------------------------------------------------------------------
# Run log
# ---------------------------------------------------------------------------

def log_run(skill_path: str, verdict: str, issue_count: int) -> None:
    """Append a run log entry."""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "path": skill_path,
        "verdict": verdict,
        "issue_count": issue_count,
    }
    with open(RUN_LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

VERDICT_ORDER = {"fix": 0, "review": 1, "ok": 2, "unreviewed": 3, "frontmatter_uneditable": 4}


def generate_report(results: List[Dict[str, Any]], skipped: List[Dict[str, Any]],
                    model: str, cooldown_days: int, force: bool) -> str:
    """Generate the markdown triage report."""
    now = datetime.now()
    lines = []
    lines.append(f"# Skill Health Report")
    lines.append(f"")
    lines.append(f"- **Date:** {now.strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"- **Model:** {model}")
    lines.append(f"- **Cooldown:** {cooldown_days} days")
    lines.append(f"- **Force:** {force}")
    lines.append(f"- **Skills reviewed:** {len(results)}")
    lines.append(f"- **Skills skipped:** {len(skipped)}")
    lines.append(f"")

    # Sort results by verdict
    sorted_results = sorted(results, key=lambda r: VERDICT_ORDER.get(r.get("verdict", "unreviewed"), 99))

    for r in sorted_results:
        verdict = r.get("verdict", "unreviewed")
        emoji = {"fix": "🔴", "review": "🟡", "ok": "🟢", "unreviewed": "⚪", "frontmatter_uneditable": "🟠"}.get(verdict, "⚪")
        lines.append(f"## {emoji} {r['name']}")
        lines.append(f"")
        lines.append(f"- **Path:** `{r['path']}`")
        lines.append(f"- **Verdict:** {verdict}")
        lines.append(f"- **Summary:** {r.get('summary', 'N/A')}")
        if r.get("fm_warning"):
            lines.append(f"- **⚠️ Frontmatter:** {r['fm_warning']}")
        if r.get("issues"):
            lines.append(f"- **Issues:**")
            for issue in r["issues"]:
                lines.append(f"  - [{issue.get('category', '?')}] {issue.get('detail', 'N/A')}")
        lines.append(f"- **Suggested action:**", )
        if verdict == "fix":
            lines.append(f"  - Patch this skill to fix the issues above")
        elif verdict == "review":
            lines.append(f"  - Read through and verify accuracy")
        elif verdict == "ok":
            lines.append(f"  - No action needed")
        elif verdict == "unreviewed":
            lines.append(f"  - LLM call failed; retry manually with `skill-health review`")
        elif verdict == "frontmatter_uneditable":
            lines.append(f"  - Check file permissions; skill was reviewed but timestamp not saved")
        lines.append(f"")

    if skipped:
        lines.append(f"## ⏭️ Skipped (in cooldown)")
        lines.append(f"")
        for s in skipped:
            days_left = cooldown_days - s.get("days_since_review", 0)
            lines.append(f"- `{s['name']}` — last reviewed {s['last_reviewed']} ({days_left}d remaining)")
        lines.append(f"")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Patch generation
# ---------------------------------------------------------------------------

PATCH_PROMPT_TEMPLATE = """\
You are a skill maintenance agent. Review this Agent OS skill against current reality, then produce a corrected version.

The skill is part of the Agent OS multi-agent system. Consider whether the file paths, tools, and patterns it references are current and accurate.

Return ONLY a JSON object (no markdown fences, no extra text) with this shape:
{{
  "issues": [
    {{
      "category": "a" | "b" | "c" | "d" | "e",
      "detail": "one sentence explaining the issue"
    }}
  ],
  "summary": "one-line summary of changes",
  "corrected_content": "the FULL corrected file content, preserving or updating frontmatter appropriately"
}}

Categories:
a = file paths referenced don't exist
b = tools/binaries mentioned aren't installed
c = recommends a pattern that's been superseded
d = contradicts another skill in the same set
e = omits something a reader needs to know to use it correctly

If no changes needed, set corrected_content to exactly the original content.

IMPORTANT:
- Preserve frontmatter (--- blocks), updating only what needs fixing.
- Keep the same overall structure and style.
- The corrected_content will replace the entire file, so include everything.

--- SYSTEM STATE (file listings) ---
{system_state}

--- SKILL FILE ({skill_path}) ---
{skill_content}
"""


def verify_patch_content(content: str) -> Dict[str, Any]:
    """Verify paths exist and tools are installed in proposed content.

    Returns dict with keys: all_paths_exist, all_tools_installed, warnings.
    """
    warnings = []

    # Find referenced absolute file paths
    path_refs = set()
    for m in re.finditer(r'(?:`|\()\s*(/[^\s`\'")]+)\s*(?:`|\)|,)', content):
        candidate = m.group(1).rstrip("/")
        if candidate.startswith(("/home", "/mnt", "/tmp", "/etc", "/usr")):
            path_refs.add(candidate)

    # Find ~/ paths in backticks
    for m in re.finditer(r'`~([^\s`\'")]+)`', content):
        expanded = str(Path.home()) + m.group(1)
        path_refs.add(expanded)

    missing_paths = []
    for p in sorted(path_refs):
        if not Path(p).exists():
            missing_paths.append(p)

    all_paths_exist = len(missing_paths) == 0
    if missing_paths:
        warnings.append(f"Referenced paths don't exist: {', '.join(missing_paths[:5])}")

    # Find referenced commands/tools (backtick mentions)
    tool_refs = set()
    for m in re.finditer(r'`(\S+)`', content):
        cmd = m.group(1)
        if "/" not in cmd and not cmd.startswith("-") and len(cmd) > 1:
            tool_refs.add(cmd)

    missing_tools = []
    for cmd in sorted(tool_refs):
        if shutil.which(cmd) is None:
            missing_tools.append(cmd)

    all_tools_installed = len(missing_tools) == 0
    if missing_tools:
        warnings.append(f"Referenced tools not in PATH: {', '.join(missing_tools[:5])}")

    return {
        "all_paths_exist": all_paths_exist,
        "all_tools_installed": all_tools_installed,
        "warnings": warnings,
    }


def generate_diff(original: str, proposed: str, filepath: str = "SKILL.md") -> str:
    """Generate a unified diff between original and proposed content."""
    original_lines = original.splitlines(keepends=True)
    proposed_lines = proposed.splitlines(keepends=True)
    diff_lines = list(difflib.unified_diff(
        original_lines, proposed_lines,
        fromfile=f"a/{filepath}",
        tofile=f"b/{filepath}",
        n=3,
    ))
    return "".join(diff_lines)


def call_patch_llm(skill_path: Path, skill_content: str, system_state: str,
                   model: str, timeout: int = 240) -> Dict[str, Any]:
    """Call LLM to produce a patch (corrected skill content)."""
    prompt = PATCH_PROMPT_TEMPLATE.format(
        system_state=system_state,
        skill_path=str(skill_path),
        skill_content=skill_content[:15000],
    )

    try:
        result = subprocess.run(
            ["opencode", "run", "--model", model, "--format", "json"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {"error": f"LLM call timed out after {timeout}s"}
    except Exception as e:
        return {"error": f"LLM call failed: {e}"}

    if result.returncode != 0:
        stderr = result.stderr.strip()[:500] if result.stderr else "no stderr"
        return {"error": f"LLM exited {result.returncode}: {stderr}"}

    # Extract JSON from opencode --format json events
    # The LLM may produce text across multiple steps (initial response + tool calls + summary).
    # Scan ALL text events for valid JSON and take the first complete match.
    all_texts = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
            if event.get("type") == "text":
                text = event.get("part", {}).get("text", "")
                if text:
                    all_texts.append(text)
        except json.JSONDecodeError:
            continue

    # Try to find JSON in each text event, preferring the earliest valid match
    for text_block in all_texts:
        cleaned = text_block.strip()
        # Try direct parse
        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict) and "corrected_content" in parsed:
                if "issues" not in parsed:
                    parsed["issues"] = []
                if "summary" not in parsed:
                    parsed["summary"] = "No summary provided"
                return parsed
        except json.JSONDecodeError:
            pass
        # Try strip fences
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            start, end = 0, len(lines)
            for i, l in enumerate(lines):
                if l.strip().startswith("```"):
                    if start == 0:
                        start = i + 1
                    else:
                        end = i
                        break
            stripped = "\n".join(lines[start:end]).strip()
            try:
                parsed = json.loads(stripped)
                if isinstance(parsed, dict) and "corrected_content" in parsed:
                    if "issues" not in parsed:
                        parsed["issues"] = []
                    if "summary" not in parsed:
                        parsed["summary"] = "No summary provided"
                    return parsed
            except json.JSONDecodeError:
                pass
        # Try balanced JSON extraction
        for candidate in _iter_balanced_json(text_block):
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict) and "corrected_content" in parsed:
                    if "issues" not in parsed:
                        parsed["issues"] = []
                    if "summary" not in parsed:
                        parsed["summary"] = "No summary provided"
                    return parsed
            except json.JSONDecodeError:
                continue

    return {"error": f"Could not parse LLM response as JSON. Raw text events: {len(all_texts)}"}


def save_patch_file(skill_path: Path, proposed_content: str, issues: List[Dict],
                    summary: str, verification: Dict[str, Any],
                    diff: str) -> Path:
    """Save a patch JSON file and return its path."""
    skill_name = skill_path.parent.name
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")

    patch_dir = PATCHES_DIR / skill_name
    patch_dir.mkdir(parents=True, exist_ok=True)

    patch = {
        "version": 1,
        "skill_path": str(skill_path.resolve()),
        "skill_name": skill_name,
        "generated_at": datetime.now().isoformat(),
        "summary": summary,
        "issues": issues,
        "proposed_content": proposed_content,
        "diff": diff,
        "verification": verification,
    }

    patch_file = patch_dir / f"{ts}.patch"
    patch_file.write_text(json.dumps(patch, indent=2), encoding="utf-8")
    return patch_file


def cmd_patch(args: argparse.Namespace) -> int:
    """Generate a proposed patch for a skill."""
    skill_path = Path(args.skill_path).resolve()
    if not skill_path.exists():
        print(f"Error: {skill_path} does not exist", file=sys.stderr)
        return 1

    if skill_path.is_dir():
        for name in ("SKILL.md", "DESCRIPTION.md"):
            candidate = skill_path / name
            if candidate.exists():
                skill_path = candidate
                break
        else:
            print(f"Error: no SKILL.md or DESCRIPTION.md found in {skill_path}", file=sys.stderr)
            return 1

    if is_bundled(skill_path):
        print(f"Error: bundled skills are out of scope: {skill_path}", file=sys.stderr)
        return 1

    print(f"Generating patch for: {skill_path}")
    content = skill_path.read_text(errors="replace")
    model = args.model or DEFAULT_MODEL

    system_state = build_system_state()
    print(f"Calling LLM ({model}) for review + patch generation...")

    result = call_patch_llm(skill_path, content, system_state, model)

    if "error" in result:
        print(f"Error: {result['error']}", file=sys.stderr)
        return 1

    proposed = result.get("corrected_content", "")
    issues = result.get("issues", [])
    summary = result.get("summary", "No summary provided")

    if not proposed.strip():
        print("Error: LLM returned empty corrected_content", file=sys.stderr)
        return 1

    # Generate diff
    diff = generate_diff(content, proposed, skill_path.name)

    # Verify proposed content
    print("Verifying proposed changes...")
    verification = verify_patch_content(proposed)
    if verification["warnings"]:
        for w in verification["warnings"]:
            print(f"  \u26a0 {w}")

    # Save patch file
    patch_path = save_patch_file(skill_path, proposed, issues, summary, verification, diff)

    print(f"\n{'='*60}")
    print(f"Issues found: {len(issues)}")
    for issue in issues:
        print(f"  [{issue.get('category', '?')}] {issue.get('detail', '')}")
    print(f"\nProposed changes:")
    print(diff if diff.strip() else "  (no changes)")
    print(f"\nPatch saved to: {patch_path}")
    print(f"To apply: skill-health apply {patch_path} --confirm")
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    """Apply a verified patch."""
    patch_path = Path(args.patch_path).resolve()
    if not patch_path.exists():
        print(f"Error: patch file not found: {patch_path}", file=sys.stderr)
        return 1

    try:
        patch = json.loads(patch_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print(f"Error: invalid patch file: {patch_path}", file=sys.stderr)
        return 1

    skill_path = Path(patch["skill_path"])
    if not skill_path.exists():
        print(f"Error: target skill no longer exists: {skill_path}", file=sys.stderr)
        return 1

    # Print patch summary
    print(f"Patch: {patch_path}")
    print(f"Target: {skill_path}")
    print(f"Generated: {patch.get('generated_at', 'unknown')}")
    print(f"Summary: {patch.get('summary', 'N/A')}")
    print(f"\nProposed diff:")
    print(patch.get("diff", "(no diff stored)"))

    if patch.get("verification", {}).get("warnings"):
        print(f"\nVerification warnings:")
        for w in patch["verification"]["warnings"]:
            print(f"  \u26a0 {w}")

    # Require --confirm
    if not args.confirm:
        print(f"\n\u26a0 Use --confirm to apply this patch.")
        return 0

    # Save backup
    skill_name = patch["skill_name"]
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    bak_dir = PATCHES_DIR / skill_name
    bak_dir.mkdir(parents=True, exist_ok=True)
    bak_path = bak_dir / f"{ts}.bak"

    original_content = skill_path.read_text(encoding="utf-8")
    bak_path.write_text(original_content, encoding="utf-8")

    # Write patched content
    skill_path.write_text(patch["proposed_content"], encoding="utf-8")

    print(f"\n\u2713 Patch applied.")
    print(f"  Backup: {bak_path}")
    print(f"  To rollback: skill-health rollback {bak_path}")

    # Optionally run skills-sync
    if args.sync:
        print("\nPropagating via skills-sync...")
        subprocess.run(["skills-sync"], capture_output=False)
        print("  skills-sync completed.")
    else:
        print("\n  Note: Run 'skills-sync' to propagate changes to all agent camps.")

    return 0


def cmd_rollback(args: argparse.Namespace) -> int:
    """Rollback a patch using a saved .bak file."""
    bak_path = Path(args.bak_path).resolve()
    if not bak_path.exists():
        print(f"Error: backup file not found: {bak_path}", file=sys.stderr)
        return 1

    if bak_path.suffix != ".bak":
        print(f"Error: not a .bak file: {bak_path}", file=sys.stderr)
        return 1

    skill_name = bak_path.parent.name
    original_content = bak_path.read_text(encoding="utf-8")

    # Try to locate the target skill file
    possible_paths = []
    shared_dir = Path.home() / "agent-os" / "skills" / "shared" / skill_name
    user_skills_dir = Path.home() / _state_dir / "skills" / skill_name
    if (shared_dir / "SKILL.md").exists():
        possible_paths.append(shared_dir / "SKILL.md")
    if (user_skills_dir / "DESCRIPTION.md").exists():
        possible_paths.append(user_skills_dir / "DESCRIPTION.md")
    if (user_skills_dir / "SKILL.md").exists():
        possible_paths.append(user_skills_dir / "SKILL.md")

    if not possible_paths:
        print(f"Error: could not find target skill file for '{skill_name}'", file=sys.stderr)
        print("Backup contains the original content. To restore manually:")
        print(f"  cp {bak_path} <target>")
        return 1

    target = possible_paths[0]

    if not args.confirm:
        print(f"This will restore {target} from backup {bak_path}")
        print(f"Use --confirm to proceed.")
        return 0

    target.write_text(original_content, encoding="utf-8")
    print(f"\u2713 Rolled back {target}")
    print("  Run 'skills-sync' to propagate.")
    return 0


# ---------------------------------------------------------------------------
# Model freshness (SH-3)
# ---------------------------------------------------------------------------

PANELS_TOML = Path.home() / ".config" / "agent-workflows" / "panels.toml"
ROLES_TOML = Path.home() / ".config" / "agent-workflows" / "roles.toml"

MODEL_ID_RE = re.compile(
    r'(?:opencode(?:-go)?/[a-zA-Z0-9][a-zA-Z0-9._-]*|custom:[a-zA-Z0-9._-]+(?:-[a-zA-Z0-9._-]+)*)'
)
# Model IDs do NOT have file extensions like .jsonc, .md, .txt, .yaml, .toml
MODEL_ID_EXT_RE = re.compile(r'\.(jsonc|md|txt|yaml|toml|yml|json|sh|py|bak|patch)$', re.IGNORECASE)


def _extract_toml_value(text: str, key: str) -> List[str]:
    """Extract string values for a given TOML key, handling inline arrays and bare strings."""
    values = []
    for m in re.finditer(rf'^{re.escape(key)}\s*=\s*(.+)$', text, re.MULTILINE):
        val = m.group(1).strip()
        if val.startswith("["):
            # Inline array: ["a", "b", "c"]
            for item in re.finditer(r'"([^"]+)"', val):
                values.append(item.group(1))
        elif val.startswith('"'):
            m2 = re.match(r'"([^"]+)"', val)
            if m2:
                values.append(m2.group(1))
        else:
            # Bare value (no quotes)
            values.append(val.split("#")[0].strip())
    return values


def _is_plausible_model_id(candidate: str) -> bool:
    """Filter out things that match MODEL_ID_RE but aren't actual model IDs."""
    # Reject file paths or URLs with file extensions
    if MODEL_ID_EXT_RE.search(candidate):
        return False
    # Reject things that are clearly paths (contain too many path segments)
    if candidate.startswith("opencode/") and candidate.count("/") > 1:
        return False
    # Reject things that look like file paths in the provider portion
    if candidate.startswith("opencode-go/") and candidate.count("/") > 1:
        return False
    return True


def extract_model_ids_from_panels() -> Dict[str, List[str]]:
    """Parse panels.toml and return {panel_name: [model_ids]}."""
    if not PANELS_TOML.exists():
        return {}
    text = PANELS_TOML.read_text(errors="replace")
    result: Dict[str, List[str]] = {}
    current_panel = None
    for line in text.splitlines():
        m = re.match(r'\[panel\.(.+)\]', line)
        if m:
            current_panel = m.group(1)
            result.setdefault(current_panel, [])
            continue
        if current_panel is None:
            continue
        # Match model IDs in various fields
        for model_m in MODEL_ID_RE.finditer(line):
            mid = model_m.group(0)
            if _is_plausible_model_id(mid):
                result[current_panel].append(mid)
        # Match inline specs like "pi opencode-go/deepseek-v4-flash"
        for spec_m in re.finditer(r'"([a-z]+)\s+(opencode(?:-go)?/[^\s"]+)"', line):
            mid = spec_m.group(2)
            if _is_plausible_model_id(mid):
                result[current_panel].append(mid)
        # Match friendly model names in panel members
        for friendly_m in re.finditer(r'"((?:claude|codex)\s+\S+(?:\s+\S+)?)"', line):
            result[current_panel].append(friendly_m.group(1))
    return result


def extract_model_ids_from_roles() -> Dict[str, List[str]]:
    """Parse roles.toml and return {role_name: [model_ids]}."""
    if not ROLES_TOML.exists():
        return {}
    text = ROLES_TOML.read_text(errors="replace")
    result: Dict[str, List[str]] = {}
    current_role = None
    for line in text.splitlines():
        m = re.match(r'\[(.+)\]', line)
        if m:
            current_role = m.group(1)
            result.setdefault(current_role, [])
            continue
        if current_role is None:
            continue
        # Match model = "value" or model = 'value'
        mm = re.match(r'model\s*=\s*"([^"]+)"', line)
        if mm:
            result[current_role].append(mm.group(1))
    return result


def extract_model_ids_from_skills() -> Dict[str, List[str]]:
    """Scan shared skills for model ID references. Returns {skill_name: [model_ids]}."""
    result: Dict[str, List[str]] = {}
    skills_dir = Path.home() / "agent-os" / "skills" / "shared"
    if not skills_dir.exists():
        return result
    for skill_dir in sorted(skills_dir.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.exists():
            continue
        text = skill_file.read_text(errors="replace")
        found = set()
        for m in MODEL_ID_RE.finditer(text):
            mid = m.group(0)
            if _is_plausible_model_id(mid):
                found.add(mid)
        # Also match bare model names in backticks (like `opus`, `gpt-5.5[high]`)
        for m in re.finditer(r'`([a-zA-Z][a-zA-Z0-9._/-]+(?:\[[a-zA-Z]+\])?)`', text):
            candidate = m.group(1)
            # Filter to likely model IDs (not file paths or commands)
            if candidate.startswith(("opencode", "custom:", "gpt", "opus", "claude", "gemini")):
                found.add(candidate)
        if found:
            result[skill_dir.name] = sorted(found)
    return result


def get_live_opencode_models() -> set:
    """Return set of available model IDs from 'opencode models'."""
    try:
        result = subprocess.run(
            ["opencode", "models"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            models = set()
            for line in result.stdout.splitlines():
                line = line.strip()
                if line and not line.startswith("Available") and not line.startswith("-"):
                    models.add(line)
            return models
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return set()


def get_pi_acpx_models() -> set:
    """Return set of available model IDs from Pi/acpx adapter."""
    try:
        result = subprocess.run(
            ["acpx", "--model", "opencode-go/deepseek-v4-flash",
             "--max-turns", "1", "pi", "exec", "pong"],
            capture_output=True, text=True, timeout=30,
        )
        # Parse the availableModels from the session/new response
        models = set()
        for line in result.stdout.splitlines():
            if '"availableModels"' in line or '"modelId"' in line:
                try:
                    obj = json.loads(line)
                    if isinstance(obj, dict) and "result" in obj:
                        models_list = obj["result"].get("models", {}).get("availableModels", [])
                        for m in models_list:
                            models.add(m.get("modelId", ""))
                except json.JSONDecodeError:
                    continue
        return models
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return set()


def cmd_freshness_check(args: argparse.Namespace) -> int:
    """Check model ID freshness across panels, roles, and skills."""
    print("Skill Health — Model Freshness Check")
    print("=" * 60)

    # Collect model IDs from all sources
    panel_models = extract_model_ids_from_panels()
    role_models = extract_model_ids_from_roles()
    skill_models = extract_model_ids_from_skills()

    # Build reverse map: model_id -> [(source_type, source_name)]
    model_sources: Dict[str, List[Tuple[str, str]]] = {}
    for panel, ids in panel_models.items():
        for mid in ids:
            model_sources.setdefault(mid, []).append(("panel", panel))
    for role, ids in role_models.items():
        for mid in ids:
            model_sources.setdefault(mid, []).append(("role", role))
    for skill, ids in skill_models.items():
        for mid in ids:
            model_sources.setdefault(mid, []).append(("skill", skill))

    if not model_sources:
        print("No model IDs found in any source.")
        return 0

    # Get live models from opencode and Pi/acpx
    print("\n[1/2] Fetching live model catalogs...")
    live_models = get_live_opencode_models()
    print(f"  {len(live_models)} models in opencode catalog")
    pi_models = get_pi_acpx_models()
    if pi_models:
        print(f"  {len(pi_models)} models in Pi/acpx catalog")
    else:
        print("  (Pi/acpx catalog unavailable — opencode-go/* models will be unchecked)")

    # Merge catalogs: opencode-go/ IDs get checked against Pi catalog, others against opencode
    live_models_all = live_models | pi_models

    # Probe each unique model ID
    print("\n[2/2] Cross-referencing model IDs against live catalog...")

    dead_count = 0
    live_count = 0
    unknown_count = 0
    # IDs that are known to be managed externally
    EXTERNAL_IDS = {"opus", "claude", "default", "haiku"}

    # Sort for deterministic output
    print("")
    print(f"  {'MODEL ID':<45} {'STATUS':<12} {'CONSUMERS'}")
    print(f"  {'-'*45} {'-'*12} {'-'*30}")

    for model_id in sorted(model_sources.keys()):
        sources = model_sources[model_id]
        consumer_str = ", ".join(f"{st}:{sn}" for st, sn in sources[:3])
        if len(sources) > 3:
            consumer_str += f" (+{len(sources) - 3} more)"

        # Determine liveness
        if model_id in EXTERNAL_IDS:
            status = "external"
            unknown_count += 1
        elif model_id.startswith("opencode-go/"):
            # Pi/acpx-managed models
            if model_id in pi_models:
                status = "live"
                live_count += 1
            elif pi_models:
                status = "DEAD"
                dead_count += 1
            else:
                status = "unchecked"
                unknown_count += 1
        elif "/" in model_id and not model_id.startswith("custom:"):
            # Provider/model format — check against opencode models
            if model_id in live_models:
                status = "live"
                live_count += 1
            else:
                status = "DEAD"
                dead_count += 1
        elif model_id.startswith("custom:"):
            # Custom models — check against opencode models
            if model_id in live_models:
                status = "live"
                live_count += 1
            else:
                status = "DEAD"
                dead_count += 1
        elif model_id.startswith(("gpt", "claude", "gemini")):
            # API model strings — check against all catalogs
            if model_id in live_models_all:
                status = "live"
                live_count += 1
            else:
                status = "unknown"
                unknown_count += 1
        else:
            # Friendly names like "claude opus high"
            status = "friendly"
            unknown_count += 1

        marker = "\U0001f534" if status == "DEAD" else "\U0001f7e2" if status == "live" else "\u26aa"
        print(f"  {marker} {model_id:<43} {status:<12} {consumer_str}")

    print("")
    print(f"Summary: {live_count} live, {dead_count} dead, {unknown_count} unknown/external")
    print(f"Sources: {len(panel_models)} panels, {len(role_models)} roles, {len(skill_models)} skills")

    if dead_count > 0 and args.model:
        print(f"\n\u2139\ufe0f Use --model {args.model} to probe via live LLM call instead of static check.")

    return 1 if dead_count > 0 else 0


def cmd_freshness_refresh(args: argparse.Namespace) -> int:
    """Propose replacements for dead model IDs."""
    if not args.confirm:
        print("This command will propose replacements for dead model IDs in panels.toml and roles.toml.")
        print(f"Use --confirm to proceed. (Model: {args.model or 'opencode/deepseek-v4-flash-free'})")
        return 0

    # Collect dead model IDs
    panel_models = extract_model_ids_from_panels()
    role_models = extract_model_ids_from_roles()
    live_models = get_live_opencode_models()

    dead_ids = set()
    for panel, ids in panel_models.items():
        for mid in ids:
            if "/" in mid and mid not in live_models and not mid.startswith("custom:"):
                dead_ids.add(mid)
    for role, ids in role_models.items():
        for mid in ids:
            if "/" in mid and mid not in live_models and not mid.startswith("custom:"):
                dead_ids.add(mid)

    if not dead_ids:
        print("No dead model IDs found. Nothing to refresh.")
        return 0

    print(f"Found {len(dead_ids)} dead model IDs. Proposing replacements via LLM...")

    # Build context for the LLM
    dead_list = "\n".join(f"  - {mid}" for mid in sorted(dead_ids))
    live_list = "\n".join(
        f"  - {m}" for m in sorted(live_models)
        if any(prefix in m for prefix in ("opencode/", "opencode-go/"))
    ) or "  (no matching models)"

    prompt = f"""\
I need to replace dead model IDs with live alternatives. Here are the dead IDs and the available model catalog.

DEAD MODEL IDs:
{dead_list}

AVAILABLE MODELS (opencode provider):
{live_list}

For each dead ID, suggest the best replacement from the available models list.
Return ONLY JSON with this shape no extra text:
{{"replacements": [{{"dead_id": "...", "suggested": "...", "reason": "..."}}]}}

Focus on semantic similarity (same provider, similar tier/capability).
"""

    try:
        result = subprocess.run(
            ["opencode", "run", "--model", args.model or "opencode/deepseek-v4-flash-free", "--format", "json"],
            input=prompt, capture_output=True, text=True, timeout=60,
        )
    except subprocess.TimeoutExpired:
        print("Error: LLM call timed out.")
        return 1
    except FileNotFoundError:
        print("Error: 'opencode' not found.")
        return 1

    # Parse response (simplified — just print the suggestions)
    print("\nProposed replacements:")
    print(f"{'Dead ID':<45} {'Suggested':<40} Reason")
    print(f"{'-'*45} {'-'*40} {'-'*30}")
    print("(LLM raw response below)")
    print(result.stdout[:2000] if result.stdout else "(empty response)")

    return 0


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_list(args: argparse.Namespace) -> int:
    """List all discovered skills with last_reviewed dates."""
    skills = discover_all_skills(args.extra_roots)
    if not skills:
        print("No skills found in any in-scope root.")
        return 1

    today = date.today().isoformat()
    for skill in skills:
        content = skill.read_text(errors="replace")
        fm, _ = parse_frontmatter(content)
        lr = fm.get("last_reviewed", "never")
        if lr == "never":
            status = "NEVER REVIEWED"
        else:
            try:
                lr_date = date.fromisoformat(lr)
                days = (date.today() - lr_date).days
                status = f"reviewed {lr} ({days}d ago)"
            except ValueError:
                status = f"reviewed {lr} (unparseable date)"
        print(f"  {skill}  —  {status}")

    print(f"\nTotal: {len(skills)} skills")
    return 0


def cmd_review(args: argparse.Namespace) -> int:
    """Review a single skill."""
    skill_path = Path(args.skill_path).resolve()
    if not skill_path.exists():
        print(f"Error: {skill_path} does not exist", file=sys.stderr)
        return 1

    # If a directory is passed, find the SKILL.md or DESCRIPTION.md inside it
    if skill_path.is_dir():
        for name in ("SKILL.md", "DESCRIPTION.md"):
            candidate = skill_path / name
            if candidate.exists():
                skill_path = candidate
                break
        else:
            print(f"Error: no SKILL.md or DESCRIPTION.md found in {skill_path}", file=sys.stderr)
            return 1

    if is_bundled(skill_path):
        print(f"Error: bundled skills are out of scope: {skill_path}", file=sys.stderr)
        return 1

    print(f"Reviewing: {skill_path}")
    content = skill_path.read_text(errors="replace")
    fm, _ = parse_frontmatter(content)

    # Check frontmatter
    fm_warning = None
    if not fm:
        fm_warning = "No frontmatter found; will append on save"

    system_state = build_system_state()
    model = args.model or DEFAULT_MODEL

    print(f"Calling LLM ({model})...")
    result = call_llm(skill_path, content, system_state, model)

    result["path"] = str(skill_path)
    result["name"] = skill_path.parent.name
    result["fm_warning"] = fm_warning

    # Print result
    verdict = result.get("verdict", "unreviewed")
    emoji = {"fix": "🔴", "review": "🟡", "ok": "🟢"}.get(verdict, "⚪")
    print(f"\n{emoji} Verdict: {verdict}")
    print(f"Summary: {result.get('summary', 'N/A')}")
    if result.get("issues"):
        print("Issues:")
        for issue in result["issues"]:
            print(f"  [{issue.get('category', '?')}] {issue.get('detail', '')}")

    # Update frontmatter only after a real model verdict. "unreviewed" means
    # the LLM path failed, so stamping it would create false freshness.
    if verdict in {"ok", "review", "fix"}:
        today = date.today().isoformat()
        try:
            new_content = set_last_reviewed(content, today)
            skill_path.write_text(new_content)
            print(f"\n✓ Updated last_reviewed to {today}")
        except Exception as e:
            print(f"\n⚠ Could not update frontmatter: {e}")
            result["verdict"] = "frontmatter_uneditable"
            verdict = "frontmatter_uneditable"
    else:
        print("\n⚠ LLM review did not complete; last_reviewed not updated")

    # Log
    log_run(str(skill_path), verdict, len(result.get("issues", [])))

    return 0


def cmd_sweep(args: argparse.Namespace) -> int:
    """Run a full sweep of all in-scope skills."""
    force = args.force
    cooldown_days = args.cooldown_days or DEFAULT_COOLDOWN_DAYS
    model = args.model or DEFAULT_MODEL
    extra_roots = args.extra_roots

    skills = discover_all_skills(extra_roots)
    if not skills:
        print("No skills found in any in-scope root.")
        return 1

    today = date.today().isoformat()
    system_state = build_system_state()

    results = []
    skipped = []
    reviewed_count = 0
    skipped_count = 0

    for skill in skills:
        content = skill.read_text(errors="replace", encoding="utf-8")
        fm, _ = parse_frontmatter(content)

        # Check cooldown
        last_reviewed = fm.get("last_reviewed")
        if not force and last_reviewed:
            try:
                lr_date = date.fromisoformat(last_reviewed)
                days_since = (date.today() - lr_date).days
                if days_since < cooldown_days:
                    skipped.append({
                        "path": str(skill),
                        "name": skill.parent.name,
                        "last_reviewed": last_reviewed,
                        "days_since_review": days_since,
                    })
                    skipped_count += 1
                    continue
            except ValueError:
                pass  # Bad date, review anyway

        # Review
        print(f"Reviewing: {skill.parent.name} ...", end=" ", flush=True)
        fm_warning = None
        if not fm:
            fm_warning = "No frontmatter found; will append on save"

        result = call_llm(skill, content, system_state, model)
        result["path"] = str(skill)
        result["name"] = skill.parent.name
        result["fm_warning"] = fm_warning

        verdict = result.get("verdict", "unreviewed")
        print(f"{verdict}")

        # Update frontmatter only after a real model verdict. "unreviewed"
        # should remain stale so the next sweep retries it.
        if verdict in {"ok", "review", "fix"}:
            try:
                new_content = set_last_reviewed(content, today)
                skill.write_text(new_content, encoding="utf-8")
            except Exception as e:
                print(f"  ⚠ Could not update frontmatter: {e}")
                result["fm_warning"] = f"Frontmatter edit failed: {e}"
                result["verdict"] = "frontmatter_uneditable"
                verdict = "frontmatter_uneditable"

        results.append(result)
        log_run(str(skill), verdict, len(result.get("issues", [])))
        reviewed_count += 1

    # Generate report
    report = generate_report(results, skipped, model, cooldown_days, force)

    # Write report file
    report_name = now_str = datetime.now().strftime("%Y-%m-%d-%H%M")
    report_path = REPORTS_DIR / f"{report_name}.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")

    print(f"\n{'='*60}")
    print(f"Sweep complete: {reviewed_count} reviewed, {skipped_count} skipped")
    print(f"Report: {report_path}")

    # If everything was skipped, write a brief "all in cooldown" report
    if reviewed_count == 0 and skipped_count > 0:
        brief = f"# Skill Health Report — All In Cooldown\n\n"
        brief += f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        brief += f"Cooldown: {cooldown_days} days\n"
        brief += f"All {skipped_count} skills reviewed within the last {cooldown_days} days. Nothing to review.\n"
        brief_path = REPORTS_DIR / f"{report_name}-cooldown.md"
        brief_path.write_text(brief, encoding="utf-8")
        print(f"Brief report (all in cooldown): {brief_path}")

    # AV-5 integration: emit one Agent Voice insight per `fix`-verdict skill.
    # Subsystem source "skill-health", category "skill-staleness" (the new
    # category the AV-5 packet introduces). Confidence scales with issue count
    # (more issues -> higher confidence the skill is broken).
    if getattr(args, "insights_emit", True):
        fix_results = [r for r in results if r.get("verdict") == "fix"]
        if fix_results:
            print(f"\nAgent Voice: emitting {len(fix_results)} insight(s) for fix verdicts...")
            emitted = emit_fix_verdict_insights(fix_results, report_path)
            print(f"Agent Voice: {emitted}/{len(fix_results)} insight(s) emitted.")
        else:
            print("Agent Voice: no fix verdicts, no insights to emit.")

    return 0


def emit_fix_verdict_insights(fix_results: List[Dict[str, Any]],
                              report_path: Path) -> int:
    """Call `agent-voice emit` once per fix-verdict result. Returns the count
    of insights that were successfully emitted (exit 0).

    Each emit is a fresh subprocess; if any one fails, log a warning and
    continue with the rest. This keeps the skill-health sweep robust against
    a transient agent-voice failure.
    """
    if not fix_results:
        return 0
    av_bin = shutil.which("agent-voice")
    if not av_bin:
        # Try the canonical path as a fallback
        candidate = Path(f"{_AOH}/bin/agent-voice")
        if candidate.exists():
            av_bin = str(candidate)
        else:
            print("  warning: agent-voice not on PATH; skipping insight emit",
                  file=sys.stderr)
            return 0

    report_evidence = str(report_path)
    emitted = 0
    for r in fix_results:
        name = r.get("name", "unknown")
        summary = r.get("summary", "no summary")
        issues = r.get("issues", []) or []
        issue_count = len(issues)
        # Confidence scales with issue count
        if issue_count >= 3:
            confidence = "high"
        elif issue_count >= 1:
            confidence = "medium"
        else:
            confidence = "low"

        statement = f"{name}: {summary}"
        # Top issue as an evidence entry (truncate long details)
        evidence = [report_evidence]
        if issues:
            top = issues[0].get("detail", "")
            if top:
                evidence.append(f"top-issue: {top[:200]}")

        try:
            result = subprocess.run(
                [
                    av_bin, "emit",
                    "--source", "skill-health",
                    "--kind", "skill-staleness",
                    "--statement", statement,
                    "--confidence", confidence,
                    "--source-ref", report_evidence,
                    "--tag", "skill-health",
                ] + [arg for ev in evidence for arg in ("--evidence", ev)],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if result.returncode == 0:
                emitted += 1
                print(f"  + {name} (id={result.stdout.strip()}, conf={confidence})")
            else:
                stderr_msg = (result.stderr or "").strip()[:200]
                print(f"  ! {name}: agent-voice emit failed (exit {result.returncode}): {stderr_msg}",
                      file=sys.stderr)
        except subprocess.TimeoutExpired:
            print(f"  ! {name}: agent-voice emit timed out", file=sys.stderr)
        except Exception as e:
            print(f"  ! {name}: agent-voice emit error: {e}", file=sys.stderr)
    return emitted


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Skill Health Review — LLM-driven staleness check for Agent OS skills"
    )
    sub = parser.add_subparsers(dest="command", help="Command to run")

    # list
    p_list = sub.add_parser("list", help="List all discovered skills with last_reviewed dates")
    p_list.add_argument("--skills-root", action="append", dest="extra_roots", type=Path,
                        help="Additional root to scan (can be repeated)")

    # review
    p_review = sub.add_parser("review", help="Review a single skill")
    p_review.add_argument("skill_path", help="Path to skill directory or SKILL.md")
    p_review.add_argument("--model", help=f"LLM model (default: {DEFAULT_MODEL})")

    # sweep
    p_sweep = sub.add_parser("sweep", help="Full sweep of all in-scope skills")
    p_sweep.add_argument("--force", action="store_true", help="Ignore cooldown, re-review everything")
    p_sweep.add_argument("--cooldown-days", type=int, help=f"Cooldown in days (default: {DEFAULT_COOLDOWN_DAYS})")
    p_sweep.add_argument("--model", help=f"LLM model (default: {DEFAULT_MODEL})")
    p_sweep.add_argument("--skills-root", action="append", dest="extra_roots", type=Path,
                         help="Additional root to scan (can be repeated)")
    p_sweep.add_argument(
        "--no-insights-emit",
        dest="insights_emit",
        action="store_false",
        default=True,
        help="Disable AV-5 agent-voice insight emit (default: emit on fix verdicts)",
    )

    # patch
    p_patch = sub.add_parser("patch", help="Generate a proposed patch for a skill with fix verdict")
    p_patch.add_argument("skill_path", help="Path to skill directory or SKILL.md")
    p_patch.add_argument("--model", help=f"LLM model (default: {DEFAULT_MODEL})")

    # apply
    p_apply = sub.add_parser("apply", help="Apply a verified patch")
    p_apply.add_argument("patch_path", help="Path to .patch file")
    p_apply.add_argument("--confirm", action="store_true", help="Confirm patch application")
    p_apply.add_argument("--sync", action="store_true", help="Run skills-sync after applying")

    # rollback
    p_rollback = sub.add_parser("rollback", help="Rollback a patch using a .bak file")
    p_rollback.add_argument("bak_path", help="Path to .bak file")
    p_rollback.add_argument("--confirm", action="store_true", help="Confirm rollback")

    # freshness
    p_freshness = sub.add_parser("freshness", help="Model ID freshness checks across panels, roles, and skills")
    freshness_sub = p_freshness.add_subparsers(dest="freshness_command", help="Freshness subcommand")

    p_fc = freshness_sub.add_parser("check", help="Check model ID freshness")
    p_fc.add_argument("--model", help=f"LLM model for live probe (default: {DEFAULT_MODEL})")

    p_fr = freshness_sub.add_parser("refresh", help="Propose replacements for dead model IDs")
    p_fr.add_argument("--model", help=f"LLM model for suggestions (default: {DEFAULT_MODEL})")
    p_fr.add_argument("--confirm", action="store_true", help="Confirm refresh")

    # help
    sub.add_parser("help", help="Show this help message")

    args = parser.parse_args()

    if args.command == "list":
        return cmd_list(args)
    elif args.command == "review":
        return cmd_review(args)
    elif args.command == "sweep":
        return cmd_sweep(args)
    elif args.command == "patch":
        return cmd_patch(args)
    elif args.command == "apply":
        return cmd_apply(args)
    elif args.command == "rollback":
        return cmd_rollback(args)
    elif args.command == "freshness":
        if args.freshness_command == "check":
            return cmd_freshness_check(args)
        elif args.freshness_command == "refresh":
            return cmd_freshness_refresh(args)
        else:
            print("Usage: skill-health freshness {check|refresh}", file=sys.stderr)
            return 1
    elif args.command == "help" or args.command is None:
        parser.print_help()
        return 0
    else:
        print(f"Unknown command: {args.command}", file=sys.stderr)
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
