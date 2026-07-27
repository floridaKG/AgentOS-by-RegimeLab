#!/usr/bin/env python3
"""
stumble-review.py — Review and decide on triaged stumbles.

Usage:
  stumble-review list                     Show undecided clusters
  stumble-review show <fingerprint>       Show details for a cluster
  stumble-review decide <fingerprint> <decision> [--note "reason"] [--spec <path>]
    decision: fix | guardrail | document | ignore
  stumble-review decide-bulk --filter <class> --max-age <days> --decision <d> [--note "reason"]
  stumble-review summary                  Show all decisions
  stumble-review export                   Export decisions as markdown

Decisions are persisted in the SQLite DB (st_decisions table).
Triage reports are derived views, not the source of truth.
"""

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ST_DB = Path.home() / ".local/state/agent-os/memory/short_term.sqlite"
REPORT_DIR = Path.home() / ".local/state/agent-os/stumble-reports"


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_conn():
    conn = sqlite3.connect(str(ST_DB))
    conn.row_factory = sqlite3.Row
    return conn


def load_previous_decisions() -> dict:
    """Load decisions from the DB (source of truth)."""
    conn = get_conn()
    try:
        rows = conn.execute("SELECT fingerprint, decision, note, spec_path FROM st_decisions").fetchall()
        return {r["fingerprint"]: {"decision": r["decision"], "note": r["note"], "spec_path": r["spec_path"]} for r in rows}
    finally:
        conn.close()


def latest_report() -> Path | None:
    reports = sorted(REPORT_DIR.glob("triage-*.json"))
    return reports[-1] if reports else None


def load_report(path: Path) -> dict:
    return json.loads(path.read_text())


def save_report(path: Path, data: dict):
    path.write_text(json.dumps(data, indent=2, default=str))


def get_cluster(data: dict, fp: str) -> dict | None:
    for c in data.get("clusters", []):
        if c["fingerprint"] == fp:
            return c
    return None


def build_fresh_triage() -> dict:
    """Build a fresh triage from current DB state (no stale reports)."""
    import hashlib, re

    def extract_stumble_key(summary: str) -> str:
        s = summary.lower().strip()
        s = re.sub(r'^(auto:\s*|explicit:\s*)', '', s)
        s = re.sub(r'[\w/.-]+\.\w+', '<file>', s)
        s = re.sub(r'\bgit\s+(push|pull|fetch|clone|checkout|merge|rebase|commit|add|status|diff)\b', r'git-\1', s)
        s = re.sub(r'\b(rejected|failed|error|denied|timeout|refused|not found|missing|broken)\b', '<error>', s)
        stop = {'a', 'an', 'the', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'from', 'is', 'was', 'and', 'or', 'but'}
        words = [w for w in s.split() if w not in stop]
        words.sort()
        return ' '.join(words)

    def fingerprint(summary: str) -> str:
        key = extract_stumble_key(summary)
        return hashlib.sha256(key.encode()).hexdigest()[:16]

    def age_days(created_at: str) -> int:
        try:
            dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            return (datetime.now(timezone.utc) - dt).days
        except Exception:
            return 0

    def classify(count: int, age: int) -> str:
        if count == 1:
            return "first-occurrence"
        if age <= 7 and count <= 3:
            return "repeat"
        if age <= 7 and count > 3:
            return "systemic"
        if count <= 3:
            return "stale-repeat"
        return "systemic"

    decided = load_previous_decisions()
    conn = get_conn()
    try:
        cur = conn.execute("""
            SELECT id, summary, content, source_ref, workspace, created_at,
                   fingerprint, status, promote_state
            FROM st_records
            WHERE intent = 'STUMBLE'
              AND status NOT IN ('rejected', 'discarded')
        """)
        stumbles = cur.fetchall()
    finally:
        conn.close()

    clusters = {}
    for s in stumbles:
        fp = s["fingerprint"] or fingerprint(s["summary"])
        if fp not in clusters:
            clusters[fp] = {"fingerprint": fp, "rows": [], "source_refs": set(), "workspaces": set()}
        c = clusters[fp]
        c["rows"].append(dict(s))
        c["source_refs"].add(s["source_ref"])
        c["workspaces"].add(s["workspace"])

    triage = []
    for fp, cluster in clusters.items():
        count = len(cluster["rows"])
        oldest = min(r["created_at"] for r in cluster["rows"])
        newest = max(r["created_at"] for r in cluster["rows"])
        age = age_days(oldest)
        d = decided.get(fp, {})
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
            "decision": d.get("decision"),
            "note": d.get("note"),
            "spec_path": d.get("spec_path"),
        }
        triage.append(entry)

    priority = {"systemic": 0, "repeat": 1, "first-occurrence": 2, "stale-repeat": 3}
    triage.sort(key=lambda x: (
        0 if x["decision"] is None else 1,
        priority.get(x["frequency_class"], 9),
        -x["count"],
    ))

    return {
        "ok": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_stumbles": len(stumbles),
        "unique_clusters": len(triage),
        "new_clusters": sum(1 for t in triage if t["decision"] is None),
        "clusters": triage,
    }


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_list():
    data = build_fresh_triage()
    undecided = [c for c in data["clusters"] if c.get("decision") is None]

    if not undecided:
        print("All clusters decided. Nothing to review.")
        return

    print(f"Undecided clusters: {len(undecided)}")
    print()

    for i, c in enumerate(undecided, 1):
        freq_icon = {"systemic": "!", "repeat": "~", "first-occurrence": "o", "stale-repeat": "-"}.get(c["frequency_class"], "?")
        print(f"  {i}. [{freq_icon}] [{c['fingerprint']}] {c['count']}x -- {c['summary'][:70]}")
        print(f"     workspaces: {', '.join(c['workspaces'])}  age: {c['age_days']}d")
        print()


