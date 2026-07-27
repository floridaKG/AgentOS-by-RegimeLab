#!/usr/bin/env python3
"""
stumble-triage.py — Daily triage of stumble records.

Deduplicates, clusters by fingerprint, counts frequency, classifies
as first-occurrence / repeat / systemic / stale-repeat. Produces a triage report.

Idempotent. Safe to re-run. Only reads ST, writes report to stumble-reports/.
Backfills fingerprints to ST records that lack one.
"""

import hashlib
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────

ST_DB = Path.home() / ".local/state/agent-os/memory/short_term.sqlite"
REPORT_DIR = Path.home() / ".local/state/agent-os/stumble-reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

def extract_stumble_key(summary: str) -> str:
    """Extract a normalized key from a stumble summary for better clustering."""
    s = summary.lower().strip()
    # Remove common prefixes
    s = re.sub(r'^(auto:\s*|explicit:\s*)', '', s)
    # Remove file paths and refs
    s = re.sub(r'[\w/.-]+\.\w+', '<file>', s)
    # Normalize git commands
    s = re.sub(r'\bgit\s+(push|pull|fetch|clone|checkout|merge|rebase|commit|add|status|diff)\b', r'git-\1', s)
    # Normalize error types
    s = re.sub(r'\b(rejected|failed|error|denied|timeout|refused|not found|missing|broken)\b', '<error>', s)
    # Remove articles and stop words
    stop = {'a', 'an', 'the', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'from', 'is', 'was', 'and', 'or', 'but'}
    words = [w for w in s.split() if w not in stop]
    # Sort for word-order invariance
    words.sort()
    return ' '.join(words)


def fingerprint(summary: str) -> str:
    """Fingerprint based on normalized key for better clustering."""
    key = extract_stumble_key(summary)
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def classify(count: int, age_days: int) -> str:
    """Classify frequency with time-windowed logic."""
    if count == 1:
        return "first-occurrence"
    if age_days <= 7 and count <= 3:
        return "repeat"
    if age_days <= 7 and count > 3:
        return "systemic"
    # Old stumbles (>7 days) with low count are stale, not systemic
    if count <= 3:
        return "stale-repeat"
    return "systemic"


def age_days(created_at: str) -> int:
    try:
        dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - dt).days
    except Exception:
        return 0


# ── Load existing report decisions ────────────────────────────────────────────

def load_previous_decisions() -> dict:
    """Load decisions from previous triage reports so we don't re-surface decided clusters."""
    decisions = {}
    for report_path in sorted(REPORT_DIR.glob("triage-*.json")):
        try:
            data = json.loads(report_path.read_text())
            for cluster in data.get("clusters", []):
                fp = cluster.get("fingerprint")
                if fp and cluster.get("decision"):
                    decisions[fp] = cluster["decision"]
        except Exception:
            continue
    return decisions


# ── Backfill fingerprints ─────────────────────────────────────────────────────

