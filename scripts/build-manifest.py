#!/usr/bin/env python3
"""
build-manifest.py - build the agent OS manifest from registries plus on-disk discovery.

The script:
- loads registry/skills.yaml and registry/workflows.yaml
- scans known skill directories for new SKILL.md frontmatter
- scans ~/.config/agent-workflows for workflow headers
- writes a combined manifest to registry/agent-manifest.yaml
- writes a delta report to proposals/registry-additions.md
"""

from __future__ import annotations

import argparse
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import yaml

_AOH = os.environ.get("AGENT_OS_HOME") or str(Path(__file__).resolve().parents[1])

HOME = Path.home()
COCKPIT = Path(_AOH).resolve()
REGISTRY_DIR = COCKPIT / "registry"
PROPOSALS_DIR = COCKPIT / "proposals"
SKILLS_REGISTRY = REGISTRY_DIR / "skills.yaml"
TOOLS_REGISTRY = REGISTRY_DIR / "tools.yaml"
WORKFLOWS_REGISTRY = REGISTRY_DIR / "workflows.yaml"
AGENTS_REGISTRY = REGISTRY_DIR / "agents.yaml"
MCP_REGISTRY = REGISTRY_DIR / "mcp_servers.yaml"
MEMORY_REGISTRY = REGISTRY_DIR / "memory_tiers.yaml"
MANIFEST_OUT = REGISTRY_DIR / "agent-manifest.yaml"
CAPABILITIES_OUT = Path(f"{_AOH}/docs/BOOT_CAPABILITIES.md")
DELTA_REPORT = PROPOSALS_DIR / "registry-additions.md"

GLOBAL_SKILLS_DIR = Path(f"{_AOH}/.claude/skills")
WORKFLOW_ROOT = HOME / ".config" / "agent-workflows"
DEFAULT_WORKSPACE_PATHS = {
    "PROJECT_A": Path(os.environ.get("PROJECT_A", f"{_AOH}/workspace-project-a")),
    "PROJECT_B": Path(os.environ.get("PROJECT_B", f"{_AOH}/workspace-project-b")),
    "VAULT": Path(os.environ.get("VAULT", f"{_AOH}/workspace-vault")),
}


def env_path(name: str, default: Path) -> Path:
    value = os.environ.get(name)
    if not value:
        return default
    return Path(value)


def load_yaml(path: Path) -> Any:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text()) or {}


def save_yaml(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(payload, sort_keys=False, default_flow_style=False)
    )


def extract_skill_frontmatter(path: Path) -> tuple[dict[str, Any] | None, list[str]]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, ["missing frontmatter delimiter"]

    end = None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            end = idx
            break
    if end is None:
        return None, ["unterminated frontmatter"]

    raw = "\n".join(lines[1:end])
    try:
        data = yaml.safe_load(raw) or {}
    except yaml.YAMLError as exc:
        return None, [f"invalid frontmatter: {exc}"]

    if not isinstance(data, dict):
        return None, ["frontmatter is not a mapping"]
    return data, []


def parse_workflow_header(path: Path) -> tuple[dict[str, str] | None, list[str]]:
    text = path.read_text(encoding="utf-8")
    header: dict[str, str] = {}
    required = ["workflow-id", "pattern", "invocation", "description"]

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            if header:
                break
            continue
        if stripped.startswith("#!"):
            continue
        if not stripped.startswith("#"):
            break
        match = re.match(r"#\s*([A-Za-z0-9_-]+):\s*(.+)$", stripped)
        if not match:
            if header:
                break
            continue
        key = match.group(1).strip()
        value = match.group(2).strip()
        header[key] = value
        if all(field in header for field in required):
            break

    missing = [field for field in required if field not in header]
    if missing:
        return None, [f"missing fields: {', '.join(missing)}"]
    return header, []


def registry_skill_id(entry: dict[str, Any]) -> str | None:
    value = entry.get("id") or entry.get("name")
    return str(value) if value else None


def registry_workflow_id(entry: dict[str, Any]) -> str | None:
    value = entry.get("id") or entry.get("name")
    return str(value) if value else None


