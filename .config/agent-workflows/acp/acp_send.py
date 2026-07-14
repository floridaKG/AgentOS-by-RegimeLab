#!/usr/bin/env python3
"""
ACP Send — Envelope writer and state machine handler.

Writes a task envelope to the ACP inbox directory and manages
the state machine: queued → claimed → running → succeeded | failed | cancelled.

Usage:
    acp_send.py <role> <workspace> <objective> [--body <text>] [--session <name>] [--json]
    acp_send.py transition <run_id> <new_state> [--reason <text>] [--json]
"""

import argparse
import json
import os
import re
import stat
import sys
import time
import hashlib
import shutil
from pathlib import Path

AGENT_OS_HOME = os.environ.get("AGENT_OS_HOME", os.path.join(os.path.expanduser("~"), "agent-os"))
ACP_ROOT = os.path.join(AGENT_OS_HOME, ".local", "state", "agent-os", "acp")
INBOX_BASE = os.path.join(ACP_ROOT, "inboxes", "workspaces")
RUNS_DIR = os.path.join(ACP_ROOT, "runs")

VALID_ROLES = {"executor", "explorer", "architect", "reviewer", "code_reviewer", "escalation", "hard_escalation"}
VALID_STATES = {"queued", "claimed", "running", "review", "resume", "succeeded", "failed", "cancelled"}
VALID_TRANSITIONS = {
    "queued": {"claimed"},
    "claimed": {"running", "failed", "cancelled"},
    "running": {"succeeded", "failed", "cancelled", "review", "resume"},
    "review": {"running", "succeeded", "failed", "cancelled"},
    "resume": {"running", "succeeded", "failed", "cancelled"},
}

# ── Security helpers ───────────────────────────────────────────────────────

# Regex patterns for safe identifiers (no traversal, no special chars)
WORKSPACE_RE = re.compile(r'^[a-z0-9][a-z0-9_-]*$', re.IGNORECASE)
RUN_ID_RE = re.compile(r'^task-\d{10}-[a-f0-9]{8}$')


def _validate_identifier(value, pattern, field_name):
    """Validate that an identifier matches the expected pattern.

    Raises ValueError if the identifier is invalid or contains traversal attempts.
    """
    if not value or not isinstance(value, str):
        raise ValueError(f"{field_name} must be a non-empty string")

    # Check for path traversal attempts
    if '..' in value or '/' in value or '\\' in value:
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
    except ValueError:
        raise ValueError(f"Path escapes base directory: {full_path}")

    return str(resolved)


def _secure_json_write(path, data):
    """Write JSON data with secure permissions (0o600).

    Creates parent directories if needed. Fails if the file already exists
    with incorrect permissions.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Write with secure permissions
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, 'w') as f:
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


def _generate_run_id(objective):
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


def cmd_send(args):
    """Create and write a new task envelope."""
    role = args.role.lower()
    workspace = args.workspace.lower()

    if role not in VALID_ROLES:
        print(f"Error: invalid role '{role}'. Valid roles: {', '.join(sorted(VALID_ROLES))}", file=sys.stderr)
        sys.exit(1)
    try:
        _validate_identifier(workspace, WORKSPACE_RE, "workspace")
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    run_id = _generate_run_id(args.objective)

    envelope = {
        "schema": "agent_os.acp.envelope.v1",
        "run_id": run_id,
        "role": role,
        "workspace": workspace,
        "objective": args.objective,
        "body": args.body or "",
        "session": args.session or "",
        "with_memory": args.with_memory,
        "state": "queued",
        "created_at": _now(),
        "updated_at": _now(),
        "history": [
            {"state": "queued", "timestamp": _now(), "source": "acp_send"}
        ],
    }

    # Write to inbox
    inbox_dir = _confined_path(INBOX_BASE, workspace)
    _ensure_dir(inbox_dir)
    inbox_path = _confined_path(INBOX_BASE, workspace, f"{run_id}.json")
    _secure_json_write(inbox_path, envelope)

    # Write to runs directory
    _write_envelope(run_id, envelope)

    if args.json:
        print(json.dumps({"run_id": run_id, "state": "queued", "inbox": inbox_path}, indent=2))
    else:
        print(f"RUN_ID={run_id}")
        print(f"Inbox: {inbox_path}")
        print(f"State: queued")

    return run_id


def cmd_transition(args):
    """Transition a run to a new state with validation."""
    run_id = args.run_id
    new_state = args.new_state.lower()

    if new_state not in VALID_STATES:
        print(f"Error: invalid state '{new_state}'. Valid states: {', '.join(sorted(VALID_STATES))}", file=sys.stderr)
        sys.exit(1)

    envelope = _read_envelope(run_id)
    current_state = envelope.get("state")

    # Check valid transition
    allowed = VALID_TRANSITIONS.get(current_state, set())
    if new_state not in allowed and current_state not in {"succeeded", "failed", "cancelled"}:
        print(f"Error: cannot transition from '{current_state}' to '{new_state}'. "
              f"Allowed transitions from '{current_state}': {', '.join(sorted(allowed))}", file=sys.stderr)
        sys.exit(1)

    # Terminal states cannot transition further
    if current_state in {"succeeded", "failed", "cancelled"}:
        print(f"Error: run {run_id} is already in terminal state '{current_state}'", file=sys.stderr)
        sys.exit(1)

    envelope["state"] = new_state
    envelope["updated_at"] = _now()
    envelope.setdefault("history", []).append(
        {"state": new_state, "timestamp": _now(), "source": args.source or "acp_send", "reason": args.reason or ""}
    )
    _write_envelope(run_id, envelope)

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
    send_p.add_argument("workspace", help="Target workspace (e.g. home, work, docs, vault)")
    send_p.add_argument("objective", help="One-line task description")
    send_p.add_argument("--body", default="", help="Detailed task body")
    send_p.add_argument("--session", default="", help="Named session for persistence")
    send_p.add_argument("--json", action="store_true", help="JSON output")
    send_p.add_argument("--with-memory", action="store_true", default=True, help="Inject memory context (default: on)")

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
