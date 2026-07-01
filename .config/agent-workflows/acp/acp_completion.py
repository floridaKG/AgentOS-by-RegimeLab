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
import sys
import time

AGENT_OS_HOME = os.environ.get("AGENT_OS_HOME", os.path.join(os.path.expanduser("~"), "agent-os"))
RUNS_DIR = os.path.join(AGENT_OS_HOME, ".local", "state", "agent-os", "acp", "runs")


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


def _find_output_path(run_dir):
    """Find the first output artifact in the artifacts directory."""
    artifacts_dir = os.path.join(run_dir, "artifacts")
    if not os.path.isdir(artifacts_dir):
        return ""
    for fname in sorted(os.listdir(artifacts_dir)):
        if fname.startswith("output_"):
            return os.path.join(artifacts_dir, fname)
    return ""


def cmd_check(args):
    run_id = args.run_id
    run_dir = os.path.join(RUNS_DIR, run_id)

    if not os.path.isdir(run_dir):
        print(f"Error: run '{run_id}' not found at {run_dir}", file=sys.stderr)
        sys.exit(1)

    envelope_path = os.path.join(run_dir, "envelope.json")
    if not os.path.exists(envelope_path):
        print(f"Error: envelope.json not found for run '{run_id}'", file=sys.stderr)
        sys.exit(1)

    with open(envelope_path, "r") as f:
        envelope = json.load(f)

    state = envelope.get("state", "unknown")
    events_path = os.path.join(run_dir, "events.jsonl")
    output_path = _find_output_path(run_dir)

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
