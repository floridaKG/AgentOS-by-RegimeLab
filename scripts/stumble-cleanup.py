#!/usr/bin/env python3
"""
stumble-cleanup.py — Clean up old triage reports and check resolution status.

Run monthly or as part of cron. Removes triage reports older than 30 days.
Checks if "fix" decisions haven't recurred in 14 days (likely resolved).
"""

import json
import sqlite3
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ST_DB = Path.home() / ".local/state/agent-os/memory/short_term.sqlite"
REPORT_DIR = Path.home() / ".local/state/agent-os/stumble-reports"


def cleanup_old_reports(max_age_days: int = 30) -> int:
    """Remove triage reports older than max_age_days. Returns count removed."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    removed = 0
    for report_path in REPORT_DIR.glob("triage-*.json"):
        try:
            # Extract timestamp from filename: triage-YYYYMMDDTHHMMSSZ.json
            ts_str = report_path.stem.replace("triage-", "")
            report_time = datetime.strptime(ts_str, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
            if report_time < cutoff:
                report_path.rename(report_path.with_suffix(".json.archived"))
                removed += 1
        except Exception:
            continue
    return removed


def check_resolution() -> list:
    """Check if 'fix' or 'guardrail' decisions haven't recurred in 14 days."""
    conn = sqlite3.connect(str(ST_DB))
    conn.row_factory = sqlite3.Row
    try:
        decisions = conn.execute(
            "SELECT fingerprint, decision, note, decided_at FROM st_decisions WHERE decision IN ('fix', 'guardrail')"
        ).fetchall()
    finally:
        conn.close()

    resolved = []
    now = datetime.now(timezone.utc)

    for d in decisions:
        decided_at = datetime.fromisoformat(d["decided_at"].replace("Z", "+00:00"))
        days_since = (now - decided_at).days

        if days_since < 14:
            continue

        # Check if any stumbles with this fingerprint exist after the decision
        conn2 = sqlite3.connect(str(ST_DB))
        conn2.row_factory = sqlite3.Row
        try:
            recent = conn2.execute(
                """SELECT count(*) as cnt FROM st_records
                   WHERE intent = 'STUMBLE' AND fingerprint = ? AND created_at > ?""",
                (d["fingerprint"], d["decided_at"]),
            ).fetchone()
        finally:
            conn2.close()

        if recent["cnt"] == 0:
            resolved.append({
                "fingerprint": d["fingerprint"],
                "decision": d["decision"],
                "note": d["note"],
                "days_since_decided": days_since,
            })

    return resolved


def main():
    removed = cleanup_old_reports()
    resolved = check_resolution()

    result = {
        "ok": True,
        "reports_archived": removed,
        "resolved_count": len(resolved),
        "resolved": resolved,
    }

    if resolved:
        result["message"] = f"{len(resolved)} decision(s) likely resolved (no recurrence in 14+ days)."
        for r in resolved:
            print(f"  Cluster {r['fingerprint']} (decided: {r['decision']}) has not recurred in {r['days_since_decided']} days. Likely resolved.")

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