def cmd_show(fp: str):
    data = build_fresh_triage()
    cluster = get_cluster(data, fp)
    if not cluster:
        print(f"Cluster {fp} not found.")
        return

    print(f"Fingerprint:  {cluster['fingerprint']}")
    print(f"Frequency:    {cluster['frequency_class']} ({cluster['count']} occurrences)")
    print(f"Summary:      {cluster['summary']}")
    print(f"Workspaces:   {', '.join(cluster['workspaces'])}")
    print(f"Source refs:  {', '.join(cluster['source_refs'])}")
    print(f"Oldest:       {cluster['oldest']}")
    print(f"Newest:       {cluster['newest']}")
    print(f"Age:          {cluster['age_days']} days")
    print(f"Record IDs:   {', '.join(cluster['ids'])}")
    print(f"Decision:     {cluster.get('decision') or 'NONE'}")
    print(f"Note:         {cluster.get('note') or ''}")
    if cluster.get("spec_path"):
        print(f"Spec:         {cluster['spec_path']}")
    print()
    print(f"Content preview:")
    print(f"  {cluster.get('content_preview', '(none)')}")


def cmd_decide(fp: str, decision: str, note: str = "", spec_path: str = ""):
    if decision not in ("fix", "guardrail", "document", "ignore"):
        print(f"Invalid decision: {decision}")
        print("Valid decisions: fix, guardrail, document, ignore")
        sys.exit(1)

    conn = get_conn()
    try:
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """INSERT INTO st_decisions (fingerprint, decision, note, decided_at, spec_path)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(fingerprint) DO UPDATE SET
                 decision = excluded.decision,
                 note = excluded.note,
                 decided_at = excluded.decided_at,
                 spec_path = excluded.spec_path""",
            (fp, decision, note, now, spec_path or None),
        )
        conn.commit()
        print(f"Decided: {fp} -> {decision}")
        if note:
            print(f"Note: {note}")
    except Exception as e:
        conn.rollback()
        print(f"Error: {e}")
        sys.exit(1)
    finally:
        conn.close()

    # Print next steps
    if decision == "fix":
        print(f"\nNext: Create a spec for this fix.")
    elif decision == "guardrail":
        print(f"\nNext: Add a rule to AGENTS.md or create an extractor rule.")
    elif decision == "document":
        print(f"\nNext: Add to lessons.md or a gotcha doc.")


