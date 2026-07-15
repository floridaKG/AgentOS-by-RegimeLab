#!/usr/bin/env python3
"""
ACP Send — Envelope writer and state machine handler.

Writes a task envelope to the ACP inbox directory and manages
the state machine: queued → claimed → running → succeeded | failed | cancelled.

Uses acp_common for shared path/state utilities. Keeps the simplified OSS
CLI (send/transition) for acp-task and smoke tests, and adds interchange
fields so multi-agent dispatch can carry identity/budget metadata.

Usage:
    acp_send.py send <role> <workspace> <objective> [--body <text>] [--session <name>] [--json]
    acp_send.py transition <run_id> <new_state> [--reason <text>] [--json]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import time
from pathlib import Path

# Shared ACP library (same directory)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import acp_common  # noqa: E402

# Prefer acp_common roots (AGENT_OS_HOME / AGENT_OS_ACP_ROOT)
ACP_ROOT = str(acp_common.ACP_ROOT)
INBOX_BASE = str(acp_common.INBOX_WORKSPACES)
RUNS_DIR = str(acp_common.RUNS)

VALID_ROLES = {
    "executor",
    "explorer",
    "architect",
    "reviewer",
    "code_reviewer",
    "escalation",
    "hard_escalation",
}
VALID_STATES = {
    "queued",
    "claimed",
    "running",
    "review",
    "resume",
    "succeeded",
    "failed",
    "cancelled",
}
VALID_TRANSITIONS = {
    "queued": {"claimed"},
    "claimed": {"running", "failed", "cancelled"},
    "running": {"succeeded", "failed", "cancelled", "review", "resume"},
    "review": {"running", "succeeded", "failed", "cancelled"},
    "resume": {"running", "succeeded", "failed", "cancelled"},
}

# Regex patterns for safe identifiers (no traversal, no special chars)
# OSS smoke / acp-task use task-<epoch>-<md5>
WORKSPACE_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$", re.IGNORECASE)
RUN_ID_RE = re.compile(
    r"^(?:task-\d{10}-[a-f0-9]{8}|[0-9]{8}-[0-9]{6}-[a-z0-9_-]+-[a-z0-9_-]+-[A-Za-z0-9]{4})$"
)


def _validate_identifier(value, pattern, field_name):
    """Validate that an identifier matches the expected pattern.

    Raises ValueError if the identifier is invalid or contains traversal attempts.
    """
    if not value or not isinstance(value, str):
        raise ValueError(f"{field_name} must be a non-empty string")

    # Check for path traversal attempts
    if ".." in value or "/" in value or "\\" in value:
        raise ValueError(f"{field_name} contains path traversal: {value}")

    if not pattern.match(value):
        raise ValueError(f"{field_name} does not match required pattern: {value}")

    return value


def _confined_path(base, *parts):
    """Resolve a path and ensure it stays within the base directory.

    Raises ValueError if:
    - The resolved path escapes the base directory
    - Any part is a symlink (symlinks are not allowed for security)
    - The path contains traversal attempts
    """
    base_path = Path(base).resolve()

    # Build the full path
    full_path = base_path
    for part in parts:
        if not part:
            continue
        full_path = full_path / part

    # Check if any component is a symlink (reject all symlinks for security)
    check_path = base_path
    for part in parts:
        if not part:
            continue
        check_path = check_path / part
        if check_path.is_symlink():
            raise ValueError(f"Symlink not allowed: {check_path}")

    # Resolve the final path
    resolved = full_path.resolve()

    # Check if resolved path is within base
    try:
        resolved.relative_to(base_path)
    except ValueError as exc:
        raise ValueError(f"Path escapes base directory: {full_path}") from exc

    return str(resolved)


def _secure_json_write(path, data):
    """Write JSON data with secure permissions (0o600).

    Creates parent directories if needed.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Write with secure permissions
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w") as f:
            fd = None
            json.dump(data, f, indent=2, default=str)
    except Exception:
        if fd is not None:
            os.close(fd)
        raise

    # Verify permissions
    actual_mode = stat.S_IMODE(path.stat().st_mode)
    if actual_mode != 0o600:
        raise PermissionError(f"File permissions {oct(actual_mode)} != expected 0o600")


def _ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def _generate_task_run_id(objective: str) -> str:
    """OSS-compatible run id used by acp-task / smoke tests.

    Format: task-<epoch10>-<md5[:8]>
    """
    ts = str(int(time.time()))
    h = hashlib.md5(objective.encode()).hexdigest()[:8]
    return f"task-{ts}-{h}"


def _read_envelope(run_id):
    _validate_identifier(run_id, RUN_ID_RE, "run_id")
    path = _confined_path(RUNS_DIR, run_id, "envelope.json")
    if not os.path.exists(path):
        print(f"Error: run {run_id} not found at {path}", file=sys.stderr)
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_envelope(run_id, data):
    _validate_identifier(run_id, RUN_ID_RE, "run_id")
    run_dir = _confined_path(RUNS_DIR, run_id)
    _ensure_dir(run_dir)
    path = _confined_path(RUNS_DIR, run_id, "envelope.json")
    _secure_json_write(path, data)


