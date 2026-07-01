#!/usr/bin/env python3
"""
ledger.py — Append-only audit ledger for Neo4j memory graph mutations.

Every CLAIM_ADDED / INVALIDATED / RETIRED event is recorded immutably,
recoverably, and idempotently.  The ledger is a standalone SQLite store
that tolerates the graph being down or the DB being unwritable.

Schema
------
ledger_events(
    event_id    TEXT PRIMARY KEY,  -- deterministic SHA-256[:32]
    ts          TEXT NOT NULL,     -- canonical ISO-8601 UTC
    event_type  TEXT NOT NULL,     -- CLAIM_ADDED | INVALIDATED | RETIRED
    claim_id    TEXT NOT NULL,     -- Neo4j node id
    actor       TEXT,              -- script / agent name
    prior_json  TEXT,              -- prior state before mutation (JSON, may be null)
    delta_json  TEXT NOT NULL,     -- what changed (JSON)
    provenance  TEXT               -- optional context (free-text)
)

event_id is deterministic for idempotency: re-emitting the exact same event
(INSERT OR IGNORE) is a safe no-op.

Fail-open: every public function catches all exceptions, logs a warning,
and returns None / empty.  A ledger error NEVER breaks the primary mutation.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import time

logger = logging.getLogger(__name__)

ENV_LEDGER_DB = "AGENT_OS_LEDGER_DB"
DEFAULT_DB = os.path.join(
    os.path.expanduser("~"),
    ".local/state/agent-os/memory/audit_ledger.sqlite",
)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS ledger_events (
    event_id    TEXT PRIMARY KEY,
    ts          TEXT NOT NULL,
    event_type  TEXT NOT NULL,
    claim_id    TEXT NOT NULL,
    actor       TEXT,
    prior_json  TEXT,
    delta_json  TEXT NOT NULL,
    provenance  TEXT
);
"""

IDX_EVENT_TYPE = """
CREATE INDEX IF NOT EXISTS idx_ledger_et
    ON ledger_events(event_type);
"""
IDX_CLAIM_ID = """
CREATE INDEX IF NOT EXISTS idx_ledger_claim
    ON ledger_events(claim_id);
"""
IDX_TS = """
CREATE INDEX IF NOT EXISTS idx_ledger_ts
    ON ledger_events(ts);
"""

WAL_PRAGMAS = [
    "PRAGMA journal_mode=WAL",
    "PRAGMA synchronous=NORMAL",
]


# ── Helpers ──────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _ledger_db_path() -> str:
    """Return ledger DB path from env or default."""
    return os.environ.get(ENV_LEDGER_DB, DEFAULT_DB)


def _ensure_dir(path: str) -> bool:
    """Ensure parent directory exists. Returns True if ok."""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        return True
    except OSError as exc:
        logger.warning("ledger: cannot create dir for %s: %s", path, exc)
        return False


def _open_ledger(db_path: str) -> sqlite3.Connection | None:
    """Open ledger DB with WAL + schema. Returns conn or None."""
    try:
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute(SCHEMA_SQL)
        conn.execute(IDX_EVENT_TYPE)
        conn.execute(IDX_CLAIM_ID)
        conn.execute(IDX_TS)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as exc:
        logger.warning("ledger: cannot open %s: %s", db_path, exc)
        return None


def _event_id(event_type: str, claim_id: str, delta_json: str) -> str:
    """Deterministic event ID — sha256 of the STABLE logical fields only.

    Event-time (ts) is deliberately excluded: the same logical mutation
    re-emitted later (e.g. the daily resolve-bridge re-touching an already
    resolved stumble) must collapse to the same id so INSERT OR IGNORE is a
    true no-op, instead of accumulating a duplicate row every run. A mutation
    to a *different* delta (e.g. a new valid_until) yields a different id and
    is recorded. The ts column still stores first-write event-time."""
    raw = f"{event_type}|{claim_id}|{delta_json}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _canonical_iso(ts: str) -> str:
    """Normalize any ISO-8601 to %Y-%m-%dT%H:%M:%SZ."""
    from datetime import datetime, timezone
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, TypeError):
        return ts