def cmd_decide_bulk(filter_class: str, max_age_days: int, decision: str, note: str = ""):
    if decision not in ("fix", "guardrail", "document", "ignore"):
        print(f"Invalid decision: {decision}")
        sys.exit(1)

    data = build_fresh_triage()
    targets = [
        c for c in data["clusters"]
        if c.get("decision") is None
        and c["frequency_class"] == filter_class
        and c["age_days"] <= max_age_days
    ]

    if not targets:
        print("No matching undecided clusters found.")
        return

    conn = get_conn()
    try:
        now = datetime.now(timezone.utc).isoformat()
        for c in targets:
            conn.execute(
                """INSERT INTO st_decisions (fingerprint, decision, note, decided_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(fingerprint) DO UPDATE SET
                     decision = excluded.decision, note = excluded.note, decided_at = excluded.decided_at""",
                (c["fingerprint"], decision, note, now),
            )
        conn.commit()
        print(f"Bulk decided {len(targets)} clusters as '{decision}'.")
        for c in targets:
            print(f"  [{c['fingerprint']}] {c['count']}x -- {c['summary'][:60]}")
    except Exception as e:
        conn.rollback()
        print(f"Error: {e}")
        sys.exit(1)
    finally:
        conn.close()


def cmd_summary():
    conn = get_conn()
    try:
        rows = conn.execute("SELECT * FROM st_decisions ORDER BY decided_at DESC").fetchall()
    finally:
        conn.close()

    if not rows:
        print("No decisions recorded.")
        return

    by_decision = {}
    for r in rows:
        d = r["decision"]
        by_decision.setdefault(d, []).append(dict(r))

    print(f"Total decisions: {len(rows)}")
    print()

    icons = {"fix": "F", "guardrail": "G", "document": "D", "ignore": "I"}
    for decision, items in sorted(by_decision.items()):
        icon = icons.get(decision, "?")
        print(f"  [{icon}] {decision}: {len(items)}")
        for c in items[:5]:
            print(f"     [{c['fingerprint']}] -- {c.get('note') or '(no note)'}")
        if len(items) > 5:
            print(f"     ... and {len(items) - 5} more")
        print()


def cmd_export():
    data = build_fresh_triage()
    clusters = data.get("clusters", [])

    print("# Stumble Triage Report")
    print(f"Generated: {data.get('generated_at', '?')}")
    print()

    icons = {"fix": "F", "guardrail": "G", "document": "D", "ignore": "I", None: "?"}
    for c in clusters:
        decision = c.get("decision") or "pending"
        icon = icons.get(c.get("decision"), "?")
        print(f"## [{icon}] {c['summary'][:80]}")
        print(f"- Fingerprint: `{c['fingerprint']}`")
        print(f"- Frequency: {c['frequency_class']} ({c['count']}x)")
        print(f"- Workspaces: {', '.join(c['workspaces'])}")
        print(f"- Age: {c['age_days']} days")
        print(f"- Decision: **{decision}**")
        if c.get("note"):
            print(f"- Note: {c['note']}")
        if c.get("spec_path"):
            print(f"- Spec: {c['spec_path']}")
        print()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]

    if not args or args[0] == "list":
        cmd_list()
    elif args[0] == "show" and len(args) > 1:
        cmd_show(args[1])
    elif args[0] == "decide" and len(args) > 2:
        fp = args[1]
        decision = args[2]
        note = ""
        spec_path = ""
        if "--note" in args:
            idx = args.index("--note")
            if idx + 1 < len(args):
                note = args[idx + 1]
        if "--spec" in args:
            idx = args.index("--spec")
            if idx + 1 < len(args):
                spec_path = args[idx + 1]
        cmd_decide(fp, decision, note, spec_path)
    elif args[0] == "decide-bulk":
        # Parse --filter, --max-age, --decision, --note
        filter_class = ""
        max_age = 999
        decision = ""
        note = ""
        for i, a in enumerate(args[1:], 1):
            if a == "--filter" and i + 1 < len(args):
                filter_class = args[i + 1]
            elif a == "--max-age" and i + 1 < len(args):
                max_age = int(args[i + 1])
            elif a == "--decision" and i + 1 < len(args):
                decision = args[i + 1]
            elif a == "--note" and i + 1 < len(args):
                note = args[i + 1]
        if not filter_class or not decision:
            print("Usage: stumble-review decide-bulk --filter <class> --max-age <days> --decision <d>")
            sys.exit(1)
        cmd_decide_bulk(filter_class, max_age, decision, note)
    elif args[0] == "summary":
        cmd_summary()
    elif args[0] == "export":
        cmd_export()
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
