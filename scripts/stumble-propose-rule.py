#!/usr/bin/env python3
"""
stumble-propose-rule.py — Generate reviewed proposals from stumble clusters.

Reads the current stumble state through stumble-review triage, then writes
proposal files under proposals/stumble-rules/.

Usage:
    python3 stumble-propose-rule.py                          # generate proposals
    python3 stumble-propose-rule.py --summary                # print summary only
    python3 stumble-propose-rule.py --summary --json          # JSON summary
    python3 stumble-propose-rule.py --dry-run                 # show what would be created

Proposal schema:
    fingerprint, created_at, workspace, source_refs, frequency_class,
    count, decision: pending, proposal_type, target, candidate, review
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

HOME = Path.home()
COCKPIT = HOME / "agent-os"
PROPOSALS_DIR = COCKPIT / "proposals" / "stumble-rules"

# High-risk keywords that trigger auto-proposal even for first-occurrence clusters
HIGH_RISK_KEYWORDS = {
    "credential", "delete", "rm ", "rm -rf", "git write", "commit", "push",
    "sandbox", "governance drift", "password", "token", "ssh key", "api key",
    "secret", "environment variable leak", "git config", ".env",
}


def get_stumble_data() -> dict[str, Any] | None:
    """Get stumble data from stumble-review's internal SQLite tables."""
    st_db = HOME / ".local/state/agent-os/memory/short_term.sqlite"
    if not st_db.exists():
        return None

    try:
        import sqlite3

        conn = sqlite3.connect(str(st_db))
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # Check if tables exist
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {r["name"] for r in cur.fetchall()}

        if "st_records" not in tables:
            conn.close()
            return None

        # Get stumble records
        cur.execute("""
            SELECT id, summary, content, source_ref, workspace, created_at,
                   fingerprint, status, promote_state
            FROM st_records
            WHERE intent = 'STUMBLE'
              AND status NOT IN ('rejected', 'discarded')
            ORDER BY created_at DESC
        """)
        stumbles = [dict(r) for r in cur.fetchall()]

        # Get decisions
        decisions = {}
        if "st_decisions" in tables:
            cur.execute("SELECT fingerprint, decision, note, decided_at, spec_path FROM st_decisions")
            for r in cur.fetchall():
                decisions[r["fingerprint"]] = dict(r)

        conn.close()

        return {"stumbles": stumbles, "decisions": decisions}
    except Exception as e:
        print(f"Warning: failed to read stumble data: {e}", file=sys.stderr)
        return None


def extract_fingerprint_data(stumbles: list[dict[str, Any]], decisions: dict) -> list[dict[str, Any]]:
    """Cluster stumbles by fingerprint and classify."""
    import hashlib

    def make_fingerprint(summary: str) -> str:
        s = summary.lower().strip()
        s = re.sub(r"^(auto:\s*|explicit:\s*)", "", s)
        s = re.sub(r"[\w/.-]+\.\w+", "<file>", s)
        s = re.sub(r"\bgit\s+(push|pull|fetch|clone|checkout|merge|rebase|commit|add|status|diff)\b", r"git-\1", s)
        s = re.sub(r"\b(rejected|failed|error|denied|timeout|refused|not found|missing|broken)\b", "<error>", s)
        stop = {"a", "an", "the", "in", "on", "at", "to", "for", "of", "with", "by", "from", "is", "was", "and", "or", "but"}
        words = [w for w in s.split() if w not in stop]
        words.sort()
        key = " ".join(words)
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

    clusters: dict[str, dict] = {}
    for s in stumbles:
        fp = s.get("fingerprint") or make_fingerprint(s.get("summary", ""))
        if fp not in clusters:
            clusters[fp] = {"rows": [], "source_refs": set(), "workspaces": set()}
        c = clusters[fp]
        c["rows"].append(s)
        c["source_refs"].add(s.get("source_ref", ""))
        c["workspaces"].add(s.get("workspace", ""))

    results = []
    for fp, cluster in clusters.items():
        count = len(cluster["rows"])
        oldest = min(r["created_at"] for r in cluster["rows"])
        newest = max(r["created_at"] for r in cluster["rows"])
        age = age_days(oldest)

        decision_info = decisions.get(fp, {})
        existing_decision = decision_info.get("decision")

        results.append({
            "fingerprint": fp,
            "count": count,
            "frequency_class": classify(count, age),
            "summary": cluster["rows"][0].get("summary", ""),
            "content_preview": (cluster["rows"][0].get("content") or "")[:300],
            "workspaces": sorted(cluster["workspaces"]),
            "source_refs": [r for r in sorted(cluster["source_refs"]) if r],
            "oldest": oldest,
            "newest": newest,
            "age_days": age,
            "decision": existing_decision,
        })

    return results