# ── Public API ────────────────────────────────────────────────────────────

def append(
    event_type: str,
    claim_id: str,
    actor: str | None = None,
    delta: dict | None = None,
    prior: str | None = None,
    provenance: str | None = None,
) -> str | None:
    """Append one event to the ledger.  Fail-open: returns event_id or None.

    Parameters
    ----------
    event_type : str
        One of CLAIM_ADDED, INVALIDATED, RETIRED.
    claim_id : str
        Neo4j node id this event affects.
    actor : str or None
        Script or agent name that caused the mutation.
    delta : dict or None
        The new/changed state (e.g. {"valid_from": "...",
        "valid_until": "..."}).  Serialised as delta_json.
    prior : str or None
        JSON string of the prior state before this mutation.
        For CLAIM_ADDED this is always None.
    provenance : str or None
        Optional free-text context (e.g. CLI args, reason).

    Returns event_id on success, None on any error.
    """
    ts = _now_iso()
    delta_json = json.dumps(delta or {}, sort_keys=True)
    eid = _event_id(event_type, claim_id, delta_json)

    db_path = _ledger_db_path()
    if not _ensure_dir(db_path):
        return None

    conn = _open_ledger(db_path)
    if conn is None:
        return None

    try:
        conn.execute(
            """INSERT OR IGNORE INTO ledger_events
               (event_id, ts, event_type, claim_id, actor, prior_json, delta_json, provenance)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (eid, ts, event_type, claim_id, actor, prior, delta_json, provenance),
        )
        conn.commit()
        return eid
    except sqlite3.Error as exc:
        logger.warning("ledger.append failed: %s", exc)
        return None
    finally:
        try:
            conn.close()
        except Exception:
            pass


def query(
    claim_id: str | None = None,
    event_type: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """Return matching ledger events, newest-first.

    Every row includes all columns.  Never raises.
    """
    db_path = _ledger_db_path()
    if not os.path.isfile(db_path):
        return []
    conn = _open_ledger(db_path)
    if conn is None:
        return []
    try:
        parts = ["SELECT * FROM ledger_events WHERE 1=1"]
        params = []
        if claim_id:
            parts.append("AND claim_id = ?")
            params.append(claim_id)
        if event_type:
            parts.append("AND event_type = ?")
            params.append(event_type)
        parts.append("ORDER BY ts DESC LIMIT ?")
        params.append(limit)
        rows = conn.execute(" ".join(parts), params).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.Error:
        return []
    finally:
        try:
            conn.close()
        except Exception:
            pass


def audit() -> dict:
    """Compare ledger state against live Neo4j.

    Returns dict with:
      - divergence: list of dicts with claim_id, issue (str), graph_*
        and ledger_* fields, or [] for clean.
      - result_count: int.

    Never raises — returns {"divergence": [{"error": "..."}]} on error.
    """
    db_path = _ledger_db_path()
    if not os.path.isfile(db_path):
        return {"divergence": [], "result_count": 0, "note": "no ledger DB"}

    conn = _open_ledger(db_path)
    if conn is None:
        return {"divergence": [], "result_count": 0, "note": "cannot open ledger"}

    try:
        # 1. Latest event per claim_id
        latest = conn.execute(
            """SELECT claim_id, event_type, ts, delta_json, prior_json
               FROM ledger_events
               WHERE rowid IN (
                   SELECT MAX(rowid) FROM ledger_events GROUP BY claim_id
               )
               ORDER BY ts DESC"""
        ).fetchall()
    except sqlite3.Error as exc:
        return {"divergence": [{"error": str(exc)}], "result_count": 1}
    finally:
        try:
            conn.close()
        except Exception:
            pass

    # 2. Read live graph state — import here to keep ledger.py importable
    #    without neo4j when the ledger is used solely for append/query.
    try:
        from long_term import _get_driver as _graph_driver
    except ImportError:
        try:
            from agent_os.memory.long_term import _get_driver as _graph_driver
        except ImportError:
            return {
                "divergence": [{"error": "cannot import long_term._get_driver"}],
                "result_count": 1,
            }

    divergence = []
    for row in latest:
        claim_id = row["claim_id"]
        ledger_event_type = row["event_type"]
        ledger_delta = json.loads(row["delta_json"]) if row["delta_json"] else {}

        # Read live graph node
        try:
            driver = _graph_driver()
            if driver is None:
                divergence.append({
                    "claim_id": claim_id,
                    "issue": "graph_unavailable",
                    "ledger_event_type": ledger_event_type,
                    "ledger_delta": ledger_delta,
                })
                continue
            with driver.session() as session:
                result = session.run(
                    "MATCH (n {id: $claim_id}) "
                    "RETURN n.valid_until as valid_until, n.valid_from as valid_from, "
                    "       n.invalidation_reason as reason, labels(n) as labels",
                    claim_id=claim_id,
                )
                node = result.single()
            driver.close()
        except Exception as exc:
            divergence.append({
                "claim_id": claim_id,
                "issue": f"graph_read_error: {exc}",
                "ledger_event_type": ledger_event_type,
                "ledger_delta": ledger_delta,
            })
            continue

        if node is None:
            divergence.append({
                "claim_id": claim_id,
                "issue": "graph_node_not_found",
                "ledger_event_type": ledger_event_type,
                "ledger_delta": ledger_delta,
            })
            continue

        # Compare ledger delta against graph
        graph_valid_until = str(node["valid_until"]) if node["valid_until"] is not None else None
        if ledger_event_type == "CLAIM_ADDED":
            ledger_valid_from = ledger_delta.get("valid_from")
            # Graph should have this node. If it has valid_until set, that's
            # expected (may have been invalidated later). Core check: node exists.
            if node["labels"] and len(node["labels"]) > 0:
                pass  # node exists — fine
            else:
                divergence.append({
                    "claim_id": claim_id,
                    "issue": "graph_node_has_no_labels",
                    "graph_valid_until": graph_valid_until,
                    "ledger_event_type": ledger_event_type,
                })
        elif ledger_event_type in ("INVALIDATED", "RETIRED"):
            ledger_valid_until = ledger_delta.get("valid_until")
            if ledger_valid_until and graph_valid_until:
                # Canonicalize both for comparison
                lvu = _canonical_iso(ledger_valid_until)
                gvu = _canonical_iso(graph_valid_until)
                if lvu != gvu:
                    divergence.append({
                        "claim_id": claim_id,
                        "issue": "valid_until_mismatch",
                        "graph_valid_until": graph_valid_until,
                        "ledger_valid_until": ledger_valid_until,
                    })
            elif ledger_valid_until and not graph_valid_until:
                divergence.append({
                    "claim_id": claim_id,
                    "issue": "graph_valid_until_missing",
                    "ledger_valid_until": ledger_valid_until,
                })

    return {"divergence": divergence, "result_count": len(divergence)}


def history_for(claim_id: str) -> list[dict]:
    """Return all events for a claim, oldest-first.  Never raises."""
    db_path = _ledger_db_path()
    if not os.path.isfile(db_path):
        return []
    conn = _open_ledger(db_path)
    if conn is None:
        return []
    try:
        rows = conn.execute(
            "SELECT * FROM ledger_events WHERE claim_id = ? ORDER BY ts ASC, rowid ASC",
            (claim_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.Error:
        return []
    finally:
        try:
            conn.close()
        except Exception:
            pass


def latest_for(claim_id: str) -> dict | None:
    """Return the most recent event for a claim, or None.  Never raises."""
    db_path = _ledger_db_path()
    if not os.path.isfile(db_path):
        return None
    conn = _open_ledger(db_path)
    if conn is None:
        return None
    try:
        row = conn.execute(
            "SELECT * FROM ledger_events WHERE claim_id = ? ORDER BY ts DESC, rowid DESC LIMIT 1",
            (claim_id,),
        ).fetchone()
        return dict(row) if row else None
    except sqlite3.Error:
        return None
    finally:
        try:
            conn.close()
        except Exception:
            pass
