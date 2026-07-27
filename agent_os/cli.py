"""Agent OS — canonical CLI command implementation.

This module implements the new unified CLI commands:
  version, capabilities, init, doctor/health, memory add/search/list/health,
  mcp serve, mcp install, mcp uninstall.

Legacy advanced commands are dispatched to scripts/agent-os via subprocess.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from agent_os import __version__

# Exit codes per spec
EXIT_OK = 0
EXIT_WARN = 1
EXIT_ERROR = 2
EXIT_USAGE = 64


def _print_json(data: Any, *, indent: int = 2) -> None:
    """Print a JSON document to stdout."""
    print(json.dumps(data, indent=indent))


def _die(message: str, code: int = EXIT_ERROR) -> None:
    """Print error to stderr and exit."""
    print(f"error: {message}", file=sys.stderr)
    sys.exit(code)


# ── New command implementations ───────────────────────────────────────────


def cmd_version(args: argparse.Namespace) -> None:
    """Print the Agent OS version."""
    if args.json:
        _print_json({"version": __version__})
    else:
        print(f"agent-os {__version__}")


def cmd_capabilities(args: argparse.Namespace) -> None:
    """Print the Agent OS capability report."""
    from agent_os.capabilities import get_capabilities

    caps = get_capabilities()
    if args.json:
        _print_json(caps)
    else:
        print(f"Agent OS {caps['version']}")
        print(f"Platform: {caps['platform']['system']} {caps['platform']['release']} ({caps['platform']['machine']})")
        print(f"Python:   {caps['platform']['python_version']}")
        print(f"Home:     {caps['home']}")
        print()
        print("Core features:")
        for feat, enabled in sorted(caps["core_features"].items()):
            status = "enabled" if enabled else "disabled"
            print(f"  {feat}: {status}")
        print()
        print("Optional backends:")
        for name, available in sorted(caps["optional_backends"].items()):
            status = "available" if available else "not installed"
            print(f"  {name}: {status}")


def cmd_init(args: argparse.Namespace) -> None:
    """Initialize Agent OS state directories and memory database."""
    from agent_os.config import init_workspace
    from agent_os.memory import ensure_db

    force = getattr(args, "force", False)
    result = init_workspace(force=force)

    try:
        ensure_db()
        result["memory_initialized"] = True
    except Exception as e:
        result["memory_initialized"] = False
        result["memory_error"] = str(e)

    if args.json:
        _print_json(result)
    else:
        if result["memory_initialized"]:
            print(f"Agent OS initialized at {result['state_dir']}")
            if result["created"]:
                for d in result["created"]:
                    print(f"  Created: {d}")
            if result["existed"]:
                for d in result["existed"]:
                    print(f"  Exists:  {d}")
        else:
            print(f"Initialization warning: {result.get('memory_error', 'unknown')}", file=sys.stderr)
            sys.exit(EXIT_WARN)


def cmd_doctor(args: argparse.Namespace) -> None:
    """Run comprehensive diagnostic checks."""
    from agent_os.diagnostics import run_diagnostics

    report = run_diagnostics()
    if args.json:
        _print_json(report.to_dict())
    else:
        for item in report.items:
            icon = {"ok": "OK", "warn": "WARN", "error": "ERR"}[item.status]
            print(f"[{icon:>4}] {item.name}: {item.message}")
        print()
        verdict = {"ok": "PASS", "warn": "WARN", "error": "FAIL"}[report.overall_status]
        print(f"Verdict: {verdict}")

    if report.overall_status == "error":
        sys.exit(EXIT_ERROR)


def cmd_health(args: argparse.Namespace) -> None:
    """Run simplified health check (single verdict)."""
    from agent_os.diagnostics import run_health_check

    report = run_health_check()
    if args.json:
        _print_json(report.to_dict())
    else:
        for item in report.items:
            icon = {"ok": "OK", "warn": "WARN", "error": "ERR"}[item.status]
            print(f"[{icon:>4}] {item.name}: {item.message}")
        verdict = {"ok": "HEALTHY", "warn": "DEGRADED", "error": "UNHEALTHY"}[report.overall_status]
        print(f"\nHealth: {verdict}")

    if report.overall_status == "error":
        sys.exit(EXIT_ERROR)
    elif report.overall_status == "warn":
        sys.exit(EXIT_WARN)


def cmd_memory_add(args: argparse.Namespace) -> None:
    """Add a memory record with safe defaults."""
    from agent_os.memory import add_memory

    result = add_memory(
        text=args.text,
        intent=args.intent,
        kind=args.kind,
        workspace=args.workspace,
        agent_id=args.agent_id,
        run_id=args.run_id,
        source_ref=args.source_ref,
        summary=args.summary,
    )

    if args.json:
        _print_json(result.to_dict())
    else:
        if result.ok:
            print(f"Added: {result.data['id']} (intent={result.data['intent']}, kind={result.data['kind']})")
        else:
            print(f"Error: {result.error}", file=sys.stderr)
            sys.exit(EXIT_ERROR)


def cmd_memory_search(args: argparse.Namespace) -> None:
    """Search memory records."""
    from agent_os.memory import search_memory

    result = search_memory(
        query=args.query,
        tier=args.tier,
        limit=args.limit,
        workspace=getattr(args, "workspace", None),
        intent=getattr(args, "intent", None),
    )

    if args.json:
        _print_json(result.to_dict())
    else:
        if not result.ok:
            print(f"Error: {result.error}", file=sys.stderr)
            sys.exit(EXIT_ERROR)
        results = result.data.get("results", [])
        if not results:
            print("No results found.")
        else:
            for r in results:
                score = f" (score={r['score']})" if "score" in r else ""
                print(f"[{r['id']}] {r['summary']}{score}")
                if args.verbose:
                    print(f"  intent={r['intent']} kind={r['kind']} ws={r['workspace']} src={r['source_ref']}")


def cmd_memory_list(args: argparse.Namespace) -> None:
    """List memory records."""
    from agent_os.memory import list_memory

    result = list_memory(
        intent=getattr(args, "intent", None),
        workspace=getattr(args, "workspace", None),
        limit=args.limit,
    )

    if args.json:
        _print_json(result.to_dict())
    else:
        if not result.ok:
            print(f"Error: {result.error}", file=sys.stderr)
            sys.exit(EXIT_ERROR)
        results = result.data.get("results", [])
        count = result.data.get("count", 0)
        if not results:
            print("No records found.")
        else:
            for r in results:
                print(f"[{r['id']}] {r['intent']}/{r['kind']} — {r['summary']}")
            print(f"\n{count} record(s)")


def cmd_memory_health(args: argparse.Namespace) -> None:
    """Check memory subsystem health."""
    from agent_os.memory import memory_health

    result = memory_health()
    if args.json:
        _print_json(result.to_dict())
    else:
        data = result.data
        checks = data.get("checks", [])
        for check in checks:
            icon = {"ok": "OK", "warn": "WARN", "error": "ERR"}[check["status"]]
            print(f"[{icon:>4}] {check['name']}: {check['message']}")
        status = data.get("status", "ok")
        verdict = {"ok": "HEALTHY", "warn": "DEGRADED", "error": "UNHEALTHY"}[status]
        print(f"\nMemory health: {verdict}")


# ── MCP command implementations ──────────────────────────────────────────


def cmd_mcp_serve(args: argparse.Namespace) -> None:
    """Start the MCP stdio server."""
    from agent_os.mcp_server import mcp

    print("Starting Agent OS MCP server...", file=sys.stderr)

    try:
        import asyncio
        asyncio.run(mcp.run_stdio_async())
    except KeyboardInterrupt:
        if not args.json:
            print("\nServer stopped.", file=sys.stderr)
    except Exception as e:
        _die(f"MCP server error: {e}", EXIT_ERROR)


def cmd_mcp_install(args: argparse.Namespace) -> None:
    """Install MCP configuration for a client."""
    client = args.client.lower()
    if client not in ("claude", "codex", "opencode"):
        _die(f"Unsupported client: {client}. Supported: claude, codex, opencode", EXIT_USAGE)

    dry_run = getattr(args, "dry_run", False)
    force = getattr(args, "force", False)

    # Build the MCP config entry
    mcp_config = {
        "command": sys.executable,
        "args": ["-m", "agent_os.mcp_server"],
        "env": {},
    }

    # Determine config file path based on client
    if client == "claude":
        config_dir = Path.home() / ".claude"
        config_file = config_dir / "settings.json"
        config_key = "mcpServers"
    elif client == "codex":
        config_dir = Path.home() / ".codex"
        config_file = config_dir / "config.json"
        config_key = "mcp_servers"
    elif client == "opencode":
        config_dir = Path.home() / ".opencode"
        config_file = config_dir / "config.json"
        config_key = "mcp_servers"

    if dry_run:
        result = {
            "action": "install",
            "client": client,
            "config_file": str(config_file),
            "config_key": config_key,
            "mcp_config": mcp_config,
            "dry_run": True,
        }
        if args.json:
            _print_json(result)
        else:
            print(f"Would install MCP config for {client}:")
            print(f"  Config file: {config_file}")
            print(f"  Config key: {config_key}")
            print(f"  MCP config: {json.dumps(mcp_config, indent=2)}")
        return

    # Read existing config
    existing_config = {}
    if config_file.exists():
        try:
            with open(config_file, "r") as f:
                existing_config = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            if not force:
                _die(f"Failed to parse {config_file}: {e}. Use --force to overwrite.", EXIT_ERROR)
            existing_config = {}

    # Check if already installed
    if config_key in existing_config and "agent-os" in existing_config[config_key]:
        if not force:
            result = {
                "action": "install",
                "client": client,
                "status": "already_installed",
                "config_file": str(config_file),
                "dry_run": False,
            }
            if args.json:
                _print_json(result)
            else:
                print(f"MCP config for agent-os already exists in {config_file}")
            return

    # Install the config
    config_dir.mkdir(parents=True, exist_ok=True)
    existing_config.setdefault(config_key, {})
    existing_config[config_key]["agent-os"] = mcp_config

    try:
        with open(config_file, "w") as f:
            json.dump(existing_config, f, indent=2)
    except IOError as e:
        _die(f"Failed to write {config_file}: {e}", EXIT_ERROR)

    result = {
        "action": "install",
        "client": client,
        "status": "installed",
        "config_file": str(config_file),
        "dry_run": False,
    }
    if args.json:
        _print_json(result)
    else:
        print(f"Installed MCP config for agent-os in {config_file}")


def cmd_mcp_uninstall(args: argparse.Namespace) -> None:
    """Uninstall MCP configuration for a client."""
    client = args.client.lower()
    if client not in ("claude", "codex", "opencode"):
        _die(f"Unsupported client: {client}. Supported: claude, codex, opencode", EXIT_USAGE)

    dry_run = getattr(args, "dry_run", False)
    force = getattr(args, "force", False)

    # Determine config file path based on client
    if client == "claude":
        config_dir = Path.home() / ".claude"
        config_file = config_dir / "settings.json"
        config_key = "mcpServers"
    elif client == "codex":
        config_dir = Path.home() / ".codex"
        config_file = config_dir / "config.json"
        config_key = "mcp_servers"
    elif client == "opencode":
        config_dir = Path.home() / ".opencode"
        config_file = config_dir / "config.json"
        config_key = "mcp_servers"

    # Read existing config
    if not config_file.exists():
        result = {
            "action": "uninstall",
            "client": client,
            "status": "not_found",
            "config_file": str(config_file),
            "dry_run": dry_run,
        }
        if args.json:
            _print_json(result)
        else:
            print(f"No config file found at {config_file}")
        return

    try:
        with open(config_file, "r") as f:
            existing_config = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        if not force:
            _die(f"Failed to parse {config_file}: {e}. Use --force to skip.", EXIT_ERROR)
        result = {
            "action": "uninstall",
            "client": client,
            "status": "skipped",
            "reason": "parse_error",
            "config_file": str(config_file),
            "dry_run": dry_run,
        }
        if args.json:
            _print_json(result)
        else:
            print(f"Skipping {config_file} (parse error)")
        return

    # Check if agent-os entry exists
    if config_key not in existing_config or "agent-os" not in existing_config[config_key]:
        result = {
            "action": "uninstall",
            "client": client,
            "status": "not_installed",
            "config_file": str(config_file),
            "dry_run": dry_run,
        }
        if args.json:
            _print_json(result)
        else:
            print(f"MCP config for agent-os not found in {config_file}")
        return

    if dry_run:
        result = {
            "action": "uninstall",
            "client": client,
            "config_file": str(config_file),
            "config_key": config_key,
            "dry_run": True,
        }
        if args.json:
            _print_json(result)
        else:
            print(f"Would uninstall MCP config for agent-os from {config_file}")
        return

    # Remove the agent-os entry
    del existing_config[config_key]["agent-os"]
    if not existing_config[config_key]:
        del existing_config[config_key]

    try:
        with open(config_file, "w") as f:
            json.dump(existing_config, f, indent=2)
    except IOError as e:
        _die(f"Failed to write {config_file}: {e}", EXIT_ERROR)

    result = {
        "action": "uninstall",
        "client": client,
        "status": "uninstalled",
        "config_file": str(config_file),
        "dry_run": False,
    }
    if args.json:
        _print_json(result)
    else:
        print(f"Uninstalled MCP config for agent-os from {config_file}")


# ── Legacy command dispatch ───────────────────────────────────────────────


def _dispatch_legacy(remaining_args: list[str]) -> None:
    """Dispatch to scripts/agent-os for legacy advanced commands."""
    home = Path(os.environ.get("AGENT_OS_HOME", Path(__file__).resolve().parent.parent))
    script = home / "scripts" / "agent-os"
    if not script.exists():
        _die(f"Legacy CLI not found: {script}", EXIT_ERROR)

    cmd = [sys.executable, str(script)] + remaining_args
    try:
        result = subprocess.run(cmd, timeout=120)
        sys.exit(result.returncode)
    except (subprocess.TimeoutExpired, TimeoutError):
        _die("Command timed out", EXIT_ERROR)
    except Exception as e:
        _die(str(e), EXIT_ERROR)


# ── Parser ────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the new CLI."""
    def add_output_flags(command_parser: argparse.ArgumentParser) -> None:
        command_parser.add_argument(
            "--json",
            action="store_true",
            default=argparse.SUPPRESS,
            help="Machine-readable JSON output",
        )
        command_parser.add_argument(
            "-q",
            "--quiet",
            action="store_true",
            default=argparse.SUPPRESS,
            help="Suppress non-error output",
        )
        command_parser.add_argument(
            "-v",
            "--verbose",
            action="store_true",
            default=argparse.SUPPRESS,
            help="Show detailed output",
        )

    parser = argparse.ArgumentParser(
        prog="agent-os",
        description="Agent OS — local-first agent orchestration framework.\n\n"
        "Quick start:\n"
        "  agent-os init\n"
        "  agent-os doctor\n"
        "  agent-os memory add \"A useful fact.\"\n"
        "  agent-os memory search \"fact\"\n",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Machine-readable JSON output",
    )
    parser.add_argument(
        "-q", "--quiet", action="store_true",
        help="Suppress non-error output",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Show detailed output",
    )

    sub = parser.add_subparsers(dest="command", metavar="<command>")

    # version
    p_version = sub.add_parser("version", help="Print version")
    add_output_flags(p_version)

    # capabilities
    p_capabilities = sub.add_parser("capabilities", help="Print capability report")
    add_output_flags(p_capabilities)

    # init
    p_init = sub.add_parser("init", help="Initialize state directories and memory")
    p_init.add_argument("--force", action="store_true", help="Overwrite existing config")
    add_output_flags(p_init)

    # doctor
    p_doctor = sub.add_parser("doctor", help="Run comprehensive diagnostics")
    add_output_flags(p_doctor)

    # health
    p_health = sub.add_parser("health", help="Run health check", aliases=["status"])
    add_output_flags(p_health)

    # memory
    mem = sub.add_parser("memory", help="Memory operations")
    mem_sub = mem.add_subparsers(dest="memory_command", metavar="<subcommand>")

    # memory add
    ma = mem_sub.add_parser("add", help="Add a memory record")
    add_output_flags(ma)
    ma.add_argument("text", help="Record content text")
    ma.add_argument("--intent", default="LESSON", help="Intent (default: LESSON)")
    ma.add_argument("--kind", default="observation", help="Kind (default: observation)")
    ma.add_argument("--workspace", default="default", help="Workspace (default: default)")
    ma.add_argument("--agent-id", default="user", help="Agent ID (default: user)")
    ma.add_argument("--run-id", default=None, help="Run ID (auto-generated if omitted)")
    ma.add_argument("--source-ref", default="cli:agent-os", help="Source reference")
    ma.add_argument("--summary", default=None, help="Summary (defaults to truncated text)")

    # memory search
    ms = mem_sub.add_parser("search", help="Search memory records")
    add_output_flags(ms)
    ms.add_argument("query", help="Search query")
    ms.add_argument("--tier", default="short_term", help="Memory tier (default: short_term)")
    ms.add_argument("--limit", type=int, default=10, help="Max results (default: 10)")
    ms.add_argument("--workspace", default=None, help="Filter by workspace")
    ms.add_argument("--intent", default=None, help="Filter by intent")

    # memory list
    ml = mem_sub.add_parser("list", help="List memory records")
    add_output_flags(ml)
    ml.add_argument("--intent", default=None, help="Filter by intent")
    ml.add_argument("--workspace", default=None, help="Filter by workspace")
    ml.add_argument("--limit", type=int, default=20, help="Max results (default: 20)")

    # memory health
    mh = mem_sub.add_parser("health", help="Check memory subsystem health")
    add_output_flags(mh)

    # mcp
    mcp_parser = sub.add_parser("mcp", help="MCP server operations")
    mcp_sub = mcp_parser.add_subparsers(dest="mcp_command", metavar="<subcommand>")

    # mcp serve
    mcp_serve = mcp_sub.add_parser("serve", help="Start the MCP stdio server")
    add_output_flags(mcp_serve)

    # mcp install
    mcp_install = mcp_sub.add_parser("install", help="Install MCP config for a client")
    add_output_flags(mcp_install)
    mcp_install.add_argument("--client", required=True, help="Client: claude, codex, or opencode")
    mcp_install.add_argument("--dry-run", action="store_true", help="Show what would be done")
    mcp_install.add_argument("--force", action="store_true", help="Overwrite existing config or skip parse errors")

    # mcp uninstall
    mcp_uninstall = mcp_sub.add_parser("uninstall", help="Uninstall MCP config for a client")
    add_output_flags(mcp_uninstall)
    mcp_uninstall.add_argument("--client", required=True, help="Client: claude, codex, or opencode")
    mcp_uninstall.add_argument("--dry-run", action="store_true", help="Show what would be done")
    mcp_uninstall.add_argument("--force", action="store_true", help="Skip parse errors")

    return parser