def discover_skill_roots() -> list[Path]:
    roots: list[Path] = [COCKPIT / "skills", GLOBAL_SKILLS_DIR]
    for workspace_name in ("PROJECT_A", "PROJECT_B", "VAULT"):
        workspace_root = env_path(workspace_name, DEFAULT_WORKSPACE_PATHS[workspace_name])
        roots.append(workspace_root / ".claude" / "skills")
    unique: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        if root in seen:
            continue
        seen.add(root)
        unique.append(root)
    return unique


def infer_skill_scope(path: Path) -> str | None:
    cockpit_skills = COCKPIT / "skills"
    if path.is_relative_to(cockpit_skills):
        return "cockpit"
    if path.is_relative_to(GLOBAL_SKILLS_DIR):
        return "global"
    for workspace_name in ("PROJECT_A", "PROJECT_B", "VAULT"):
        workspace_root = env_path(workspace_name, DEFAULT_WORKSPACE_PATHS[workspace_name])
        workspace_skills = workspace_root / ".claude" / "skills"
        if path.is_relative_to(workspace_skills):
            return f"workspace.{workspace_root.name}"
    return None


def list_skill_files() -> list[Path]:
    files: list[Path] = []
    for root in discover_skill_roots():
        if root.exists():
            files.extend(sorted(root.rglob("SKILL.md")))
    return files


def list_workflow_files() -> list[Path]:
    if not WORKFLOW_ROOT.exists():
        return []
    return sorted(
        path
        for path in WORKFLOW_ROOT.rglob("*")
        if path.is_file() and path.suffix in {".sh", ".py"} and "lib" not in path.parts
    )


def normalize_skill_entry(entry: dict[str, Any]) -> dict[str, Any]:
    payload = dict(entry)
    payload["id"] = registry_skill_id(entry)
    return payload


def normalize_workflow_entry(entry: dict[str, Any]) -> dict[str, Any]:
    payload = dict(entry)
    payload["id"] = registry_workflow_id(entry)
    return payload


def build_registry_id_sets(skills_registry: dict[str, Any], workflows_registry: dict[str, Any]) -> tuple[set[str], set[str]]:
    skill_ids: set[str] = set()
    for entry in skills_registry.get("skills", []):
        if isinstance(entry, dict):
            rid = registry_skill_id(entry)
            if rid:
                skill_ids.add(rid)

    workflow_ids: set[str] = set()
    for entry in workflows_registry.get("workflows", []):
        if isinstance(entry, dict):
            rid = registry_workflow_id(entry)
            if rid:
                workflow_ids.add(rid)

    return skill_ids, workflow_ids


