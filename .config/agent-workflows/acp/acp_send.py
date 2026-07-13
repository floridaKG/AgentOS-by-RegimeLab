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
import sys
import time
import hashlib
import shutil

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


def _ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def _generate_run_id(objective):
    ts = str(int(time.time()))
    h = hashlib.md5(objective.encode()).hexdigest()[:8]
    return f"task-{ts}-{h}"


def _read_envelope(run_id):
    path = os.path.join(RUNS_DIR, run_id, "envelope.json")
    if not os.path.exists(path):
        print(f"Error: run {run_id} not found at {path}", file=sys.stderr)
        sys.exit(1)
    with open(path, "r") as f:
        return json.load(f)


def _write_envelope(run_id, data):
    run_dir = os.path.join(RUNS_DIR, run_id)
    _ensure_dir(run_dir)
    path = os.path.join(run_dir, "envelope.json")
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)


def cmd_send(args):
    """Create and write a new task envelope."""
    role = args.role.lower()
    workspace = args.workspace.lower()

    if role not in VALID_ROLES:
        print(f"Error: invalid role '{role}'. Valid roles: {', '.join(sorted(VALID_ROLES))}", file=sys.stderr)
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
    inbox_dir = os.path.join(INBOX_BASE, workspace)
    _ensure_dir(inbox_dir)
    inbox_path = os.path.join(inbox_dir, f"{run_id}.json")
    with open(inbox_path, "w") as f:
        json.dump(envelope, f, indent=2, default=str)

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
    send_p.add_argument("workspace", help="Target workspace (e.g. home, project-a)")
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