def main() -> None:
    """Main entry point for the unified CLI."""
    # Known new commands
    new_commands = {"version", "capabilities", "init", "doctor", "health", "status", "memory", "mcp"}

    # Check if this is a known new command or a legacy command
    if len(sys.argv) > 1:
        first_arg = sys.argv[1]
        # Skip flags at the top level
        if not first_arg.startswith("-") and first_arg not in new_commands:
            # This is a legacy command — dispatch to scripts/agent-os
            _dispatch_legacy(sys.argv[1:])
            return
        if first_arg == "memory" and len(sys.argv) > 2:
            legacy_memory_commands = {"recall", "promote", "lifecycle"}
            if sys.argv[2] in legacy_memory_commands:
                _dispatch_legacy(sys.argv[1:])
                return

    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(EXIT_USAGE)

    # Route to command handler
    cmd = args.command
    if cmd == "version":
        cmd_version(args)
    elif cmd == "capabilities":
        cmd_capabilities(args)
    elif cmd == "init":
        cmd_init(args)
    elif cmd == "doctor":
        cmd_doctor(args)
    elif cmd in ("health", "status"):
        cmd_health(args)
    elif cmd == "memory":
        mem_cmd = getattr(args, "memory_command", None)
        if not mem_cmd:
            # Print memory subcommand help
            parser.parse_args(["memory", "--help"])
            sys.exit(EXIT_USAGE)
        if mem_cmd == "add":
            cmd_memory_add(args)
        elif mem_cmd == "search":
            cmd_memory_search(args)
        elif mem_cmd == "list":
            cmd_memory_list(args)
        elif mem_cmd == "health":
            cmd_memory_health(args)
        else:
            _die(f"Unknown memory command: {mem_cmd}", EXIT_USAGE)
    elif cmd == "mcp":
        mcp_cmd = getattr(args, "mcp_command", None)
        if not mcp_cmd:
            # Print MCP subcommand help
            parser.parse_args(["mcp", "--help"])
            sys.exit(EXIT_USAGE)
        if mcp_cmd == "serve":
            cmd_mcp_serve(args)
        elif mcp_cmd == "install":
            cmd_mcp_install(args)
        elif mcp_cmd == "uninstall":
            cmd_mcp_uninstall(args)
        else:
            _die(f"Unknown MCP command: {mcp_cmd}", EXIT_USAGE)
    else:
        _die(f"Unknown command: {cmd}", EXIT_USAGE)
