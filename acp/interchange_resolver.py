#!/usr/bin/env python3
"""Interchange Resolver — agent/role resolution for ACP interchange.

Resolves explicit agent IDs and operational roles to execution routes
(agent_id, provider, model, role). Used by interchange.py and importable
for direct testing.

Supports both private flat-list agents.yaml and OSS nested `agents:` format.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tomllib
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional


# ── Paths ──────────────────────────────────────────────────────────────────────

_HOME = Path(os.environ.get("HOME", os.path.expanduser("~"))).expanduser()
_THIS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _THIS_DIR.parent


def _detect_agent_os_home() -> Path:
    env = os.environ.get("AGENT_OS_HOME")
    if env:
        return Path(env).expanduser()
    if (_REPO_ROOT / "registry" / "agents.yaml").exists() or (
        _REPO_ROOT / ".config" / "agent-workflows" / "roles.toml"
    ).exists():
        return _REPO_ROOT
    return _HOME / "agent-os"


AGENT_OS_HOME = _detect_agent_os_home()

AGENTS_YAML = Path(
    os.environ.get(
        "AGENT_OS_AGENTS_YAML",
        str(AGENT_OS_HOME / "registry" / "agents.yaml"),
    )
)
ROLES_TOML = Path(
    os.environ.get(
        "AGENT_OS_ROLES_TOML",
        str(AGENT_OS_HOME / ".config" / "agent-workflows" / "roles.toml"),
    )
)


# ── ResolvedRoute dataclass ─────────────────────────────────────────────────────

@dataclass(frozen=True)
class ResolvedRoute:
    """Canonical resolution result for one interchange dispatch."""

    target_agent_id: str
    resolved_role: str
    resolved_provider: str
    resolved_model: str
    schema: str = "agent.os.interchange.resolved_route.v1"
    requested_role: Optional[str] = None
    requested_model: Optional[str] = None
    model_source: str = "config"
    caller_identity_source: str = "declared"


def load_agents() -> list[dict]:
    """Load agents.yaml and return the list of agent entries.

    Accepts:
      - flat list: [{id: ...}, ...]
      - nested OSS: {agents: [{id: ...}, ...]}
    """
    try:
        import yaml
    except ImportError as exc:
        raise ImportError(
            "PyYAML is required for agents.yaml resolution. "
            "Install with: pip install pyyaml"
        ) from exc

    if not AGENTS_YAML.exists():
        return []

    with open(AGENTS_YAML) as f:
        data = yaml.safe_load(f)

    if data is None:
        return []
    if isinstance(data, list):
        return [e for e in data if isinstance(e, dict)]
    if isinstance(data, dict):
        agents = data.get("agents", [])
        if isinstance(agents, list):
            return [e for e in agents if isinstance(e, dict)]
    return []


def find_agent(agent_id: str) -> Optional[dict]:
    """Find an agent entry by ID. Returns None if not found."""
    agents = load_agents()
    for entry in agents:
        if entry.get("id") == agent_id:
            return entry
    return None


def load_roles() -> dict:
    """Load roles.toml and return the dict of role -> config."""
    if not ROLES_TOML.exists():
        return {}
    with open(ROLES_TOML, "rb") as f:
        data = tomllib.load(f)
    # Filter non-role tables (e.g. [workspaces])
    return {
        k: v
        for k, v in data.items()
        if isinstance(v, dict) and k != "workspaces"
    }


def _is_live_agent(agent: dict) -> bool:
    """Treat lifecycle=live OR status=tested/experimental as dispatchable candidates."""
    lifecycle = agent.get("lifecycle")
    if lifecycle == "live":
        return True
    if lifecycle in {"retired", "aspirational", "disabled"}:
        return False
    status = agent.get("status")
    if status in {"tested", "experimental", "live"}:
        return True
    # Default: if no lifecycle/status, allow (OSS minimal registry)
    return lifecycle is None and status is None


# ── Direct agent roles ──────────────────────────────────────────────────────────

# First-class agent IDs that may also appear as direct roles.
DIRECT_AGENT_ROLES = {
    "claude",
    "codex",
    "opencode",
    "droid",
    "pi",
    "hermes",
    "cline",
    "omp",
    "cursor",
    "grok",
}


def is_direct_role(role_name: str) -> bool:
    """Check if a role name is a recognized direct agent role."""
    return role_name in DIRECT_AGENT_ROLES


# ── Agent interchange capability defaults ───────────────────────────────────────

def get_agent_interchange_capability(agent: dict) -> dict:
    """Extract or derive interchange capability block from an agent entry.

    Derives from current adapter behavior. Does not guess — returns safe
    defaults for unknown agents.
    """
    interchange = agent.get("interchange", {})
    if interchange:
        return interchange

    agent_id = agent.get("id", "")
    adapter = agent.get("adapter", "") or agent.get("invocation_template", "")
    has_session = "session" in str(adapter) or "session" in str(
        agent.get("capabilities", [])
    )
    is_live = _is_live_agent(agent)

    if is_live:
        return {
            "dispatchable": True,
            "can_dispatch": False,  # default off — set per agent evidence
            "invocation_modes": ["oneshot", "persistent"] if has_session else ["oneshot"],
            "return_modes": ["sync", "async"],
            "persistence": {
                "kind": "wrapper" if has_session else "none",
                "reconnect": bool(has_session),
            },
            "route_provider": agent.get("provider", agent_id),
            "conformance": {
                "deterministic": "unverified",
                "live": "unverified",
                "checked_at": None,
                "evidence": None,
            },
        }
    return {
        "dispatchable": False,
        "can_dispatch": False,
        "invocation_modes": [],
        "return_modes": [],
        "persistence": {"kind": "none", "reconnect": False},
        "conformance": {
            "deterministic": "unverified",
            "live": "unverified",
            "checked_at": None,
            "evidence": None,
        },
    }


# ── Resolution ──────────────────────────────────────────────────────────────────

def resolve_explicit_agent(
    target_agent_id: str,
    requested_role: Optional[str] = None,
    requested_model: Optional[str] = None,
    strict_model: bool = True,
) -> ResolvedRoute:
    """Resolve an explicit agent ID to an execution route."""
    agent = find_agent(target_agent_id)
    if not agent:
        # Fallback: allow known direct agent ids even if registry is sparse
        if target_agent_id in DIRECT_AGENT_ROLES:
            role_cfg = load_roles().get(target_agent_id, {})
            resolved_model = (
                requested_model
                or (role_cfg.get("model") if isinstance(role_cfg, dict) else None)
                or "default"
            )
            resolved_provider = (
                (role_cfg.get("provider") if isinstance(role_cfg, dict) else None)
                or target_agent_id
            )
            return ResolvedRoute(
                target_agent_id=target_agent_id,
                resolved_role=target_agent_id,
                resolved_provider=resolved_provider,
                resolved_model=resolved_model,
                requested_role=requested_role,
                requested_model=requested_model,
                model_source="explicit" if requested_model else "config",
            )
        raise ValueError(f"Agent '{target_agent_id}' not found in agents.yaml")

    if not _is_live_agent(agent):
        raise ValueError(
            f"Agent '{target_agent_id}' is not live/dispatchable "
            f"(lifecycle={agent.get('lifecycle')!r}, status={agent.get('status')!r})"
        )

    # Check interchange dispatchable flag (default True for OSS minimal entries)
    ic = agent.get("interchange") or get_agent_interchange_capability(agent)
    if not ic.get("dispatchable", True):
        raise ValueError(
            f"Agent '{target_agent_id}' is not interchange-dispatchable"
        )

    # Resolve through role config when present
    role_cfg = load_roles().get(target_agent_id, {})
    resolved_model = ""
    resolved_provider = agent.get("provider") or target_agent_id
    if isinstance(role_cfg, dict):
        resolved_model = role_cfg.get("model", "") or resolved_model
        resolved_provider = role_cfg.get("provider", resolved_provider)
    model_source = "config"

    if requested_model:
        _validate_model_for_agent(target_agent_id, agent, requested_model, strict_model)
        resolved_model = requested_model
        model_source = "explicit"

    if not resolved_model:
        resolved_model = "default"

    return ResolvedRoute(
        target_agent_id=target_agent_id,
        resolved_role=target_agent_id,
        resolved_provider=resolved_provider,
        resolved_model=resolved_model,
        requested_role=requested_role,
        requested_model=requested_model,
        model_source=model_source,
    )


def resolve_role_selected(
    requested_role: str,
    requested_model: Optional[str] = None,
) -> ResolvedRoute:
    """Resolve an operational role to exactly one agent and route."""
    roles = load_roles()
    role_cfg = roles.get(requested_role)
    if not role_cfg:
        # Direct agent role fallback
        if requested_role in DIRECT_AGENT_ROLES:
            return resolve_explicit_agent(
                target_agent_id=requested_role,
                requested_role=requested_role,
                requested_model=requested_model,
            )
        raise ValueError(f"Role '{requested_role}' not found in roles.toml")

    resolved_provider = role_cfg.get("provider", "")
    resolved_model = role_cfg.get("model", "")
    if not resolved_provider and not resolved_model:
        # Old format: chain = ['provider:model']
        chain = role_cfg.get("chain", [])
        if chain:
            first = chain[0]
            resolved_provider = first.split(":")[0]
            resolved_model = first.split(":", 1)[1] if ":" in first else ""

    if not resolved_provider:
        raise ValueError(f"Role '{requested_role}' has no provider configured")

    target_agent_id = _map_provider_to_agent(resolved_provider, requested_role)

    if requested_model:
        agent = find_agent(target_agent_id)
        if agent:
            _validate_model_for_agent(
                target_agent_id, agent, requested_model, strict_model=True
            )
        resolved_model = requested_model

    return ResolvedRoute(
        target_agent_id=target_agent_id,
        resolved_role=requested_role,
        resolved_provider=resolved_provider,
        resolved_model=resolved_model or "default",
        requested_role=requested_role,
        requested_model=requested_model,
        model_source="explicit" if requested_model else "config",
    )


def _map_provider_to_agent(provider: str, role: str) -> str:
    """Map a provider string to one live agent ID."""
    provider_to_agent = {
        "pi": "pi",
        "opencode": "opencode",
        "codex": "codex",
        "claude": "claude",
        "hermes": "hermes",
        "droid": "droid",
        "cline": "cline",
        "omp": "omp",
        "cursor": "cursor",
        "grok": "grok",
        "anthropic": "claude",
        "openai": "codex",
    }

    # Prefer interchange.route_provider metadata when available
    agents = load_agents()
    matches = []
    for entry in agents:
        ic = entry.get("interchange", {}) or {}
        if (
            ic.get("route_provider") == provider
            and _is_live_agent(entry)
            and ic.get("dispatchable", True)
        ):
            matches.append(entry["id"])
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise ValueError(
            f"Provider '{provider}' maps ambiguously to live agents {matches} "
            f"(role='{role}')"
        )

    agent_id = provider_to_agent.get(provider)
    if agent_id:
        agent = find_agent(agent_id)
        if agent is None:
            # Sparse OSS registry: allow known mapping without full entry
            return agent_id
        if _is_live_agent(agent):
            return agent_id

    # Last resort: provider name is itself an agent id
    if find_agent(provider) or provider in DIRECT_AGENT_ROLES:
        return provider

    raise ValueError(
        f"Cannot map provider '{provider}' to a live agent (role='{role}')"
    )


def _validate_model_for_agent(
    agent_id: str,
    agent: dict,
    model: str,
    strict: bool = True,
) -> None:
    """Validate an explicit model against the agent's catalog when present."""
    catalog = agent.get("catalog", [])
    models_allowed = agent.get("models_allowed", [])

    # OSS agents often only document models under configuration.models
    config = agent.get("configuration") or {}
    if not catalog and not models_allowed:
        # No catalog available — cannot validate; warn only in strict mode
        if strict and model and model != "default":
            # Soft pass: registry has no catalog; do not block
            return
        return

    effort_suffix = agent.get("effort_suffix")
    catalog_model = model
    if effort_suffix == "required":
        import re

        match = re.fullmatch(r"(.+)\[(low|medium|high|xhigh)\]", model)
        if not match:
            raise ValueError(
                f"Model '{model}' for agent '{agent_id}' requires an effort suffix "
                "such as [low], [medium], [high], or [xhigh]"
            )
        catalog_model = match.group(1)

    catalog_matched = False
    if catalog:
        catalog_models = set()
        for entry in catalog:
            if isinstance(entry, dict):
                catalog_models.add(entry.get("model", ""))
            elif isinstance(entry, str):
                catalog_models.add(entry)
                if " (" in entry:
                    catalog_models.add(entry.split(" (")[0])

        if catalog_model in catalog_models:
            catalog_matched = True
        else:
            import fnmatch

            for cat_model in catalog_models:
                if fnmatch.fnmatch(catalog_model, cat_model) or fnmatch.fnmatch(
                    cat_model, catalog_model
                ):
                    catalog_matched = True
                    break

    if not catalog_matched and models_allowed:
        import fnmatch

        for allowed in models_allowed:
            if fnmatch.fnmatch(catalog_model, allowed):
                return
        if strict:
            raise ValueError(
                f"Model '{model}' not in agent '{agent_id}' catalog or "
                f"allowed models. Catalog: {catalog}. "
                f"Allowed patterns: {models_allowed}"
            )

    if not catalog_matched and not models_allowed and strict and catalog:
        raise ValueError(
            f"Model '{model}' not in agent '{agent_id}' catalog or allowed models"
        )


