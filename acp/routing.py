#!/usr/bin/env python3
"""ACP Routing — resolve ACP roles to provider/model/inbox.

Usage: routing.py --role <role>  or  routing.py --list
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Resolve AGENT_OS_HOME and import acp_common
_HOME = Path(os.environ.get("HOME", os.path.expanduser("~"))).expanduser()
_THIS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _THIS_DIR.parent


def _detect_agent_os_home() -> Path:
    env = os.environ.get("AGENT_OS_HOME")
    if env:
        return Path(env).expanduser()
    if (_REPO_ROOT / ".config" / "agent-workflows" / "acp" / "acp_common.py").exists():
        return _REPO_ROOT
    return _HOME / "agent-os"


AGENT_OS_HOME = _detect_agent_os_home()
_ACP_CANDIDATES = [
    AGENT_OS_HOME / ".config" / "agent-workflows" / "acp",
    _REPO_ROOT / ".config" / "agent-workflows" / "acp",
]
ACP_DIR = next(
    (d for d in _ACP_CANDIDATES if (d / "acp_common.py").exists()),
    _ACP_CANDIDATES[0],
)
sys.path.insert(0, str(ACP_DIR))
import acp_common  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="ACP role → provider/model routing")
    parser.add_argument("--role", default=None)
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()

    if args.list:
        try:
            import tomllib

            with open(acp_common.ROLES_TOML, "rb") as f:
                roles = tomllib.load(f)
        except Exception:
            roles = {}
        for role_name, cfg in sorted(roles.items()):
            if isinstance(cfg, dict) and role_name != "workspaces":
                provider = cfg.get("provider", "?")
                model = cfg.get("model", "?")
                cost = cfg.get("cost", "?")
                print(f"{role_name}: {provider}/{model} ({cost})")
        return

    if not args.role:
        print(
            "Usage: routing.py --role <role>  or  routing.py --list",
            file=sys.stderr,
        )
        sys.exit(1)

    provider, model = acp_common.get_role_model(args.role)
    role = acp_common.resolve_role("home", "ASSIGN", fallback_role=args.role)
    print(f"role: {role}")
    print(f"provider: {provider}")
    print(f"model: {model}")
    print(f"inbox: {acp_common.INBOX_AGENTS}/{args.role}")


if __name__ == "__main__":
    main()
