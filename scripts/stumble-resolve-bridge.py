#!/usr/bin/env python3
"""
stumble-resolve-bridge.py — Bridge st_decisions → st_records.status (+ Neo4j valid_until)

For every decision in st_decisions, find st_records where:
  intent='STUMBLE' AND fingerprint matches AND created_at <= decided_at AND status='active'

Then update status:
  decision IN ('document', 'fix', 'guardrail') → status='resolved'
  decision = 'ignore'                           → status='discarded'

When a record is marked resolved, ALSO set valid_until in Neo4j (idempotent)
on the matching graph node — a resolved "broken" fact is no longer valid.
No-op if the Neo4j node does not exist yet. Neo4j failures are logged
but never break the existing SQLite path.

Idempotent: skips records already at target status.

Usage:
  python3 stumble-resolve-bridge.py --dry-run   # Preview changes
  python3 stumble-resolve-bridge.py              # Apply changes
"""

import argparse
import json
import logging
import os
import sqlite3
import sys
import time
from pathlib import Path

# ledger.py lives in agent-os/memory/, not this scripts/ dir — add it to the
# path so the standalone cron invocation (python3 stumble-resolve-bridge.py)
# can import it. Without this the bare `import ledger` raises ModuleNotFoundError.
sys.path.insert(0, os.path.join(os.environ.get("AGENT_OS_HOME", os.path.expanduser("~/agent-os")), "memory"))
import ledger  # noqa: E402

ST_DB = Path.home() / ".local/state/agent-os/memory/short_term.sqlite"

# Decision → target status mapping
DECISION_STATUS = {
    "document": "resolved",
    "fix": "resolved",
    "guardrail": "resolved",
    "ignore": "discarded",
}

# ── Neo4j helpers (inline, same pattern as long_term.py) ──────────────────

ENV_NEO4J_URI = "AGENT_MEMORY_NEO4J_URI"
ENV_NEO4J_USER = "AGENT_MEMORY_NEO4J_USER"
ENV_NEO4J_PASSWORD = "AGENT_MEMORY_NEO4J_PASSWORD"


def _get_neo4j_driver():
    """Return a neo4j driver or None if unavailable."""
    uri = os.environ.get(ENV_NEO4J_URI)
    user = os.environ.get(ENV_NEO4J_USER)
    password = os.environ.get(ENV_NEO4J_PASSWORD)
    if not (uri and user and password):
        return None
    try:
        import neo4j
        return neo4j.GraphDatabase.driver(uri, auth=(user, password),
                                          notifications_min_severity="OFF")
    except ImportError:
        logging.warning("neo4j Python package not installed; skipping graph valid_until")
        return None
    except Exception as exc:
        logging.warning("Neo4j driver init failed: %s", exc)
        return None


def _canonical_iso(ts):
    """Normalize any ISO-8601 timestamp to canonical %Y-%m-%dT%H:%M:%SZ (UTC).

    valid_until is compared lexicographically against _now_iso() in the recall
    Cypher; mixing dialects (microseconds/+00:00 vs trailing Z) breaks that sort.
    Falls back to the raw value if it can't be parsed."""
    from datetime import datetime, timezone
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, TypeError):
        return ts


