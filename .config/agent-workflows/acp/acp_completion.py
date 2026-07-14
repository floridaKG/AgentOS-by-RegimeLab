#!/usr/bin/env python3
"""
ACP Completion — Check the completion status of an ACP run.

Usage:
    acp_completion.py <run_id>
    acp_completion.py <run_id> --json
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

AGENT_OS_HOME = os.environ.get("AGENT_OS_HOME", os.path.join(os.path.expanduser("~"), "agent-os"))
RUNS_DIR = os.path.join(AGENT_OS_HOME, ".local", "state", "agent-os", "acp", "runs")

# Regex patterns for safe identifiers (same contract as acp_send.py / acp-daemon)
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

    full_path = base_path
    for part in parts:
        if not part:
            continue
        full_path = full_path / part

    # Check if any component is a symlink
    check_path = base_path
    for part in parts:
        if not part:
            continue
        check_path = check_path / part
        if check_path.is_symlink():
            raise ValueError(f"Symlink not allowed: {check_path}")

    resolved = full_path.resolve()

    try:
        resolved.relative_to(base_path)
    except ValueError:
        raise ValueError(f"Path escapes base directory: {full_path}")

    return str(resolved)


def _get_elapsed_seconds(envelope):
    created = envelope.get("created_at", "")
    if not created:
        return 0.0
    try:
        created_ts = time.mktime(time.strptime(created.split("+")[0].split("-")[0], "%Y-%m-%dT%H:%M:%S"))
        return time.time() - created_ts
    except (ValueError, OSError):
        return 0.0


def _read_first_n(filepath, n=500):
    """Read first N characters of a file."""
    if not os.path.exists(filepath):
        return ""
    try:
        with open(filepath, "r", errors="replace") as f:
            return f.read(n)
    except OSError:
        return ""


def _find_output_path(run_id):
    """Find the first output artifact in the artifacts directory."""
    artifacts_dir = _confined_path(RUNS_DIR, run_id, "artifacts")
    if not os.path.isdir(artifacts_dir):
        return ""
    for fname in sorted(os.listdir(artifacts_dir)):
        if fname.startswith("output_"):
            return _confined_path(RUNS_DIR, run_id, "artifacts", fname)
    return ""


def cmd_check(args):
    run_id = args.run_id

    # Validate run_id before any file access
    try:
        _validate_identifier(run_id, RUN_ID_RE, "run_id")
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    run_dir = _confined_path(RUNS_DIR, run_id)

    if not os.path.isdir(run_dir):
        print(f"Error: run '{run_id}' not found at {run_dir}", file=sys.stderr)
        sys.exit(1)

    envelope_path = _confined_path(RUNS_DIR, run_id, "envelope.json")
    if not os.path.exists(envelope_path):
        print(f"Error: envelope.json not found for run '{run_id}'", file=sys.stderr)
        sys.exit(1)

    with open(envelope_path, "r") as f:
        envelope = json.load(f)

    state = envelope.get("state", "unknown")
    events_path = _confined_path(RUNS_DIR, run_id, "events.jsonl")
    output_path = _find_output_path(run_id)

    # Count events
    event_count = 0
    last_event = ""
    if os.path.exists(events_path):
        with open(events_path, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    event_count += 1
                    try:
                        ev = json.loads(line)
                        last_event = ev.get("event", "")
                    except json.JSONDecodeError:
                        pass

    elapsed = _get_elapsed_seconds(envelope)
    summary = _read_first_n(output_path, 500) if output_path else ""

    has_partial = bool(output_path and summary)

    if args.json:
        result = {
            "schema": "agent_os.acp.completion.v1",
            "run_id": run_id,
            "state": state,
            "classification": _classify(state, envelope),
            "elapsed_seconds": round(elapsed, 1),
            "output_path": output_path or "",
            "has_partial_output": has_partial,
            "events": event_count,
            "last_event": last_event,
            "summary": summary,
            "budget": {"token_cap": 200000, "spent_usd": 0.0},
        }
        print(json.dumps(result, indent=2))
    else:
        print(f"Run ID:        {run_id}")
        print(f"State:         {state}")
        print(f"Elapsed:       {elapsed:.1f}s")
        print(f"Events:        {event_count} ({last_event})")
        print(f"Output:        {output_path or '(none)'}")
        print(f"Has partial:   {'yes' if has_partial else 'no'}")
        print(f"---")
        if summary:
            print(f"Summary (first 500 chars):")
            print(summary)
        else:
            print("(no output yet)")


def _classify(state, envelope):
    """Derive a classification from state and history."""
    if state == "succeeded":
        return "success"
    if state == "cancelled":
        return "cancelled"
    if state == "failed":
        history = envelope.get("history", [])
        for entry in reversed(history):
            reason = entry.get("reason", "")
            if "timeout" in reason.lower() or "worker_timeout" in reason.lower():
                return "timeout"
            if "auth" in reason.lower():
                return "auth_error"
            if "rate" in reason.lower():
                return "rate_limited"
            if "parse" in reason.lower():
                return "parse_error"
        return "failed"
    if state in {"queued", "claimed", "running"}:
        return "in_progress"
    return "unknown"


def main():
    parser = argparse.ArgumentParser(description="Check ACP run completion status")
    parser.add_argument("run_id", help="ACP run ID to check")
    parser.add_argument("--json", action="store_true", help="Output structured JSON")
    args = parser.parse_args()
    cmd_check(args)


if __name__ == "__main__":
    main()