def is_high_risk(summary: str, content: str) -> bool:
    """Check if a stumble matches a high-risk keyword."""
    combined = f"{summary} {content}".lower()
    for keyword in HIGH_RISK_KEYWORDS:
        if keyword.lower() in combined:
            return True
    return False


def determine_proposal_type(cluster: dict[str, Any]) -> str:
    """Determine the proposal type based on cluster characteristics."""
    fc = cluster["frequency_class"]
    if fc in ("systemic", "repeat"):
        return "hard_rule"
    if is_high_risk(cluster.get("summary", ""), cluster.get("content_preview", "")):
        return "hard_rule"
    return "document_only"


def generate_rule_id(summary: str) -> str:
    """Generate a rule id from a summary."""
    s = summary.lower().strip()
    s = re.sub(r"[^a-z0-9\s]", "", s)
    words = s.split()[:5]
    return "_".join(words) if words else "auto_rule"


def generate_candidate_rule(cluster: dict[str, Any], proposal_type: str) -> dict[str, Any]:
    """Generate a candidate rule entry."""
    summary = cluster.get("summary", "")
    rule_text = f"Avoid: {summary[:120]}"
    rationale = f"Stumble cluster '{cluster['fingerprint']}' recurred {cluster['count']}x in {', '.join(cluster['workspaces'])} workspace(s)"

    severity = "warning"
    enforcement_mode = "doctor-gate"

    if cluster["frequency_class"] == "systemic":
        severity = "blocking"
        enforcement_mode = "command-risk-check" if is_high_risk(summary, cluster.get("content_preview", "")) else "doctor-gate"

    return {
        "rule": rule_text,
        "rationale": rationale,
        "severity": severity,
        "enforcement_mode": enforcement_mode,
        "validator": "none",
    }


def load_existing_proposals() -> dict[str, dict]:
    """Load existing proposals to avoid overwriting approved/rejected ones."""
    proposals: dict[str, dict] = {}
    if PROPOSALS_DIR.exists():
        for pf in PROPOSALS_DIR.glob("*.yaml"):
            try:
                data = yaml.safe_load(pf.read_text())
                if isinstance(data, dict) and data.get("fingerprint"):
                    proposals[data["fingerprint"]] = data
            except yaml.YAMLError:
                continue
    return proposals


def proposal_filename(fp: str, summary: str) -> str:
    """Generate a proposal filename."""
    slug = re.sub(r"[^a-z0-9]+", "-", summary.lower().strip())[:40].strip("-")
    if not slug:
        slug = "unnamed"
    return f"{fp}-{slug}.yaml"


