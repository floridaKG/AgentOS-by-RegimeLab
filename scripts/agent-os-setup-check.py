#!/usr/bin/env python3
"""Agent OS setup gap reporter (headless).

Prints a stable JSON object plus human-readable status lines describing the
setup state of an Agent OS install. Never prompts. Always exits 0: this is a
diagnostic for agents and CI, not a gate.

Usage:
  agent-os setup --check
  python3 scripts/agent-os-setup-check.py [--json-only]

Output contract (stable keys, every missing/absent item carries a `hint`):
  os, node, npm, acpx, codegraph, rtk, agents, providers, roles_toml,
  setup_complete
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

HOME = Path.home()
CONFIG_ENV = HOME / ".config" / "agent-os" / "config.env"
SECRETS_ENV = HOME / ".config" / "agent-os" / "secrets.env"
ROLES_TOML = HOME / ".config" / "agent-workflows" / "roles.toml"
AGENT_OS_HOME = Path(os.environ.get("AGENT_OS_HOME", "") or "")
MARKER = AGENT_OS_HOME / ".local" / "state" / "agent-os" / "setup-complete"

AGENTS = ["claude", "codex", "pi", "omp", "grok", "droid"]


def load_env_file(path: Path) -> dict:
    """Parse KEY=VALUE lines from a config/secrets file, tolerating comments."""
    env: dict = {}
    if not path.is_file():
        return env
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return env
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def check_bin(name: str, hint: str) -> dict:
    found = shutil.which(name)
    return {"status": "ready" if found else "missing", "hint": "" if found else hint}


def main() -> int:
    json_only = "--json-only" in sys.argv

    merged_env = dict(os.environ)
    merged_env.update(load_env_file(CONFIG_ENV))
    merged_env.update(load_env_file(SECRETS_ENV))

    os_ok = sys.platform.startswith("linux")

    node = check_bin("node", "Install Node.js 18 or newer (needed for ACPx / CodeGraph)")
    npm = check_bin("npm", "Install npm (ships with Node.js 18+)")
    acpx = check_bin("acpx", "npm install -g acpx")
    codegraph = check_bin("codegraph", "npm install -g @codegraph/cli")
    rtk = check_bin("rtk", "Re-run: ./install.sh --with-rtk (bundled binary, no download)")

    agents = {name: ("ready" if shutil.which(name) else "absent") for name in AGENTS}

    openrouter_key = bool((merged_env.get("OPENROUTER_API_KEY") or "").strip())
    openai_base = (merged_env.get("OPENAI_BASE_URL") or "").strip()
    anthropic_key = bool((merged_env.get("ANTHROPIC_API_KEY") or "").strip())

    roles_status = "missing"
    roles_hint = "Run docs/AGENT_SETUP.md step 5 to write roles.toml"
    if ROLES_TOML.is_file():
        try:
            text = ROLES_TOML.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            text = ""
        if "$HOME/projects" in text or "$VAULT_PATH" in text:
            roles_status = "placeholder"
        else:
            roles_status = "configured"
        roles_hint = "" if roles_status == "configured" else roles_hint

    setup_complete = MARKER.is_file() if AGENT_OS_HOME else False

    report = {
        "os": {
            "status": "ready" if os_ok else "unsupported",
            "hint": "" if os_ok else "Only Linux / WSL2 are verified for v1 (macOS unsupported for v1 claims)",
        },
        "node": node,
        "npm": npm,
        "acpx": acpx,
        "codegraph": codegraph,
        "rtk": rtk,
        "agents": agents,
        "providers": {
            "anthropic_key": "present" if anthropic_key else "absent",
            "openrouter_key": "present" if openrouter_key else "absent",
            "openai_base_url": openai_base or "default (https://openrouter.ai/api/v1)",
        },
        "roles_toml": {"status": roles_status, "hint": roles_hint},
        "setup_complete": setup_complete,
    }

    if not json_only:
        print("=== Agent OS setup --check ===")
        print(f"  os:            {report['os']['status']}")
        for key in ("node", "npm", "acpx", "codegraph", "rtk"):
            item = report[key]
            status = item["status"].ljust(7)
            print(f"  {key + ':':<14} {status} {item['hint']}")
        for name, status in agents.items():
            print(f"  agent {name:<8} {status}")
        prov = report["providers"]
        print(f"  anthropic key: {prov['anthropic_key']}")
        print(f"  openrouter key:{prov['openrouter_key']}")
        print(f"  openai base:   {prov['openai_base_url']}")
        print(f"  roles_toml:    {report['roles_toml']['status']} {report['roles_toml']['hint']}")
        print(f"  setup_complete:{' true' if setup_complete else ' false'}")
        print("---")

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