def discover_skills(skill_ids: set[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    additions: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for path in list_skill_files():
        frontmatter, errors = extract_skill_frontmatter(path)
        if not frontmatter:
            skipped.append({"path": str(path), "reason": "; ".join(errors) if errors else "missing frontmatter"})
            continue

        missing = [key for key in ("id", "trigger", "scope", "description", "status") if key not in frontmatter]
        if missing:
            skipped.append(
                {
                    "path": str(path),
                    "reason": f"missing required keys: {', '.join(missing)}",
                }
            )
            continue

        skill_id = str(frontmatter["id"])
        if skill_id in skill_ids:
            continue

        additions.append(
            {
                "id": skill_id,
                "path": str(path),
                "scope": frontmatter.get("scope"),
                "trigger": frontmatter.get("trigger", []),
                "description": frontmatter.get("description", ""),
                "status": frontmatter.get("status", "experimental"),
                "warning": "add to registry/skills.yaml",
            }
        )

    return additions, skipped


def discover_workflows(workflow_ids: set[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    additions: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for path in list_workflow_files():
        header, errors = parse_workflow_header(path)
        if not header:
            skipped.append({"path": str(path), "reason": "; ".join(errors) if errors else "missing workflow header"})
            continue

        workflow_id = header["workflow-id"]
        if workflow_id in workflow_ids:
            continue

        additions.append(
            {
                "id": workflow_id,
                "path": str(path),
                "pattern": header["pattern"],
                "invocation": header["invocation"],
                "description": header["description"],
                "warning": "add to registry/workflows.yaml",
            }
        )

    return additions, skipped


def build_delta_report(
    skill_additions: list[dict[str, Any]],
    workflow_additions: list[dict[str, Any]],
    skill_skips: list[dict[str, Any]],
    workflow_skips: list[dict[str, Any]],
) -> str:
    lines = [
        "# Registry Additions",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
    ]

    if skill_additions:
        lines.extend([
            "## Skills",
            "",
            "| ID | Scope | Path | Description | Warning |",
            "|---|---|---|---|---|",
        ])
        for item in skill_additions:
            lines.append(
                f"| `{item['id']}` | `{item.get('scope', '')}` | `{item['path']}` | {item.get('description', '')} | {item.get('warning', '')} |"
            )
        lines.append("")
    else:
        lines.extend(["## Skills", "", "No unregistered skills were found.", ""])

    if workflow_additions:
        lines.extend([
            "## Workflows",
            "",
            "| ID | Pattern | Invocation | Path | Warning |",
            "|---|---|---|---|---|",
        ])
        for item in workflow_additions:
            lines.append(
                f"| `{item['id']}` | `{item.get('pattern', '')}` | `{item.get('invocation', '')}` | `{item['path']}` | {item.get('warning', '')} |"
            )
        lines.append("")
    else:
        lines.extend(["## Workflows", "", "No unregistered workflows were found.", ""])

    if skill_skips or workflow_skips:
        lines.extend(["## Skipped", ""])
        for item in skill_skips:
            lines.append(f"- Skill `{item['path']}` skipped: {item['reason']}")
        for item in workflow_skips:
            lines.append(f"- Workflow `{item['path']}` skipped: {item['reason']}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def build_manifest(
    skills_registry: dict[str, Any],
    tools_registry: dict[str, Any],
    workflows_registry: dict[str, Any],
    agents_registry: dict[str, Any],
    mcp_registry: dict[str, Any],
    memory_registry: dict[str, Any],
    skill_additions: list[dict[str, Any]],
    workflow_additions: list[dict[str, Any]],
    skill_skips: list[dict[str, Any]],
    workflow_skips: list[dict[str, Any]],
) -> dict[str, Any]:
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "skills": len(skills_registry.get("skills", [])),
            "tools": len(tools_registry) if isinstance(tools_registry, list) else 0,
            "workflows": len(workflows_registry.get("workflows", [])),
            "agents": len(agents_registry) if isinstance(agents_registry, list) else 0,
            "mcp_servers": len(mcp_registry.get("mcp_servers", [])),
            "memory_tiers": len(memory_registry.get("tiers", [])),
        },
        "source": {
            "skills_registry": str(SKILLS_REGISTRY),
            "tools_registry": str(TOOLS_REGISTRY),
            "workflows_registry": str(WORKFLOWS_REGISTRY),
            "agents_registry": str(AGENTS_REGISTRY),
            "mcp_registry": str(MCP_REGISTRY),
            "memory_registry": str(MEMORY_REGISTRY),
            "skill_roots": [str(root) for root in discover_skill_roots()],
            "workflow_root": str(WORKFLOW_ROOT),
        },
        "registries": {
            "skills": [normalize_skill_entry(entry) for entry in skills_registry.get("skills", []) if isinstance(entry, dict)],
            "tools": list(tools_registry) if isinstance(tools_registry, list) else [],
            "workflows": [normalize_workflow_entry(entry) for entry in workflows_registry.get("workflows", []) if isinstance(entry, dict)],
            "agents": list(agents_registry) if isinstance(agents_registry, list) else [],
            "mcp_servers": [entry for entry in mcp_registry.get("mcp_servers", []) if isinstance(entry, dict)],
            "memory_tiers": [entry for entry in memory_registry.get("tiers", []) if isinstance(entry, dict)],
        },
        "discovered": {
            "skills": skill_additions,
            "workflows": workflow_additions,
        },
        "scan": {
            "skipped_skills": skill_skips,
            "skipped_workflows": workflow_skips,
        },
    }
    return manifest


def build_capabilities_doc(
    skills_registry: dict[str, Any],
    tools_registry: dict[str, Any],
    workflows_registry: dict[str, Any],
    agents_registry: dict[str, Any],
    mcp_registry: dict[str, Any],
    memory_registry: dict[str, Any],
) -> str:
    """Build the boot-visible BOOT_CAPABILITIES.md — concise capability overview that every agent reads at boot."""
    lines: list[str] = []
    lines.append("---")
    lines.append("title: Agent OS — Boot Capabilities")
    lines.append("generated: true")
    lines.append(f"generated_at: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}")
    lines.append(f"last_updated: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}")
    lines.append("purpose: Boot-visible capability overview. Every agent reads this to know what tools, skills, workflows, agents, MCP servers, and memory capabilities are available.")
    lines.append("source_of_truth: $AGENT_OS_HOME/registry/ (skills.yaml, tools.yaml, workflows.yaml, agents.yaml, mcp_servers.yaml, memory_tiers.yaml)")
    lines.append("deep_index: $AGENT_OS_HOME/INDEX.md")
    lines.append("---")
    lines.append("")
    lines.append("# Agent OS — Boot Capabilities")
    lines.append("")
    lines.append(f"*Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} from registries.*")
    lines.append("")
    lines.append("<!-- This file is auto-generated by build-manifest.py. Do not edit directly. -->")
    lines.append("")
    lines.append("Quick reference: **Loop Patterns** · **Skills** · **Tools** · **Workflows** · **Agents** · **MCP** · **Memory** · [INDEX.md]($AGENT_OS_HOME/INDEX.md) (deep inventory)")
    lines.append("")

    # ── ACP Agents ──
    lines.append("## ACP Agents")
    lines.append("")
    lines.append("| Agent | Use when | Model selection | Catalog / Notes |")
    lines.append("|---|---|---|---|")
    agents = list(agents_registry) if isinstance(agents_registry, list) else []
    for agent in agents:
        aid = agent.get("id", "?")
        use_when = agent.get("use_when", agent.get("role_strengths", []))
        if isinstance(use_when, list):
            use_when = "; ".join(use_when)
        ms = agent.get("model_selection", "?")
        catalog = agent.get("catalog", agent.get("models_allowed", []))
        if isinstance(catalog, list):
            catalog = ", ".join(str(c) for c in catalog)
        notes = agent.get("note", "")
        if notes:
            catalog = f"{catalog} ({notes})"
        lines.append(f"| `{aid}` | {use_when} | {ms} | {catalog} |")
    lines.append("")

    # ── Skills ──
    lines.append("## Skills")
    lines.append("")
    lines.append("### os-shared (auto-loaded via agent-os-shared plugin)")
    lines.append("")
    lines.append("| Skill | What it does | Triggers |")
    lines.append("|---|---|---|")
    skills = skills_registry.get("skills", [])
    os_shared = [s for s in skills if isinstance(s, dict) and s.get("tier") == "os-shared" and s.get("status") != "deprecated"]
    for skill in sorted(os_shared, key=lambda s: s.get("name", "")):
        name = skill.get("name", "?")
        desc = skill.get("description", "").split(".")[0][:80]
        triggers = skill.get("trigger", [])
        trig_str = ", ".join(triggers[:4])
        if len(triggers) > 4:
            trig_str += f" +{len(triggers) - 4} more"
        lines.append(f"| `{name}` | {desc} | {trig_str} |")
    lines.append("")

    # Workspace skills (grouped by tier)
    for tier_label, tier_key in [("Project A", "workspace-project-a"), ("Project B", "workspace-project-b"), ("Vault", "workspace-vault"), ("Personal", "personal")]:
        tier_skills = [s for s in skills if isinstance(s, dict) and s.get("tier") == tier_key and s.get("status") != "deprecated"]
        if not tier_skills:
            continue
        lines.append(f"### {tier_label}")
        lines.append("")
        lines.append("| Skill | What it does |")
        lines.append("|---|---|")
        for skill in sorted(tier_skills, key=lambda s: s.get("name", "")):
            name = skill.get("name", "?")
            desc = skill.get("description", "").split(".")[0][:100]
            lines.append(f"| `{name}` | {desc} |")
        lines.append("")

    # Agent-specific skills (available via ACP dispatch)
    agent_skills = [s for s in skills if isinstance(s, dict) and s.get("tier", "").startswith("agent-") and s.get("status") != "deprecated"]
    if agent_skills:
        lines.append("### Agent-specific skills (available via ACP dispatch)")
        lines.append("")
        lines.append("| Skill | What it does |")
        lines.append("|---|---|")
        for skill in sorted(agent_skills, key=lambda s: s.get("name", "")):
            name = skill.get("name", "?")
            desc = skill.get("description", "").split(".")[0][:100]
            lines.append(f"| `{name}` | {desc} |")
        lines.append("")

    # ── Tools ──
    lines.append("## CLI Tools")
    lines.append("")
    lines.append("| Tool | What it does | Invocation |")
    lines.append("|---|---|---|")
    tools = list(tools_registry) if isinstance(tools_registry, list) else []
    for tool in sorted(tools, key=lambda t: t.get("id", "")):
        if isinstance(tool, dict):
            tid = tool.get("id", "?")
            purpose = tool.get("purpose", "").split(".")[0][:80]
            inv = tool.get("invocation", "")
            status = tool.get("status", "")
            if status == "deprecated":
                continue
            lines.append(f"| `{tid}` | {purpose} | `{inv}` |")
    lines.append("")

    # ── Loop Patterns (cross-cutting: all agent loop types) ──
    lines.append("## Loop Patterns")
    lines.append("")
    lines.append("All the ways an agent can loop — feedback loops, overnight loops, parallel evaluation loops, orchestration loops, learning loops, and memory lifecycle loops.")
    lines.append("")
    lines.append("| Loop | Type | What it does | How to invoke |")
    lines.append("|---|---|---|---|")

    loop_patterns = [
        ("worktree-loop", "Worktree", "Overnight autonomous loop in isolated git worktree on loop/* branch. Model rotates on churn. No auto-merge.",
         "`worktree-loop start <task_file> [--max-iters N]`"),
        ("team / MOE 1", "Parallel evaluation", "N cheap LLMs in parallel + cheap judge -> verdict+disagreements. Tool-free, fast.",
         "`/moe` or `team fire --tier 1 --panel quick --task \"<text>\"`"),
        ("team / MOE 2", "Parallel evaluation", "Provider-diverse full agents in parallel with inline model/agent swap.",
         "`/moe 2` or `team fire --tier 2 --panel swarm --task \"<text>\"`"),
        ("team / MOE 3", "Persistent dialogue", "Iterative transcript-replay rounds (collaborate/redteam) with convergence judge.",
         "`/moe 3 collaborate|redteam`"),
        ("agent-workflow swarm", "Multi-agent", "N parallel explorers inspect separate angles, then a reviewer synthesizes.",
         "`agent-workflow swarm <task> [n]`"),
        ("agent-workflow council", "Multi-agent", "3 independent opinions, moderator surfaces disagreement.",
         "`agent-workflow council <problem>`"),
        ("agent-workflow dialogue", "Multi-agent", "Two agents alternate turns across N rounds, reviewer synthesizes transcript.",
         "`agent-workflow dialogue <role_a> <role_b> <topic> [turns]`"),
        ("agent-workflow redteam", "Multi-agent", "Proposer defends -> attacker finds holes -> adjudicator PASS/FAIL verdict.",
         "`agent-workflow redteam <artifact> [turns]`"),
        ("agent-workflow orchestrate", "Multi-agent", "Explore -> build -> review -> fix pipeline for multi-phase goals.",
         "`agent-workflow orchestrate <goal.txt>`"),
        ("sidecar", "Persistent session", "Higher-reasoning DRIVER + persistent pi execution partner. Free Zen + paid Go fallback.",
         "`sidecar init` / `sidecar \"<instruction>\"`"),
        ("get-smarter", "Learning loop", "Error logging and review loop. Captures setbacks, reviews periodically, implements fixes.",
         "`get-smarter log \"<summary>\"` / `get-smarter review`"),
        ("stumble-triage", "Learning loop", "Triage stumble clusters from short-term memory. Groups by fingerprint, surfaces recurrence.",
         "`stumble-triage` / `stumble-review list`"),
        ("agent-voice", "Feedback loop", "Append-only insight buffer. Agents emit friction/improvement/risk. Surfaces via doctor gate.",
         "`agent-voice emit --kind friction|improvement|risk --statement \"...\"`"),
        ("self-learning (workflow)", "Session loop", "Mandatory end-of-session 5-question reflection. Captures lessons, triggers skill promotion.",
         "Triggered automatically at end of session."),
        ("skill-promotion (workflow)", "Recurrence loop", "Same lesson 2+ times -> promotes to BOOT.md rule or new skill. Runs on recurrence detection.",
         "Triggered by self-learning workflow on repeat patterns."),
        ("memory-promote", "Memory loop", "Promotes validated short-term entries to Neo4j + Pinecone. Runs automatically (cron) or on demand.",
         "`memory-promote`"),
    ]
    for name, ltype, desc, invoke in loop_patterns:
        lines.append(f"| `{name}` | {ltype} | {desc} | {invoke} |")
    lines.append("")

    # ── Workflows ──
    lines.append("## Workflows")
    lines.append("")
    lines.append("| Workflow | When it runs | Invocation |")
    lines.append("|---|---|---|")
    workflows = workflows_registry.get("workflows", [])
    for wf in workflows:
        if isinstance(wf, dict):
            wf_id = wf.get("id") or wf.get("name", "?")
            triggered = wf.get("triggered_by", wf.get("pattern", ""))
            if isinstance(triggered, list):
                triggered = ", ".join(triggered)
            inv = wf.get("invocation", wf.get("command", ""))
            lines.append(f"| `{wf_id}` | {triggered} | `{inv}` |")
    lines.append("")

    # ── MCP Servers ──
    lines.append("## MCP Servers")
    lines.append("")
    lines.append("| Server | Use when | Tools | Access |")
    lines.append("|---|---|---|---|")
    mcp_servers = mcp_registry.get("mcp_servers", [])
    for server in mcp_servers:
        if isinstance(server, dict):
            name = server.get("name", "?")
            use_when = server.get("use_when", "")
            tool_count = server.get("tool_count", 0)
            agent_access = server.get("agent_access", [])
            if isinstance(agent_access, list):
                agent_access = "; ".join(agent_access[:3])
            lines.append(f"| `{name}` | {use_when} | {tool_count} tools | {agent_access} |")
    lines.append("")

    # ── Memory ──
    lines.append("## Memory Capabilities")
    lines.append("")
    lines.append("| Tier | Backend | Write via | Read via |")
    lines.append("|---|---|---|---|")
    memory_tiers = memory_registry.get("tiers", [])
    for tier in memory_tiers:
        if isinstance(tier, dict) and tier.get("status") in ("live",):
            tid = tier.get("id", "?")
            backend = tier.get("backend", "?")
            write_via = tier.get("write_via", "?")
            read_via = tier.get("read_via", "?")
            lines.append(f"| `{tid}` | {backend} | `{write_via}` | `{read_via}` |")
    lines.append("")
    lines.append("### Memory CLI tools")
    lines.append("")
    lines.append("| Command | What it does |")
    lines.append("|---|---|")
    memory_cmds = memory_registry.get("commands", [])
    for cmd in memory_cmds:
        if isinstance(cmd, dict):
            name = cmd.get("name", "?")
            purpose = cmd.get("purpose", "").split(".")[0][:100]
            wrapper = cmd.get("wrapper", "")
            name_str = f"`{name}`" if not wrapper else f"`{name}` (alias: `{wrapper}`)"
            lines.append(f"| {name_str} | {purpose} |")
    lines.append("")

    # ── Where to go next ──
    lines.append("## Where to go next")
    lines.append("")
    lines.append("- **Loop patterns**: `$AGENT_OS_HOME/docs/LOOPS.md` — full loop reference with decision table")
    lines.append("- **Deep inventory**: `$AGENT_OS_HOME/INDEX.md` — grep for anything")
    lines.append("- **Boot routing**: `$AGENT_OS_HOME/AGENTS.md` → `boot-check` → `BOOT_FACTS.yaml`")
    lines.append("- **ACP capability map**: `$AGENT_OS_HOME/docs/ACP_CAPABILITY_MAP.md`")
    lines.append("- **Memory architecture**: `$AGENT_OS_HOME/registry/memory_tiers.yaml`")
    lines.append("- **Doc governance**: `$AGENT_OS_HOME/docs/SELF_MANAGEMENT.md`")
    lines.append("")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the agent OS manifest and capability surface from registries")
    parser.add_argument("--dry-run", action="store_true", help="print the manifest and capabilities to stdout instead of writing files")
    parser.add_argument("--capabilities-only", action="store_true", help="only generate BOOT_CAPABILITIES.md, skip manifest and delta report")
    args = parser.parse_args()

    skills_registry = load_yaml(SKILLS_REGISTRY)
    tools_registry = load_yaml(TOOLS_REGISTRY)
    workflows_registry = load_yaml(WORKFLOWS_REGISTRY)
    agents_registry = load_yaml(AGENTS_REGISTRY)
    mcp_registry = load_yaml(MCP_REGISTRY)
    memory_registry = load_yaml(MEMORY_REGISTRY)

    # Normalize list-valued registries
    if isinstance(tools_registry, dict) and "tools" in tools_registry:
        tools_registry = tools_registry["tools"]
    if isinstance(agents_registry, dict) and "agents" in agents_registry:
        agents_registry = agents_registry["agents"]
    if isinstance(mcp_registry, dict):
        mcp_registry = mcp_registry  # already has mcp_servers key
    if isinstance(memory_registry, dict):
        memory_registry = memory_registry  # already has tiers + commands keys

    # Generate BOOT_CAPABILITIES.md
    capabilities_doc = build_capabilities_doc(
        skills_registry,
        tools_registry,
        workflows_registry,
        agents_registry,
        mcp_registry,
        memory_registry,
    )

    if args.capabilities_only:
        if args.dry_run:
            print(capabilities_doc)
            return 0
        CAPABILITIES_OUT.parent.mkdir(parents=True, exist_ok=True)
        CAPABILITIES_OUT.write_text(capabilities_doc, encoding="utf-8")
        print(f"wrote capabilities: {CAPABILITIES_OUT}")
        return 0

    # Skill/workflow discovery for delta report
    skill_ids, workflow_ids = build_registry_id_sets(skills_registry, workflows_registry)
    skill_additions, skill_skips = discover_skills(skill_ids)
    workflow_additions, workflow_skips = discover_workflows(workflow_ids)

    manifest = build_manifest(
        skills_registry,
        tools_registry,
        workflows_registry,
        agents_registry,
        mcp_registry,
        memory_registry,
        skill_additions,
        workflow_additions,
        skill_skips,
        workflow_skips,
    )
    report = build_delta_report(skill_additions, workflow_additions, skill_skips, workflow_skips)

    if args.dry_run:
        print(yaml.safe_dump(manifest, sort_keys=False, default_flow_style=False))
        print("---")
        print(capabilities_doc)
        print("---")
        print(report)
        return 0

    save_yaml(MANIFEST_OUT, manifest)
    DELTA_REPORT.parent.mkdir(parents=True, exist_ok=True)
    DELTA_REPORT.write_text(report, encoding="utf-8")
    CAPABILITIES_OUT.parent.mkdir(parents=True, exist_ok=True)
    CAPABILITIES_OUT.write_text(capabilities_doc, encoding="utf-8")

    print(f"wrote manifest: {MANIFEST_OUT}")
    print(f"wrote capabilities: {CAPABILITIES_OUT}")
    print(f"wrote delta report: {DELTA_REPORT}")
    print(f"discovered skills: {len(skill_additions)}")
    print(f"discovered workflows: {len(workflow_additions)}")
    print(f"registry counts — skills: {manifest['summary']['skills']}, tools: {manifest['summary']['tools']}, workflows: {manifest['summary']['workflows']}, agents: {manifest['summary']['agents']}, mcp: {manifest['summary']['mcp_servers']}, memory: {manifest['summary']['memory_tiers']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