def backfill_fingerprints(db: sqlite3.Connection, stumbles: list) -> int:
    """Write fingerprint to ST records that lack one. Returns count updated."""
    updated = 0
    for s in stumbles:
        if s["fingerprint"] is None:
            fp = fingerprint(s["summary"])
            db.execute(
                "UPDATE st_records SET fingerprint = ? WHERE id = ? AND fingerprint IS NULL",
                (fp, s["id"]),
            )
            updated += 1
    if updated > 0:
        db.commit()
    return updated


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if not ST_DB.exists():
        print(json.dumps({"ok": False, "error": f"DB not found: {ST_DB}"}))
        sys.exit(1)

    db = sqlite3.connect(str(ST_DB))
    db.row_factory = sqlite3.Row
    cur = db.cursor()

    # Get all active stumbles not yet triaged/decided
    cur.execute("""
        SELECT id, summary, content, source_ref, workspace, created_at,
               fingerprint, status, promote_state
        FROM st_records
        WHERE intent = 'STUMBLE'
          AND status NOT IN ('rejected', 'discarded')
    """)
    stumbles = cur.fetchall()

    if not stumbles:
        report = {
            "ok": True,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_stumbles": 0,
            "new_clusters": 0,
            "clusters": [],
            "message": "No stumbles to triage.",
        }
        report_path = REPORT_DIR / f"triage-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
        report_path.write_text(json.dumps(report, indent=2, default=str))
        print(json.dumps({"ok": True, "new_clusters": 0, "report": str(report_path)}))
        return

    # Backfill fingerprints to records that lack one
    backfilled = backfill_fingerprints(db, stumbles)

    # Re-read after backfill to get updated fingerprints
    cur.execute("""
        SELECT id, summary, content, source_ref, workspace, created_at,
               fingerprint, status, promote_state
        FROM st_records
        WHERE intent = 'STUMBLE'
          AND status NOT IN ('rejected', 'discarded')
    """)
    stumbles = cur.fetchall()

    # Load previous decisions
    decided = load_previous_decisions()

    # Group by fingerprint
    clusters = {}
    for s in stumbles:
        fp = s["fingerprint"] or fingerprint(s["summary"])
        if fp not in clusters:
            clusters[fp] = {
                "fingerprint": fp,
                "rows": [],
                "source_refs": set(),
                "workspaces": set(),
            }
        c = clusters[fp]
        c["rows"].append(dict(s))
        c["source_refs"].add(s["source_ref"])
        c["workspaces"].add(s["workspace"])

    # Classify
    triage = []
    for fp, cluster in clusters.items():
        count = len(cluster["rows"])
        oldest = min(r["created_at"] for r in cluster["rows"])
        newest = max(r["created_at"] for r in cluster["rows"])
        age = age_days(oldest)

        entry = {
            "fingerprint": fp,
            "count": count,
            "frequency_class": classify(count, age),
            "summary": cluster["rows"][0]["summary"],
            "content_preview": (cluster["rows"][0].get("content") or "")[:300],
            "workspaces": sorted(cluster["workspaces"]),
            "source_refs": sorted(cluster["source_refs"]),
            "oldest": oldest,
            "newest": newest,
            "age_days": age,
            "ids": [r["id"] for r in cluster["rows"]],
            "statuses": list(set(r["status"] for r in cluster["rows"])),
            "promote_states": list(set(r["promote_state"] for r in cluster["rows"])),
            "decision": decided.get(fp),
        }
        triage.append(entry)

    # Sort: undecided first, then systemic > repeat > first-occurrence > stale-repeat
    priority = {"systemic": 0, "repeat": 1, "first-occurrence": 2, "stale-repeat": 3}
    triage.sort(key=lambda x: (
        0 if x["decision"] is None else 1,
        priority.get(x["frequency_class"], 9),
        -x["count"],
    ))

    new_count = sum(1 for t in triage if t["decision"] is None)

    report = {
        "ok": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_stumbles": len(stumbles),
        "unique_clusters": len(triage),
        "new_clusters": new_count,
        "decided_clusters": len(triage) - new_count,
        "backfilled_fingerprints": backfilled,
        "systemic": sum(1 for t in triage if t["frequency_class"] == "systemic" and t["decision"] is None),
        "repeat": sum(1 for t in triage if t["frequency_class"] == "repeat" and t["decision"] is None),
        "first_occurrence": sum(1 for t in triage if t["frequency_class"] == "first-occurrence" and t["decision"] is None),
        "stale_repeat": sum(1 for t in triage if t["frequency_class"] == "stale-repeat" and t["decision"] is None),
        "clusters": triage,
    }

    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_path = REPORT_DIR / f"triage-{now}.json"
    report_path.write_text(json.dumps(report, indent=2, default=str))

    # Print summary
    print(json.dumps({
        "ok": True,
        "report": str(report_path),
        "total_stumbles": len(stumbles),
        "unique_clusters": len(triage),
        "new_clusters": new_count,
        "decided_clusters": len(triage) - new_count,
        "backfilled_fingerprints": backfilled,
        "systemic_new": report["systemic"],
        "repeat_new": report["repeat"],
        "first_occurrence_new": report["first_occurrence"],
        "stale_repeat_new": report["stale_repeat"],
    }, indent=2))


if __name__ == "__main__":
    main()
