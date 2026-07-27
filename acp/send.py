#!/usr/bin/env python3
"""ACP Send — interchange-oriented wrapper around acp_send.py / acp_common.

Usage: send.py --role <role> --workspace <ws> --objective "<text>"
               [--wait] [--wait-timeout <sec>] [--intent <intent>]
               [--session <name>] [--print-run-id]
               [--caller-agent-id <id>] [--target-agent-id <id>]
               [--requested-role <role>] [--parent-run-id <id>]

This is the canonical entry point for ACP interchange dispatch.
Explicit caller/target fields propagate caller identity context from
AGENT_OS_AGENT_* environment variables when available.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

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

AGENTS_YAML = Path(
    os.environ.get(
        "AGENT_OS_AGENTS_YAML",
        str(AGENT_OS_HOME / "registry" / "agents.yaml"),
    )
)
# Fallback to simplified OSS envelope writer
ACP_SEND_PY = ACP_DIR / "acp_send.py"



def _reject_trusted_conflict(flag_name, declared, env_name):
    trusted = os.environ.get(env_name)
    if trusted and declared and trusted != declared:
        print(
            f"ACP_SEND: ERROR — {flag_name} '{declared}' conflicts with "
            f"{env_name}='{trusted}'",
            file=sys.stderr,
        )
        sys.exit(1)


def _load_agent_ids() -> set[str]:
    """Best-effort load of registered agent IDs. Empty set if unavailable."""
    if not AGENTS_YAML.exists():
        return set()
    try:
        import yaml
    except ImportError:
        return set()
    try:
        data = yaml.safe_load(AGENTS_YAML.read_text())
    except Exception:
        return set()
    agents = []
    if isinstance(data, list):
        agents = data
    elif isinstance(data, dict):
        agents = data.get("agents") or []
    return {
        entry.get("id")
        for entry in agents
        if isinstance(entry, dict) and entry.get("id")
    }


def main():
    parser = argparse.ArgumentParser(description="Send an ACP message")

    parser.add_argument(
        "--role",
        default=None,
        help="Operational role for the target (deprecated: use --requested-role)",
    )
    parser.add_argument("--workspace", default="home")
    parser.add_argument("--objective", required=True)
    parser.add_argument("--intent", default=None)
    parser.add_argument("--wait", action="store_true")
    parser.add_argument("--wait-timeout", type=int, default=1800)
    parser.add_argument("--session", default=None)
    parser.add_argument("--print-run-id", action="store_true")
    # -- Interchange caller/target fields --
    parser.add_argument(
        "--caller-agent-id",
        default=None,
        help="Caller agent ID (default: auto-detect from AGENT_OS_AGENT_ID)",
    )
    parser.add_argument("--caller-role", default=None, help="Caller's current role")
    parser.add_argument("--caller-provider", default=None, help="Caller's provider")
    parser.add_argument("--caller-model", default=None, help="Caller's model")
    parser.add_argument(
        "--target-agent-id",
        default=None,
        help="Explicit target agent ID (overrides --role)",
    )
    parser.add_argument(
        "--requested-role",
        default=None,
        help="Behavioral role requested of the target",
    )
    parser.add_argument(
        "--parent-run-id",
        default=None,
        help="Parent ACP run ID (auto-derived from AGENT_OS_ACP_ACTIVE_RUN_ID)",
    )
    parser.add_argument("--model", default=None, help="Explicit model override")
    parser.add_argument("--provider", default=None, help="Explicit provider override")
    parser.add_argument(
        "--strict-model",
        action="store_true",
        help="Require the explicit model to be applied without fallback",
    )
    # -- Interchange execution options --
    parser.add_argument(
        "--mode",
        default="oneshot",
        choices=["oneshot", "persistent"],
        help="Execution mode",
    )
    parser.add_argument(
        "--return-mode",
        default="sync",
        choices=["sync", "async"],
        help="Return mode (sync requires no active daemon run)",
    )
    parser.add_argument("--allow-paid", action="store_true", help="Allow paid cost class")
    parser.add_argument("--token-cap", type=int, default=12000, help="Token cap for dispatch")
    parser.add_argument("--max-cost-usd", type=float, default=0.0, help="Max cost in USD")
    parser.add_argument("--no-memory", action="store_true", help="Disable memory injection")
    parser.add_argument(
        "--notify-via-agent-mail",
        action="store_true",
        help="Send Agent Mail notification on completion",
    )
    parser.add_argument("--json", action="store_true", help="Machine-readable JSON output")

    args = parser.parse_args()

    # ── Nested --wait deadlock guard ────────────────────────────────────────
    active_run_id = os.environ.get("AGENT_OS_ACP_ACTIVE_RUN_ID", "")
    if active_run_id and args.wait:
        print(
            "ACP_SEND: REJECTED — synchronous --wait dispatch is not"
            " allowed from inside a daemon-launched worker"
            f" (AGENT_OS_ACP_ACTIVE_RUN_ID={active_run_id})."
            " Nested --wait would deadlock because the daemon is"
            " blocked on this worker.  Use fire-and-forget dispatch"
            " (omit --wait) or dispatch from outside the daemon.",
            file=sys.stderr,
        )
        sys.exit(1)

    # ── Derive caller identity ──────────────────────────────────────────────
    _reject_trusted_conflict("--caller-agent-id", args.caller_agent_id, "AGENT_OS_AGENT_ID")
    _reject_trusted_conflict("--caller-role", args.caller_role, "AGENT_OS_AGENT_ROLE")
    _reject_trusted_conflict(
        "--caller-provider", args.caller_provider, "AGENT_OS_AGENT_PROVIDER"
    )
    _reject_trusted_conflict("--caller-model", args.caller_model, "AGENT_OS_AGENT_MODEL")

    caller_agent_id = (
        os.environ.get("AGENT_OS_AGENT_ID") or args.caller_agent_id or "worker"
    )
    caller_role = (
        os.environ.get("AGENT_OS_AGENT_ROLE") or args.caller_role or "unknown"
    )
    caller_provider = (
        os.environ.get("AGENT_OS_AGENT_PROVIDER") or args.caller_provider or "unknown"
    )
    caller_model = (
        os.environ.get("AGENT_OS_AGENT_MODEL") or args.caller_model or "unknown"
    )
    caller_identity_source = (
        "trusted" if os.environ.get("AGENT_OS_AGENT_ID") else "declared"
    )

    # Soft registry validation (optional PyYAML)
    agent_ids = _load_agent_ids()
    if agent_ids:
        local_agent_ids = {"worker", "orchestrator", "router"}
        if (
            args.target_agent_id
            and args.target_agent_id not in agent_ids
            and args.target_agent_id not in local_agent_ids
        ):
            print(
                f"ACP_SEND: ERROR — target agent {args.target_agent_id!r} "
                "is not a registered agent",
                file=sys.stderr,
            )
            sys.exit(1)
        if (
            caller_agent_id not in {"worker", "orchestrator", "router"}
            and caller_agent_id not in agent_ids
            and caller_agent_id not in local_agent_ids
        ):
            print(
                f"ACP_SEND: ERROR — caller agent {caller_agent_id!r} is not registered",
                file=sys.stderr,
            )
            sys.exit(1)

    # ── Derive parent_run_id ────────────────────────────────────────────────
    parent_run_id = os.environ.get("AGENT_OS_ACP_ACTIVE_RUN_ID") or args.parent_run_id
    if args.parent_run_id and os.environ.get("AGENT_OS_ACP_ACTIVE_RUN_ID"):
        if args.parent_run_id != parent_run_id:
            print(
                f"ACP_SEND: ERROR — --parent-run-id '{args.parent_run_id}' conflicts "
                f"with AGENT_OS_ACP_ACTIVE_RUN_ID='{parent_run_id}'",
                file=sys.stderr,
            )
            sys.exit(1)

    # ── Resolve intent from role if not explicit ────────────────────────────
    resolve_role = args.requested_role or args.role
    intent = args.intent or {
        "architect": "SPEC",
        "executor": "IMPLEMENT",
        "reviewer": "REVIEW",
        "code_reviewer": "REVIEW",
        "explorer": "RESEARCH",
        "escalation": "HELP",
        "hard_escalation": "HELP",
    }.get(resolve_role, "DOCS")

    # ── Generate run ID + ensure state dirs ─────────────────────────────────
    acp_common.ensure_state_dirs()
    run_id = acp_common.generate_run_id(workspace=args.workspace, slug="acp")
    workspace = acp_common.normalize_workspace(args.workspace)

    # Generic allowed paths only — no private project roots
    home_path = str(AGENT_OS_HOME)
    ws_path = home_path
    roles_workspaces = {}
    try:
        import tomllib

        with open(acp_common.ROLES_TOML, "rb") as f:
            roles_data = tomllib.load(f)
        roles_workspaces = roles_data.get("workspaces") or {}
        if isinstance(roles_workspaces, dict) and workspace in roles_workspaces:
            entry = roles_workspaces[workspace]
            if isinstance(entry, dict) and entry.get("path"):
                ws_path = os.path.expandvars(entry["path"])
            elif isinstance(entry, str):
                ws_path = os.path.expandvars(entry)
    except Exception:
        pass

    packet = {
        "run_id": run_id,
        "parent_agent": caller_agent_id,
        "workspace": workspace,
        "intent": intent,
        "objective": args.objective,
        "allowed_paths": [ws_path, home_path],
        "denied_paths": ["/.ssh/", "/.mssh/", "/.env"],
        "boot_docs": [
            str(AGENT_OS_HOME / "AGENTS.md"),
            str(Path(ws_path) / "AGENTS.md"),
        ],
        "skills": [],
        "git_policy": "read-only",
        "secrets_policy": "none",
        "verification": "Task complete",
        "report_path": None,
        "status_update_path": None,
        # Interchange fields
        "caller_agent_id": caller_agent_id,
        "caller_role": caller_role,
        "caller_provider": caller_provider,
        "caller_model": caller_model,
        "caller_identity_source": caller_identity_source,
        "requested_role": args.requested_role,
        "target_agent_id": args.target_agent_id,
        "parent_run_id": parent_run_id,
        "interchange_mode": args.mode,
        "interchange_return_mode": args.return_mode,
        "resolved_model": args.model or "",
        "resolved_provider": args.provider or "",
        "strict_model": args.strict_model,
        "interchange_depth": int(os.environ.get("AGENT_OS_INTERCHANGE_DEPTH", "0")),
        "interchange_ancestry": os.environ.get("AGENT_OS_INTERCHANGE_ANCESTRY", ""),
        "notify_via_agent_mail": args.notify_via_agent_mail,
        "memory": not args.no_memory,
    }
    packet_path = acp_common.TMP_DIR / f"packet_{run_id}.json"
    acp_common.TMP_DIR.mkdir(parents=True, exist_ok=True)
    packet_path.write_text(json.dumps(packet, indent=2))

    # Optional context-pack injection
    context_pack_script = AGENT_OS_HOME / "scripts" / "context-pack.sh"
    context_block = ""
    if context_pack_script.is_file():
        try:
            result = subprocess.run(
                ["bash", str(context_pack_script), args.objective, "--budget=4000"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0 and result.stdout.strip():
                context_block = result.stdout.strip() + "\n\n---\n\n"
        except (subprocess.TimeoutExpired, OSError):
            pass

    body = context_block + args.objective

    # ── Enqueue the canonical modern envelope ─────────────────────────────
    if caller_agent_id == "orchestrator":
        reply_to = acp_common.INBOX_ORCHESTRATOR
    else:
        reply_to = acp_common.INBOX_AGENTS / caller_agent_id
        reply_to.mkdir(parents=True, exist_ok=True)

    requested_role = args.requested_role or args.role
    target = {
        "workspace": workspace,
        "role": requested_role or resolve_role,
    }
    if args.target_agent_id:
        target["agent_id"] = args.target_agent_id
    if args.model:
        target["model"] = args.model
    if args.provider:
        target["provider"] = args.provider

    message = {
        "schema": "agent_os.acp.envelope.v1",
        "message_id": acp_common.generate_message_id(),
        "run_id": run_id,
        "from": {
            "agent_id": caller_agent_id,
            "provider": caller_provider,
            "model": caller_model,
            "role": caller_role,
        },
        "to": target,
        "intent": "ASSIGN",
        "reply_to": str(reply_to),
        "summary": args.objective,
        "body": body,
        "packet": packet,
        "session_name": args.session or "",
        "state": "queued",
        "created_at": acp_common._utc_now(),
        "budget": {
            "cost_class": "paid" if args.allow_paid else "free",
            "allow_paid": bool(args.allow_paid),
            "max_usd": float(args.max_cost_usd or 0.0),
            "token_cap": int(args.token_cap or 12000),
            "spent_usd": 0.0,
        },
    }
    inbox = acp_common.INBOX_WORKSPACES / workspace
    inbox.mkdir(parents=True, exist_ok=True)
    acp_common.ensure_run_dir(run_id)
    acp_common.write_run_record(
        run_id,
        acp_common.build_run_record(
            run_id=run_id,
            workspace=workspace,
            packet=packet,
            reply_to=str(reply_to),
            state="queued",
            message_id=message["message_id"],
            timeout_seconds=args.wait_timeout,
        ),
    )
    acp_common.write_budget_json(run_id, message["budget"])
    # Also write envelope.json for OSS completion tooling compatibility
    env_path = acp_common.RUNS / run_id / "envelope.json"
    env_path.write_text(json.dumps(message, indent=2), encoding="utf-8")
    acp_common.atomic_write(inbox, f"{run_id}.json", message)
    acp_common.append_event(
        run_id,
        "message_sent",
        {
            "message_id": message["message_id"],
            "intent": "ASSIGN",
            "to_inbox": str(inbox),
            "target_agent_id": args.target_agent_id,
        },
    )

    if args.print_run_id:
        print(f"RUN_ID={run_id}")
    elif args.json:
        print(
            json.dumps(
                {"run_id": run_id, "state": "queued", "inbox": str(inbox / f"{run_id}.json")},
                indent=2,
            )
        )
    else:
        print(f"RUN_ID={run_id}")
        print(f"Inbox: {inbox / f'{run_id}.json'}")
        print("State: queued")

    # ── Wait if requested (inline poll — acp_wait.py is deferred) ─────────
    if args.wait:
        terminal = acp_common.TERMINAL_RUN_STATES
        import time

        deadline = time.time() + max(1, args.wait_timeout)
        while time.time() < deadline:
            run = acp_common.read_run_json(run_id) or {}
            state = run.get("state") or run.get("status") or "queued"
            if state in terminal:
                if args.json:
                    print(json.dumps({"run_id": run_id, "state": state}, indent=2))
                else:
                    print(f"Final state: {state}")
                sys.exit(0 if state == "succeeded" else 1)
            time.sleep(1)
        print(
            f"ACP_SEND: timeout waiting for run {run_id} after {args.wait_timeout}s",
            file=sys.stderr,
        )
        sys.exit(124)


if __name__ == "__main__":
    main()