def _interchange_fields(args) -> dict:
    """Optional interchange identity fields for multi-agent dispatch."""
    fields = {}
    # Trusted env vars take precedence when present
    caller_agent_id = (
        os.environ.get("AGENT_OS_AGENT_ID")
        or getattr(args, "caller_agent_id", None)
        or ""
    )
    if caller_agent_id:
        fields["caller_agent_id"] = caller_agent_id
        fields["caller_identity_source"] = (
            "trusted" if os.environ.get("AGENT_OS_AGENT_ID") else "declared"
        )
    for attr, env_name, key in (
        ("caller_role", "AGENT_OS_AGENT_ROLE", "caller_role"),
        ("caller_provider", "AGENT_OS_AGENT_PROVIDER", "caller_provider"),
        ("caller_model", "AGENT_OS_AGENT_MODEL", "caller_model"),
    ):
        val = os.environ.get(env_name) or getattr(args, attr, None)
        if val:
            fields[key] = val
    parent_run_id = os.environ.get("AGENT_OS_ACP_ACTIVE_RUN_ID") or getattr(
        args, "parent_run_id", None
    )
    if parent_run_id:
        fields["parent_run_id"] = parent_run_id
    if getattr(args, "target_agent_id", None):
        fields["target_agent_id"] = args.target_agent_id
    if getattr(args, "requested_role", None):
        fields["requested_role"] = args.requested_role
    if getattr(args, "model", None):
        fields["resolved_model"] = args.model
    if getattr(args, "provider", None):
        fields["resolved_provider"] = args.provider
    if getattr(args, "allow_paid", False):
        fields["allow_paid"] = True
    token_cap = getattr(args, "token_cap", None)
    if token_cap is not None:
        fields["token_cap"] = token_cap
    max_cost = getattr(args, "max_cost_usd", None)
    if max_cost is not None and max_cost > 0:
        fields["max_cost_usd"] = max_cost
    depth = os.environ.get("AGENT_OS_INTERCHANGE_DEPTH")
    if depth:
        fields["interchange_depth"] = int(depth)
    ancestry = os.environ.get("AGENT_OS_INTERCHANGE_ANCESTRY")
    if ancestry:
        fields["interchange_ancestry"] = ancestry
    return fields


def cmd_send(args):
    """Create and write a new task envelope."""
    role = args.role.lower()
    workspace = acp_common.normalize_workspace(args.workspace.lower())

    if role not in VALID_ROLES:
        print(
            f"Error: invalid role '{role}'. Valid roles: {', '.join(sorted(VALID_ROLES))}",
            file=sys.stderr,
        )
        sys.exit(1)
    try:
        _validate_identifier(workspace, WORKSPACE_RE, "workspace")
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    acp_common.ensure_state_dirs()
    run_id = _generate_task_run_id(args.objective)
    ix = _interchange_fields(args)

    envelope = {
        "schema": "agent_os.acp.envelope.v1",
        "message_id": acp_common.generate_message_id(),
        "run_id": run_id,
        "role": role,
        "workspace": workspace,
        "objective": args.objective,
        "body": args.body or "",
        "session": args.session or "",
        "with_memory": bool(getattr(args, "with_memory", True)),
        "state": "queued",
        "created_at": _now(),
        "updated_at": _now(),
        "history": [
            {"state": "queued", "timestamp": _now(), "source": "acp_send"}
        ],
        # Interchange-friendly to/from blocks
        "from": {
            "agent_id": ix.get("caller_agent_id", "worker"),
            "role": ix.get("caller_role", "unknown"),
            "provider": ix.get("caller_provider", "unknown"),
            "model": ix.get("caller_model", "unknown"),
        },
        "to": {
            "workspace": workspace,
            "role": role,
            **(
                {"agent_id": ix["target_agent_id"]}
                if ix.get("target_agent_id")
                else {}
            ),
            **({"model": ix["resolved_model"]} if ix.get("resolved_model") else {}),
            **(
                {"provider": ix["resolved_provider"]}
                if ix.get("resolved_provider")
                else {}
            ),
        },
        "intent": "ASSIGN",
        "budget": {
            "cost_class": "paid" if ix.get("allow_paid") else "free",
            "allow_paid": bool(ix.get("allow_paid", False)),
            "max_usd": float(ix.get("max_cost_usd", 0.0) or 0.0),
            "token_cap": int(ix.get("token_cap", 12000) or 12000),
            "spent_usd": 0.0,
        },
        "packet": {
            "run_id": run_id,
            "workspace": workspace,
            "objective": args.objective,
            "git_policy": "read-only",
            "secrets_policy": "none",
            **{k: v for k, v in ix.items()},
        },
    }

    # Write to inbox
    inbox_dir = _confined_path(INBOX_BASE, workspace)
    _ensure_dir(inbox_dir)
    inbox_path = _confined_path(INBOX_BASE, workspace, f"{run_id}.json")
    _secure_json_write(inbox_path, envelope)

    # Write to runs directory (envelope + run.json + budget for interchange)
    _write_envelope(run_id, envelope)
    acp_common.ensure_run_dir(run_id)
    acp_common.write_run_record(
        run_id,
        acp_common.build_run_record(
            run_id=run_id,
            message_id=envelope["message_id"],
            workspace=workspace,
            state="queued",
            packet=envelope.get("packet"),
        ),
    )
    acp_common.write_budget_json(run_id, envelope["budget"])
    acp_common.append_event(
        run_id,
        "message_sent",
        {
            "message_id": envelope["message_id"],
            "intent": "ASSIGN",
            "to_inbox": inbox_path,
            "role": role,
        },
    )

    if args.json:
        print(
            json.dumps(
                {"run_id": run_id, "state": "queued", "inbox": inbox_path},
                indent=2,
            )
        )
    else:
        print(f"RUN_ID={run_id}")
        print(f"Inbox: {inbox_path}")
        print("State: queued")

    return run_id


