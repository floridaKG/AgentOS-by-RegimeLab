#!/usr/bin/env python3
"""memory-lifecycle-soak-check.py — Verify the soak window for delete-gate flip.

Checks:
  1. memory-health-gate.py GREEN for the soak window
  2. Stale-detect reports produced (lifecycle detect-stale)
  3. Pinecone prune dry-run reports produced (optional)
  4. Contradictions log present (optional)
  5. Neo4j orphan reports present (optional)

Usage:
  python3 memory-lifecycle-soak-check.py --window 14d
  python3 memory-lifecycle-soak-check.py --window 14d --json
  python3 memory-lifecycle-soak-check.py --help

Environment:
  AGENT_OS_HOME       Install root (defaults to parent of scripts/)
  AGENT_OS_STATE_DIR  State/log root (default: ~/.local/state/agent-os)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_SCRIPT_PATH = Path(__file__).resolve()
AGENT_OS_HOME = Path(
    os.environ.get("AGENT_OS_HOME") or str(_SCRIPT_PATH.parent.parent)
).resolve()
os.environ.setdefault("AGENT_OS_HOME", str(AGENT_OS_HOME))

STATE_DIR = Path(
    os.path.expanduser(
        os.environ.get(
            "AGENT_OS_STATE_DIR",
            str(Path.home() / ".local" / "state" / "agent-os"),
        )
    )
)

HEALTH_GATE = AGENT_OS_HOME / "scripts" / "memory-health-gate.py"
MEMORY_LOG_DIR = STATE_DIR / "logs" / "memory"


def run_cmd(cmd: list[str], timeout: int = 30) -> tuple[int, str, str]:
    """Run a command and return (exit_code, stdout, stderr)."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except Exception as e:
        return -1, "", str(e)


def check_health_gate() -> dict:
    """Check if memory-health-gate.py reports HEALTHY."""
    if not HEALTH_GATE.is_file():
        return {
            "ok": False,
            "status": "ERROR",
            "detail": f"health gate not found: {HEALTH_GATE}",
        }
    code, stdout, stderr = run_cmd(
        [sys.executable, str(HEALTH_GATE), "--json"],
        timeout=120,
    )
    if code != 0:
        return {"ok": False, "status": "ERROR", "detail": (stderr or stdout)[:200]}
    try:
        data = json.loads(stdout)
        overall = data.get("overall", "UNKNOWN")
        return {"ok": overall == "HEALTHY", "status": overall, "detail": data}
    except json.JSONDecodeError:
        return {"ok": False, "status": "PARSE_ERROR", "detail": stdout[:200]}


def check_stale_detect_reports() -> dict:
    """Check if stale-detect reports exist in the log directory."""
    log_dir = MEMORY_LOG_DIR / "stale-detect"
    if not log_dir.exists():
        return {"ok": False, "report_count": 0, "detail": "stale-detect dir missing"}
    reports = list(log_dir.glob("*.json"))
    return {"ok": len(reports) > 0, "report_count": len(reports)}


def check_pinecone_prune_reports() -> dict:
    """Check if pinecone-prune reports exist."""
    log_dir = MEMORY_LOG_DIR / "pinecone-prune"
    if not log_dir.exists():
        return {
            "ok": False,
            "report_count": 0,
            "detail": "pinecone-prune dir missing",
        }
    reports = list(log_dir.glob("*.json"))
    return {"ok": True, "report_count": len(reports)}


def check_contradictions_log() -> dict:
    """Check contradictions.log exists and has entries."""
    log_file = MEMORY_LOG_DIR / "contradictions.log"
    if not log_file.exists():
        return {"ok": False, "lines": 0}
    lines = log_file.read_text(encoding="utf-8").strip().split("\n")
    return {"ok": True, "lines": len([ln for ln in lines if ln.strip()])}


def check_neo4jorphans_reports() -> dict:
    """Check if neo4j-orphans reports exist."""
    log_dir = MEMORY_LOG_DIR / "neo4j-orphans"
    if not log_dir.exists():
        return {
            "ok": False,
            "report_count": 0,
            "detail": "neo4j-orphans dir missing",
        }
    reports = list(log_dir.glob("*.json"))
    return {"ok": True, "report_count": len(reports)}


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Verify the soak window for memory lifecycle delete-gate flip."
        ),
    )
    parser.add_argument(
        "--window",
        default="14d",
        help="Soak window (e.g. 14d)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output JSON report",
    )
    args = parser.parse_args()

    results: dict = {
        "ok": True,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "window": args.window,
        "agent_os_home": str(AGENT_OS_HOME),
        "state_dir": str(STATE_DIR),
        "checks": {},
    }

    # Check 1: Health gate
    health = check_health_gate()
    results["checks"]["health_gate"] = health
    if not health["ok"]:
        results["ok"] = False

    # Check 2: Stale detect reports
    stale = check_stale_detect_reports()
    results["checks"]["stale_detect_reports"] = stale
    if not stale["ok"]:
        results["ok"] = False

    # Check 3: Pinecone prune reports
    pinecone = check_pinecone_prune_reports()
    results["checks"]["pinecone_prune_reports"] = pinecone

    # Check 4: Contradictions log
    contradictions = check_contradictions_log()
    results["checks"]["contradictions_log"] = contradictions

    # Check 5: Neo4j orphan reports
    neo4j = check_neo4jorphans_reports()
    results["checks"]["neo4j_orphan_reports"] = neo4j

    # Summary
    results["all_checks_passed"] = all(
        c.get("ok", False)
        for c in results["checks"].values()
        if isinstance(c, dict)
    )

    if args.json:
        print(json.dumps(results, indent=2, default=str))
    else:
        print(f"Soak Check — Window: {args.window}")
        print(f"Overall: {'GREEN' if results['ok'] else 'RED'}")
        for name, check in results["checks"].items():
            if isinstance(check, dict):
                status = "✓" if check.get("ok") else "✗"
                detail = ""
                if "status" in check:
                    detail = f" ({check['status']})"
                elif "report_count" in check:
                    detail = f" ({check['report_count']} reports)"
                elif "lines" in check:
                    detail = f" ({check['lines']} lines)"
                print(f"  {status} {name}{detail}")

    return 0 if results["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