def _set_neo4j_valid_until(node_id, valid_until_iso):
    """Set valid_until on a Neo4j node by id. No-op if node doesn't exist.
    Never raises (fail-open).

    Pre-reads the prior valid_until for the audit ledger, then appends
    a RETIRED event if the node exists."""
    valid_until_iso = _canonical_iso(valid_until_iso)
    driver = _get_neo4j_driver()
    if driver is None:
        return
    prior_valid_until = None
    try:
        with driver.session() as session:
            # 1. Pre-read prior valid_until for ledger
            pre = session.run(
                "MATCH (n {id: $node_id}) RETURN n.valid_until as prior",
                node_id=node_id,
            )
            pre_row = pre.single()
            if pre_row:
                prior_valid_until = str(pre_row["prior"]) if pre_row["prior"] is not None else None

            # 2. SET valid_until
            result = session.run(
                "MATCH (n {id: $node_id}) "
                "SET n.valid_until = $valid_until, n.updated_at = $now "
                "RETURN n.id as id",
                node_id=node_id,
                valid_until=valid_until_iso,
                now=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            )
            row = result.single()
            if row:
                logging.info("Neo4j valid_until set for node '%s'", node_id)
                # 3. Ledger: log RETIRED
                ledger.append(
                    "RETIRED",
                    node_id,
                    actor="stumble-resolve-bridge",
                    delta={"valid_until": valid_until_iso},
                    prior=prior_valid_until,
                    provenance=f"resolved_stumble st_id:{node_id.replace('promoted_', '')}",
                )
            else:
                logging.debug("No Neo4j node found for id='%s'; skipping valid_until", node_id)
    except Exception as exc:
        logging.warning("Failed to set Neo4j valid_until for node '%s': %s", node_id, exc)
    finally:
        try:
            driver.close()
        except Exception:
            pass


# ── Decision pipeline ─────────────────────────────────────────────────────


def get_decision_rows(conn):
    """Fetch all decisions from st_decisions."""
    return conn.execute(
        "SELECT fingerprint, decision, decided_at FROM st_decisions"
    ).fetchall()


def find_matching_records(conn, fingerprint, decided_at, target_status):
    """Find active ST records matching this fingerprint that predate the decision.

    Returns records that are NOT already at the target status (idempotent).
    """
    rows = conn.execute(
        """SELECT id, status, created_at FROM st_records
           WHERE intent = 'STUMBLE'
             AND fingerprint = ?
             AND created_at <= ?
             AND status != ?
           ORDER BY created_at ASC""",
        (fingerprint, decided_at, target_status),
    ).fetchall()
    return rows


def main():
    parser = argparse.ArgumentParser(description="Bridge st_decisions to st_records.status")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    args = parser.parse_args()

    conn = sqlite3.connect(str(ST_DB))
    conn.row_factory = sqlite3.Row

    decisions = get_decision_rows(conn)

    summary = {
        "ok": True,
        "dry_run": args.dry_run,
        "total_decisions": len(decisions),
        "resolved": 0,
        "discarded": 0,
        "skipped_unknown_decision": 0,
        "skipped_already_at_target": 0,
        "details": [],
    }

    for d in decisions:
        fp = d["fingerprint"]
        decision = d["decision"]
        decided_at = d["decided_at"]

        target_status = DECISION_STATUS.get(decision)
        if target_status is None:
            summary["skipped_unknown_decision"] += 1
            continue

        records = find_matching_records(conn, fp, decided_at, target_status)

        for r in records:
            if r["status"] == target_status:
                summary["skipped_already_at_target"] += 1
                continue

            summary["details"].append({
                "id": r["id"],
                "fingerprint": fp,
                "decision": decision,
                "old_status": r["status"],
                "new_status": target_status,
                "created_at": r["created_at"],
            })

            if target_status == "resolved":
                summary["resolved"] += 1
            elif target_status == "discarded":
                summary["discarded"] += 1

            if not args.dry_run:
                conn.execute(
                    "UPDATE st_records SET status = ? WHERE id = ?",
                    (target_status, r["id"]),
                )
                # When marking a stumble resolved, also set valid_until in Neo4j
                # so the fact is no longer recalled as current.  No-op if the
                # Neo4j node hasn't been created yet (may be promoted later).
                if target_status == "resolved":
                    graph_id = f"promoted_{r['id']}"
                    _set_neo4j_valid_until(graph_id, d["decided_at"])

    if not args.dry_run:
        conn.commit()

    conn.close()

    # Summary line
    total_changes = summary["resolved"] + summary["discarded"]
    summary["total_changes"] = total_changes

    print(json.dumps(summary, indent=2))
    sys.exit(0)


if __name__ == "__main__":
    main()