def cmd_transition(args):
    """Transition a run to a new state with validation."""
    run_id = args.run_id
    new_state = args.new_state.lower()

    if new_state not in VALID_STATES:
        print(
            f"Error: invalid state '{new_state}'. Valid states: {', '.join(sorted(VALID_STATES))}",
            file=sys.stderr,
        )
        sys.exit(1)

    envelope = _read_envelope(run_id)
    current_state = envelope.get("state")

    # Check valid transition
    allowed = VALID_TRANSITIONS.get(current_state, set())
    if new_state not in allowed and current_state not in {
        "succeeded",
        "failed",
        "cancelled",
    }:
        print(
            f"Error: cannot transition from '{current_state}' to '{new_state}'. "
            f"Allowed transitions from '{current_state}': {', '.join(sorted(allowed))}",
            file=sys.stderr,
        )
        sys.exit(1)

    # Terminal states cannot transition further
    if current_state in {"succeeded", "failed", "cancelled"}:
        print(
            f"Error: run {run_id} is already in terminal state '{current_state}'",
            file=sys.stderr,
        )
        sys.exit(1)

    envelope["state"] = new_state
    envelope["updated_at"] = _now()
    envelope.setdefault("history", []).append(
        {
            "state": new_state,
            "timestamp": _now(),
            "source": args.source or "acp_send",
            "reason": args.reason or "",
        }
    )
    _write_envelope(run_id, envelope)

    # Mirror into run.json via acp_common when present
    try:
        acp_common.transition_run_state(
            run_id,
            new_state,
            message=args.reason or "",
            blocked_reason=args.reason if new_state in {"failed", "cancelled"} else None,
        )
    except Exception:
        # Envelope is authoritative for simplified OSS path
        pass

    if args.json:
        print(json.dumps({"run_id": run_id, "state": new_state}, indent=2))
    else:
        print(f"RUN_ID={run_id}: {current_state} → {new_state}")


def main():
    parser = argparse.ArgumentParser(description="ACP Envelope Writer & State Machine")
    sub = parser.add_subparsers(dest="command", help="Sub-command")

    # send subcommand
    send_p = sub.add_parser("send", help="Send a new task envelope")
    send_p.add_argument("role", help="Agent role (e.g. executor, explorer)")
    send_p.add_argument(
        "workspace", help="Target workspace (e.g. home, work, docs, scratch)"
    )
    send_p.add_argument("objective", help="One-line task description")
    send_p.add_argument("--body", default="", help="Detailed task body")
    send_p.add_argument("--session", default="", help="Named session for persistence")
    send_p.add_argument("--json", action="store_true", help="JSON output")
    send_p.add_argument(
        "--with-memory",
        action="store_true",
        default=True,
        help="Inject memory context (default: on)",
    )
    # Interchange optional fields
    send_p.add_argument("--caller-agent-id", default=None)
    send_p.add_argument("--caller-role", default=None)
    send_p.add_argument("--caller-provider", default=None)
    send_p.add_argument("--caller-model", default=None)
    send_p.add_argument("--target-agent-id", default=None)
    send_p.add_argument("--requested-role", default=None)
    send_p.add_argument("--parent-run-id", default=None)
    send_p.add_argument("--model", default=None, help="Explicit model override")
    send_p.add_argument("--provider", default=None, help="Explicit provider override")
    send_p.add_argument("--allow-paid", action="store_true")
    send_p.add_argument("--token-cap", type=int, default=None)
    send_p.add_argument("--max-cost-usd", type=float, default=None)

    # transition subcommand
    trans_p = sub.add_parser("transition", help="Transition a run's state")
    trans_p.add_argument("run_id", help="Run ID to transition")
    trans_p.add_argument("new_state", help="Target state")
    trans_p.add_argument("--reason", default="", help="Optional reason for transition")
    trans_p.add_argument("--source", default="acp_send", help="Source of the transition")
    trans_p.add_argument("--json", action="store_true", help="JSON output")

    args = parser.parse_args()

    if args.command == "send":
        cmd_send(args)
    elif args.command == "transition":
        cmd_transition(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