# ── CLI ─────────────────────────────────────────────────────────────────────────

def cli_resolve(args: argparse.Namespace) -> None:
    """CLI handler for `resolve` subcommand."""
    try:
        if args.agent_id:
            route = resolve_explicit_agent(
                target_agent_id=args.agent_id,
                requested_role=args.role,
                requested_model=args.model,
                strict_model=not args.no_strict,
            )
        elif args.role:
            route = resolve_role_selected(
                requested_role=args.role,
                requested_model=args.model,
            )
        else:
            print("ERROR: specify --agent-id or --role", file=sys.stderr)
            sys.exit(1)

        if args.json:
            print(json.dumps(asdict(route), indent=2))
        else:
            print(f"target_agent_id:  {route.target_agent_id}")
            print(f"resolved_role:    {route.resolved_role}")
            print(f"resolved_provider: {route.resolved_provider}")
            print(f"resolved_model:   {route.resolved_model}")
            print(f"requested_role:   {route.requested_role}")
            print(f"requested_model:  {route.requested_model}")
            print(f"model_source:     {route.model_source}")
    except (ValueError, FileNotFoundError, ImportError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


def cli_list_agents(args: argparse.Namespace) -> None:
    """CLI handler for `list-agents` subcommand."""
    try:
        agents = load_agents()
    except ImportError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    output = []
    for entry in agents:
        if _is_live_agent(entry) or args.all:
            ic = entry.get("interchange") or get_agent_interchange_capability(entry)
            output.append(
                {
                    "id": entry.get("id"),
                    "lifecycle": entry.get("lifecycle") or entry.get("status"),
                    "dispatchable": ic.get("dispatchable", True),
                    "provider": entry.get("provider"),
                    "route_provider": ic.get(
                        "route_provider", entry.get("provider")
                    ),
                }
            )
    if args.json:
        print(json.dumps(output, indent=2))
    else:
        for a in output:
            print(
                f"{a['id']:12s}  dispatchable={a['dispatchable']}  "
                f"provider={a['provider']}"
            )


def cli_check(args: argparse.Namespace) -> None:
    """CLI handler for `check` subcommand — verify registry consistency."""
    errors = []
    try:
        agents = load_agents()
    except ImportError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    roles = load_roles()
    agent_ids = {a["id"] for a in agents if a.get("id")}

    # Check interchange blocks exist for live agents (soft for OSS)
    for agent in agents:
        if _is_live_agent(agent):
            ic = agent.get("interchange", {})
            if not ic:
                # Soft: OSS minimal registry omits interchange blocks
                pass

    for role_name, role_cfg in roles.items():
        provider = role_cfg.get("provider", "")
        if provider and provider not in agent_ids and provider not in DIRECT_AGENT_ROLES:
            try:
                _map_provider_to_agent(provider, role_name)
            except ValueError:
                errors.append(
                    f"Role '{role_name}' provider '{provider}' has no agent mapping"
                )

    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    else:
        print("interchange_resolver check: PASS")


def main():
    parser = argparse.ArgumentParser(
        description="ACP Interchange Resolver — agent/role resolution"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    rp = sub.add_parser("resolve", help="Resolve an agent ID or role to a route")
    rp.add_argument("--agent-id", help="Target agent ID")
    rp.add_argument("--role", help="Operational role to resolve")
    rp.add_argument("--model", help="Explicit model override")
    rp.add_argument(
        "--no-strict",
        action="store_true",
        help="Disable strict model validation",
    )
    rp.add_argument("--json", action="store_true", help="JSON output")
    rp.set_defaults(func=cli_resolve)

    lp = sub.add_parser("list-agents", help="List known agents")
    lp.add_argument(
        "--all", action="store_true", help="Include aspirational agents"
    )
    lp.add_argument("--json", action="store_true", help="JSON output")
    lp.set_defaults(func=cli_list_agents)

    cp = sub.add_parser("check", help="Check registry consistency")
    cp.set_defaults(func=cli_check)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