def write_proposal(cluster: dict[str, Any], proposal_type: str, dry_run: bool = False) -> dict[str, Any] | None:
    """Write a proposal file. Returns the proposal data or None if skipped."""
    fp = cluster["fingerprint"]
    now = datetime.now(timezone.utc)

    candidate = generate_candidate_rule(cluster, proposal_type)
    rule_id = generate_rule_id(cluster.get("summary", ""))

    proposal = {
        "fingerprint": fp,
        "created_at": now.isoformat(),
        "workspace": cluster["workspaces"][0] if cluster["workspaces"] else "agent-os",
        "source_refs": cluster["source_refs"],
        "frequency_class": cluster["frequency_class"],
        "count": cluster["count"],
        "decision": "pending",
        "proposal_type": proposal_type,
        "target": {
            "file": "$AGENT_OS_HOME/registry/hard_rules.yaml",
            "rule_id": rule_id,
        },
        "candidate": candidate,
        "review": {
            "status": "pending",
            "reviewer": None,
            "reviewed_at": None,
            "note": None,
        },
    }

    if dry_run:
        return proposal

    PROPOSALS_DIR.mkdir(parents=True, exist_ok=True)
    fname = proposal_filename(fp, cluster.get("summary", ""))
    fpath = PROPOSALS_DIR / fname
    fpath.write_text(yaml.safe_dump(proposal, sort_keys=False, default_flow_style=False))
    return proposal


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Generate stumble rule proposals")
    parser.add_argument("--summary", action="store_true", help="Print summary only (no proposal generation)")
    parser.add_argument("--json", action="store_true", help="JSON output (with --summary)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be created without writing")
    args = parser.parse_args()

    data = get_stumble_data()
    if not data or not data.get("stumbles"):
        if args.json:
            print(json.dumps({"ok": True, "proposals_created": 0, "message": "No stumbles to propose from"}))
        else:
            print("No stumbles to propose from.")
        return 0

    clusters = extract_fingerprint_data(data["stumbles"], data.get("decisions", {}))

    # Selection policy:
    # - Include undecided repeat/systemic clusters
    # - Include first-occurrence only if high-risk
    candidates = []
    for c in clusters:
        if c.get("decision"):
            continue  # already decided
        fc = c["frequency_class"]
        if fc in ("repeat", "systemic"):
            candidates.append(c)
        elif fc == "first-occurrence":
            if is_high_risk(c.get("summary", ""), c.get("content_preview", "")):
                candidates.append(c)
        # skip stale-repeat

    if not candidates:
        if args.json:
            print(json.dumps({"ok": True, "proposals_created": 0, "message": "No undecided clusters need proposals"}))
        else:
            print("No undecided clusters need proposals.")
        return 0

    # Load existing proposals to avoid overwriting
    existing = load_existing_proposals()

    created = []
    for c in candidates:
        fp = c["fingerprint"]
        if fp in existing:
            existing_proposal = existing[fp]
            # Only update if the cluster changed (different count)
            if existing_proposal.get("count") == c["count"] and existing_proposal.get("decision") != "pending":
                continue
            # Never overwrite approved/rejected
            if existing_proposal.get("decision") in ("approved", "rejected", "approved_dry_run"):
                continue

        ptype = determine_proposal_type(c)
        proposal = write_proposal(c, ptype, dry_run=args.dry_run or args.summary)
        if proposal:
            created.append(proposal)

    if args.summary or args.json:
        result = {
            "ok": True,
            "proposals_created": len(created),
            "total_clusters": len(clusters),
            "candidate_clusters": len(candidates),
            "proposals": created if args.json else [
                {
                    "fingerprint": p["fingerprint"],
                    "proposal_type": p["proposal_type"],
                    "frequency_class": p["frequency_class"],
                    "count": p["count"],
                    "summary": p.get("candidate", {}).get("rule", "")[:80],
                }
                for p in created
            ],
        }
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"Proposals: {len(created)} created ({len(candidates)} candidates from {len(clusters)} clusters)")
            for p in created:
                print(f"  [{p['fingerprint']}] {p['proposal_type']} ({p['frequency_class']}, {p['count']}x) -- {p.get('candidate', {}).get('rule', '')[:70]}")
    else:
        if created:
            print(f"Created {len(created)} proposal(s) in {PROPOSALS_DIR}")
            for p in created:
                fname = proposal_filename(p["fingerprint"], p.get("source_refs", [""])[0] if p.get("source_refs") else "")
                print(f"  {fname}")
        else:
            print("No new proposals created.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
