#!/usr/bin/python3
"""
short_term.py — Short-term memory backend for agent OS (P9 WP1)

CLI interface for $AGENT_OS_HOME/bin/memory-st.
Uses only Python standard library. SQLite with FTS5 for search.

Allowed write paths:
  - $AGENT_OS_HOME/.local/state/agent-os/memory/short_term.sqlite (runtime DB)

Commands:
  init, write, query, get, update-status, mark-candidate,
  set-promote-state, add-tag, get-by-fingerprint,
  unresolved-help, packet-context
"""

import argparse
import json
import os
import re
import sqlite3
import string
import sys
import time
import random
import uuid

_AOH = os.environ.get("AGENT_OS_HOME") or os.path.dirname(os.path.abspath(__file__))


# ── Constants ──────────────────────────────────────────────────────────────

# Runtime DB path. Overridable via AGENT_OS_ST_DB so tests (and isolated
# tooling) can point at a throwaway database without touching the live WAL.
# Default is unchanged for all normal callers.
DB_PATH = os.path.expanduser(
    os.environ.get(
        "AGENT_OS_ST_DB",
        f"{os.environ.get('HOME', os.path.expanduser('~'))}/.local/state/agent-os/memory/short_term.sqlite",
    )
)
SCHEMA_PATH = os.path.expanduser(
    f"{_AOH}/memory/core/schema_short_term.sql"
)
NOW_MD_PATH = f"{_AOH}/NOW.md (ARCHIVED 2026-05-31 — archive at agent-os-docs/archive/2026-05/doc-governance/NOW.md)"

ALLOWED_KINDS = {
    "packet_summary", "status", "observation", "stumble",
    "confirmed", "help_request", "help_resolution", "verification", "state",
}

ALLOWED_INTENTS = {
    "OBSERVATION", "LESSON", "DECISION", "STUMBLE", "CONFIRMED",
    "OPS", "HELP", "VERIFICATION", "STATE", "LEARNING", "IMPLEMENT",
    "BUG", "SPEC", "DOCS", "RESEARCH",
}

ALLOWED_STATUSES = {"active", "resolved", "superseded", "discarded"}

ALLOWED_PROMOTE_STATES = {
    "none", "candidate", "promoted", "rejected", "proposed", "approved",
}

SEED_RECORD_ID = "st_seed_now"


# ── Database Helpers ──────────────────────────────────────────────────────

def get_conn():
    """Return a SQLite connection with WAL mode, foreign keys, and a busy
    timeout so concurrent writers don't raise SQLITE_BUSY mid-transaction."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA busy_timeout = 30000;")
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn):
    """Create tables from schema file."""
    schema = open(SCHEMA_PATH).read()
    conn.executescript(schema)
    conn.commit()


def delete_record(record_id: str) -> int:
    """Delete a record and ALL of its dependent rows in one transaction.

    Shadow tables and their cascade behavior:
      - st_tags: FK ON DELETE CASCADE -> removed automatically.
      - st_semantic_cluster_members: FK ON DELETE CASCADE -> automatic.
      - st_records_fts: content-storing FTS5, NOT FK-linked -> delete explicitly.
      - memory_proposals / memory_diffs: NO ON DELETE CASCADE -> delete explicitly.

    Returns the number of base rows deleted (0 if id did not exist).
    """
    conn = get_conn()
    try:
        conn.execute(
            "DELETE FROM st_records_fts WHERE id = ?", (record_id,)
        )
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name='st_semantic_cluster_members'"
        )
        if cur.fetchone():
            conn.execute(
                "DELETE FROM st_semantic_cluster_members WHERE st_record_id = ?",
                (record_id,),
            )
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name IN ('memory_proposals','memory_diffs')"
        )
        have_tables = {r[0] for r in cur.fetchall()}
        if "memory_proposals" in have_tables:
            if "memory_diffs" in have_tables:
                conn.execute(
                    "DELETE FROM memory_diffs WHERE proposal_id IN "
                    "(SELECT proposal_id FROM memory_proposals "
                    "WHERE st_record_id = ?)",
                    (record_id,),
                )
            conn.execute(
                "DELETE FROM memory_proposals WHERE st_record_id = ?",
                (record_id,),
            )
        cur = conn.execute("DELETE FROM st_records WHERE id = ?", (record_id,))
        deleted = cur.rowcount
        conn.commit()
        return deleted
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def sync_fts_to_base(conn) -> int:
    """Remove orphaned shadow rows whose parent record no longer exists.

    Reconciles st_records_fts, st_tags, and memory_proposals. Returns the
    number of orphaned rows removed. Idempotent.
    """
    cur = conn.cursor()
    before = conn.total_changes
    cur.execute(
        "DELETE FROM st_records_fts WHERE id NOT IN (SELECT id FROM st_records)"
    )
    cur.execute(
        "DELETE FROM st_tags WHERE record_id NOT IN (SELECT id FROM st_records)"
    )
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name IN ('memory_proposals','memory_diffs')"
    )
    have_tables = {r[0] for r in cur.fetchall()}
    if "memory_proposals" in have_tables:
        if "memory_diffs" in have_tables:
            cur.execute(
                "DELETE FROM memory_diffs WHERE proposal_id IN "
                "(SELECT p.proposal_id FROM memory_proposals p "
                "WHERE p.st_record_id NOT IN (SELECT id FROM st_records))"
            )
        cur.execute(
            "DELETE FROM memory_proposals WHERE st_record_id "
            "NOT IN (SELECT id FROM st_records)"
        )
    conn.commit()
    return conn.total_changes - before


def generate_id():
    """Generate a unique short-term memory record ID."""
    ts = time.strftime("%Y%m%d")
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"st_{ts}_{suffix}"


def now_iso():
    """Return current UTC timestamp in ISO format."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def sanitize_fts5(query):
    """
    Strip FTS5 special operators from user query and wrap in double quotes
    token string for relevance-ranked search.
    """
    # Remove FTS5 special operators: ^ * " ( ) + - and keywords NOT, AND, OR, NEAR
    cleaned = re.sub(
        r'[\^"()+\-*]|\b(?:NOT|AND|OR|NEAR)\b',
        " ",
        query,
        flags=re.IGNORECASE,
    )
    # Collapse whitespace
    tokens = cleaned.split()
    if not tokens:
        return '""'
    return " AND ".join(tokens)


def record_to_dict(row):
    """Convert a sqlite3.Row to a plain dict."""
    return dict(row)


# ── Seed Logic ────────────────────────────────────────────────────────────

def seed_now_state(conn):
    """
    Seed one `state` record from NOW.md if not already seeded.
    Uses fixed id='st_seed_now' so it only runs once.
    """
    existing = conn.execute(
        "SELECT id FROM st_records WHERE id = ?", (SEED_RECORD_ID,)
    ).fetchone()
    if existing:
        return  # already seeded

    summary = "Active plan (NOW.md scratchpad archived 2026-05-31; seed record preserved)"
    content = (
        "Active plan: "
        f"{_AOH}/docs/AGENTIC_COCKPIT_MASTER_PLAN.md"
    )
    now = now_iso()

    conn.execute(
        """INSERT INTO st_records
           (id, run_id, message_id, agent_id, workspace, intent, kind,
            content, summary, source_ref, status, promote_state,
            fingerprint, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            SEED_RECORD_ID,
            "seed_init",
            None,
            "system",
            "home",
            "OPS",
            "state",
            content,
            summary,
            NOW_MD_PATH,
            "active",
            "none",
            None,
            now,
            now,
        ),
    )

    # Also seed into FTS
    conn.execute(
        "INSERT INTO st_records_fts(id, content, summary) VALUES (?, ?, ?)",
        (SEED_RECORD_ID, content, summary),
    )

    conn.commit()


# ── Command Handlers ──────────────────────────────────────────────────────

def cmd_init(args):
    """Initialize the SQLite database and seed state (NOW.md content archived 2026-05-31)."""
    conn = get_conn()
    try:
        init_db(conn)
        seed_now_state(conn)
        print(json.dumps({"ok": True, "action": "init", "db": DB_PATH}))
    finally:
        conn.close()


def cmd_write(args):
    """Write a short-term memory record."""
    # Validate kind
    if args.kind not in ALLOWED_KINDS:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": f"Invalid kind '{args.kind}'. "
                    f"Allowed: {', '.join(sorted(ALLOWED_KINDS))}",
                }
            )
        )
        sys.exit(1)

    # Validate intent
    if args.intent not in ALLOWED_INTENTS:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": f"Invalid intent '{args.intent}'. "
                    f"Allowed: {', '.join(sorted(ALLOWED_INTENTS))}",
                }
            )
        )
        sys.exit(1)

    # Boundary tier enforcement: brain-tier writes require evidence
    if args.boundary_kind == "brain" and not args.evidence_ref and not args.justify_no_evidence:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "brain-tier write requires --evidence-ref or --justify-no-evidence",
                }
            ),
            file=sys.stderr,
        )
        sys.exit(1)

    # Read content from file
    try:
        with open(args.content_file, "r") as f:
            content = f.read()
    except FileNotFoundError:
        print(
            json.dumps(
                {"ok": False, "error": f"Content file not found: {args.content_file}"}
            )
        )
        sys.exit(1)
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"Error reading file: {e}"}))
        sys.exit(1)

    record_id = generate_id()
    now = now_iso()

    conn = get_conn()
    try:
        # Idempotent migration: ensure boundary_kind column exists.
        cols = [r[1] for r in conn.execute("PRAGMA table_info(st_records)").fetchall()]
        if "boundary_kind" not in cols:
            conn.execute("ALTER TABLE st_records ADD COLUMN boundary_kind TEXT")
            conn.commit()

        conn.execute(
            """INSERT INTO st_records
               (id, run_id, message_id, agent_id, workspace, intent, kind,
                content, summary, source_ref, status, promote_state,
                fingerprint, created_at, updated_at, boundary_kind)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record_id,
                args.run_id,
                None,
                args.agent_id,
                args.workspace,
                args.intent,
                args.kind,
                content,
                args.summary,
                args.source_ref,
                "active",
                "none",
                args.fingerprint,
                now,
                now,
                args.boundary_kind,
            ),
        )

        # Insert into FTS5 index
        conn.execute(
            "INSERT INTO st_records_fts(id, content, summary) VALUES (?, ?, ?)",
            (record_id, content, args.summary),
        )

        # Insert tags if provided
        if args.tag:
            for tag in args.tag:
                conn.execute(
                    "INSERT OR IGNORE INTO st_tags(record_id, tag) VALUES (?, ?)",
                    (record_id, tag),
                )

        # Persist boundary evidence as tags
        for ref in args.evidence_ref:
            conn.execute(
                "INSERT OR IGNORE INTO st_tags(record_id, tag) VALUES (?, ?)",
                (record_id, f"evidence_ref:{ref}"),
            )
        if args.justify_no_evidence:
            conn.execute(
                "INSERT OR IGNORE INTO st_tags(record_id, tag) VALUES (?, ?)",
                (record_id, f"justify_no_evidence:{args.justify_no_evidence}"),
            )

        # If kind is help_request, also create entry in st_help_requests
        if args.kind == "help_request":
            conn.execute(
                """INSERT OR IGNORE INTO st_help_requests
                   (id, run_id, message_id, parent_agent, requesting_agent,
                    workspace, uncertainty_type, question, recommended_default,
                    status, resolution_record_id, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record_id,
                    args.run_id,
                    "",
                    "",
                    args.agent_id,
                    args.workspace,
                    "",
                    args.summary,
                    "",
                    "active",
                    None,
                    now,
                    now,
                ),
            )

        conn.commit()

        result = {
            "ok": True,
            "id": record_id,
            "promote_state": "none",
            "boundary_kind": args.boundary_kind,
        }
        print(json.dumps(result))

    except Exception as e:
        conn.rollback()
        print(json.dumps({"ok": False, "error": str(e)}))
        sys.exit(1)
    finally:
        conn.close()


def cmd_query(args):
    """Search short-term memory records by FTS5 query."""
    conn = get_conn()
    try:
        safe_query = sanitize_fts5(args.text)
        conditions = []
        params = []

        # FTS5 MATCH
        conditions.append("fts.id = r.id")
        conditions.append("st_records_fts MATCH ?")
        params.append(safe_query)

        # Optional filters
        if args.workspace and args.workspace != "any":
            conditions.append("r.workspace = ?")
            params.append(args.workspace)
        if args.intent and args.intent != "any":
            conditions.append("r.intent = ?")
            params.append(args.intent)
        if args.kind:
            conditions.append("r.kind = ?")
            params.append(args.kind)

        where_clause = " AND ".join(conditions)

        sql = f"""
            SELECT r.id, r.workspace, r.intent, r.kind, r.summary,
                   r.source_ref, r.status, r.promote_state, r.created_at,
                   r.run_id, r.agent_id, r.fingerprint,
                   rank as score
            FROM st_records_fts fts
            JOIN st_records r ON fts.id = r.id
            WHERE {where_clause}
            ORDER BY rank
            LIMIT ?
        """
        params.append(args.limit)

        rows = conn.execute(sql, params).fetchall()

        results = []
        for row in rows:
            d = record_to_dict(row)
            # Keep score as a float rounded to 2 decimal places
            d["score"] = round(d.get("score", 0), 2)
            results.append(d)

        print(json.dumps({"ok": True, "results": results}))

    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        sys.exit(1)
    finally:
        conn.close()


def cmd_get(args):
    """Get a single record by ID."""
    conn = get_conn()
    try:
        row = conn.execute(
            """SELECT r.*, GROUP_CONCAT(t.tag, ',') as tags_str
               FROM st_records r
               LEFT JOIN st_tags t ON t.record_id = r.id
               WHERE r.id = ?
               GROUP BY r.id""",
            (args.id,),
        ).fetchone()

        if not row:
            print(json.dumps({"ok": False, "error": f"Record not found: {args.id}"}))
            sys.exit(1)

        d = record_to_dict(row)
        # Split tags string into list
        tags = d.pop("tags_str", None)
        d["tags"] = tags.split(",") if tags else []

        # Also get help request data if applicable
        if d.get("kind") == "help_request":
            hr = conn.execute(
                "SELECT * FROM st_help_requests WHERE id = ?",
                (args.id,),
            ).fetchone()
            if hr:
                d["help_request"] = record_to_dict(hr)

        print(json.dumps({"ok": True, "record": d}))

    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        sys.exit(1)
    finally:
        conn.close()


def cmd_update_status(args):
    """Update the status of a record."""
    if args.status not in ALLOWED_STATUSES:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": f"Invalid status '{args.status}'. "
                    f"Allowed: {', '.join(sorted(ALLOWED_STATUSES))}",
                }
            )
        )
        sys.exit(1)

    conn = get_conn()
    try:
        # Check record exists
        row = conn.execute(
            "SELECT id, kind, status FROM st_records WHERE id = ?", (args.id,)
        ).fetchone()
        if not row:
            print(json.dumps({"ok": False, "error": f"Record not found: {args.id}"}))
            sys.exit(1)

        now = now_iso()
        conn.execute(
            "UPDATE st_records SET status = ?, updated_at = ? WHERE id = ?",
            (args.status, now, args.id),
        )

        # If this is a help_request and status is resolved, update st_help_requests too
        if row["kind"] == "help_request" and args.status == "resolved":
            conn.execute(
                "UPDATE st_help_requests SET status = ?, updated_at = ? WHERE id = ?",
                ("resolved", now, args.id),
            )

        conn.commit()
        print(json.dumps({"ok": True, "id": args.id, "status": args.status}))

    except Exception as e:
        conn.rollback()
        print(json.dumps({"ok": False, "error": str(e)}))
        sys.exit(1)
    finally:
        conn.close()


def cmd_mark_candidate(args):
    """
    Mark a record as promotion candidate.
    Sets promote_state to 'candidate' and preserves the reason as a tag.
    """
    conn = get_conn()
    try:
        # Check record exists
        row = conn.execute(
            "SELECT id, promote_state FROM st_records WHERE id = ?", (args.id,)
        ).fetchone()
        if not row:
            print(json.dumps({"ok": False, "error": f"Record not found: {args.id}"}))
            sys.exit(1)

        now = now_iso()
        conn.execute(
            "UPDATE st_records SET promote_state = ?, updated_at = ? WHERE id = ?",
            ("candidate", now, args.id),
        )

        # Preserve reason as a tag (schema-preserving approach)
        conn.execute(
            "INSERT OR IGNORE INTO st_tags(record_id, tag) VALUES (?, ?)",
            (args.id, f"promote_reason:{args.reason}"),
        )

        conn.commit()
        print(json.dumps({"ok": True, "id": args.id, "promote_state": "candidate"}))

    except Exception as e:
        conn.rollback()
        print(json.dumps({"ok": False, "error": str(e)}))
        sys.exit(1)
    finally:
        conn.close()


def cmd_set_promote_state(args):
    """
    Set promote_state for a record (promoted/rejected/proposed/approved).
    This is the supported interface — agents must not write SQLite directly.
    """
    # Validate state — promoted/rejected/proposed/approved through this command
    if args.state not in {"promoted", "rejected", "proposed", "approved"}:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": f"Invalid state '{args.state}'. "
                    f"Allowed: promoted, rejected. "
                    f"(Use 'mark-candidate' for 'candidate' state.)",
                }
            )
        )
        sys.exit(1)

    conn = get_conn()
    try:
        # Check record exists
        row = conn.execute(
            "SELECT id, promote_state FROM st_records WHERE id = ?", (args.id,)
        ).fetchone()
        if not row:
            print(json.dumps({"ok": False, "error": f"Record not found: {args.id}"}))
            sys.exit(1)

        now = now_iso()
        # Stamp promoted_at when transitioning to 'promoted'; clear on 'rejected'.
        if args.state == "promoted":
            conn.execute(
                "UPDATE st_records SET promote_state = ?, updated_at = ?, "
                "promoted_at = ? WHERE id = ?",
                (args.state, now, now, args.id),
            )
        else:
            conn.execute(
                "UPDATE st_records SET promote_state = ?, updated_at = ? WHERE id = ?",
                (args.state, now, args.id),
            )

        # Preserve reason as a tag (schema-preserving approach)
        if args.reason:
            conn.execute(
                "INSERT OR IGNORE INTO st_tags(record_id, tag) VALUES (?, ?)",
                (args.id, f"promote_reason:{args.reason}"),
            )

        conn.commit()
        result_payload = {
            "ok": True,
            "id": args.id,
            "promote_state": args.state,
        }
        if args.state == "promoted":
            result_payload["promoted_at"] = now
        print(json.dumps(result_payload))

    except Exception as e:
        conn.rollback()
        print(json.dumps({"ok": False, "error": str(e)}))
        sys.exit(1)
    finally:
        conn.close()


def cmd_get_by_fingerprint(args):
    """
    Look up a record by its fingerprint hash.
    Returns {ok, found, record: {id, promote_state}} or {ok, found: false}.
    """
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT id, promote_state FROM st_records WHERE fingerprint = ?",
            (args.fingerprint,),
        ).fetchone()
        if row:
            print(
                json.dumps(
                    {
                        "ok": True,
                        "found": True,
                        "record": {"id": row["id"], "promote_state": row["promote_state"]},
                    }
                )
            )
        else:
            print(json.dumps({"ok": True, "found": False}))
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        sys.exit(1)
    finally:
        conn.close()


def cmd_add_tag(args):
    """Attach a tag to an existing record via the supported memory-st interface."""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT id FROM st_records WHERE id = ?",
            (args.id,),
        ).fetchone()
        if not row:
            print(json.dumps({"ok": False, "error": f"Record not found: {args.id}"}))
            sys.exit(1)

        conn.execute(
            "INSERT OR IGNORE INTO st_tags(record_id, tag) VALUES (?, ?)",
            (args.id, args.tag),
        )
        conn.execute(
            "UPDATE st_records SET updated_at = ? WHERE id = ?",
            (now_iso(), args.id),
        )
        conn.commit()
        print(json.dumps({"ok": True, "id": args.id, "tag": args.tag}))
    except Exception as e:
        conn.rollback()
        print(json.dumps({"ok": False, "error": str(e)}))
        sys.exit(1)
    finally:
        conn.close()


def cmd_unresolved_help(args):
    """Return unresolved HELP requests, optionally filtered by workspace."""
    conn = get_conn()
    try:
        if args.workspace and args.workspace != "any":
            rows = conn.execute(
                """SELECT hr.*, r.summary, r.source_ref, r.kind
                   FROM st_help_requests hr
                   LEFT JOIN st_records r ON r.id = hr.id
                   WHERE hr.status = 'active' AND hr.workspace = ?
                   ORDER BY hr.created_at DESC""",
                (args.workspace,),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT hr.*, r.summary, r.source_ref, r.kind
                   FROM st_help_requests hr
                   LEFT JOIN st_records r ON r.id = hr.id
                   WHERE hr.status = 'active'
                   ORDER BY hr.created_at DESC""",
            ).fetchall()

        results = [record_to_dict(row) for row in rows]
        print(json.dumps({"ok": True, "results": results}))

    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        sys.exit(1)
    finally:
        conn.close()


def cmd_packet_context(args):
    """
    Return packet context for a given run ID.
    Returns empty context if no records exist, but always valid JSON.
    """
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM st_packet_context WHERE packet_run_id = ?",
            (args.run_id,),
        ).fetchone()

        if row:
            d = record_to_dict(row)
            d["context_json"] = json.loads(d["context_json"])
            print(json.dumps({"ok": True, "packet_context": d}))
        else:
            print(
                json.dumps(
                    {
                        "ok": True,
                        "packet_context": {
                            "packet_run_id": args.run_id,
                            "workspace": "",
                            "intent": "",
                            "query": "",
                            "context_json": {},
                            "token_budget": 0,
                            "created_at": "",
                        },
                    }
                )
            )

    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        sys.exit(1)
    finally:
        conn.close()


# ── Argument Parser ───────────────────────────────────────────────────────

def cmd_set_decision(args):
    """Record a stumble triage decision (fix|guardrail|document|ignore)."""
    conn = get_conn()
    try:
        now = now_iso()
        conn.execute(
            """INSERT INTO st_decisions (fingerprint, decision, note, decided_at, decided_by, spec_path)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(fingerprint) DO UPDATE SET
                 decision = excluded.decision,
                 note = excluded.note,
                 decided_at = excluded.decided_at,
                 decided_by = excluded.decided_by,
                 spec_path = excluded.spec_path""",
            (args.fingerprint, args.decision, args.note, now, args.decided_by, args.spec_path),
        )
        conn.commit()
        print(json.dumps({"ok": True, "fingerprint": args.fingerprint, "decision": args.decision}))
    except Exception as e:
        conn.rollback()
        print(json.dumps({"ok": False, "error": str(e)}))
        sys.exit(1)
    finally:
        conn.close()


def cmd_get_decisions(args):
    """List all stumble triage decisions."""
    conn = get_conn()
    try:
        if args.decision:
            rows = conn.execute(
                "SELECT * FROM st_decisions WHERE decision = ? ORDER BY decided_at DESC",
                (args.decision,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM st_decisions ORDER BY decided_at DESC"
            ).fetchall()
        results = [dict(r) for r in rows]
        print(json.dumps({"ok": True, "count": len(results), "decisions": results}))
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        sys.exit(1)
    finally:
        conn.close()


def cmd_get_decision(args):
    """Get a decision by fingerprint."""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM st_decisions WHERE fingerprint = ?",
            (args.fingerprint,),
        ).fetchone()
        if row:
            print(json.dumps({"ok": True, "decision": dict(row)}))
        else:
            print(json.dumps({"ok": True, "found": False}))
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        sys.exit(1)
    finally:
        conn.close()


def cmd_delete(args):
    """Delete a record via delete_record() so dependent rows stay consistent."""
    try:
        deleted = delete_record(args.id)
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        sys.exit(1)
    print(json.dumps({"ok": True, "id": args.id, "deleted": deleted}))


def build_parser():
    parser = argparse.ArgumentParser(
        description="Short-term memory CLI for agent OS (P9 WP1)"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # init
    p_init = subparsers.add_parser("init", help="Initialize the SQLite database")

    # write
    p_write = subparsers.add_parser("write", help="Write a short-term memory record")
    p_write.add_argument("--run-id", required=True)
    p_write.add_argument("--agent-id", required=True)
    p_write.add_argument("--workspace", required=True)
    p_write.add_argument("--intent", required=True)
    p_write.add_argument("--kind", required=True)
    p_write.add_argument("--summary", required=True)
    p_write.add_argument("--content-file", required=True)
    p_write.add_argument("--source-ref", required=True)
    p_write.add_argument("--tag", action="append", default=[])
    p_write.add_argument("--fingerprint", default=None)
    p_write.add_argument(
        "--boundary-kind",
        choices=["session", "memory", "brain"],
        default=None,
        help="Boundary tier for this record (session|memory|brain). NULL = legacy.",
    )
    p_write.add_argument(
        "--evidence-ref",
        action="append",
        default=[],
        help="Citation/evidence reference (repeatable). Required for brain-tier unless --justify-no-evidence supplied.",
    )
    p_write.add_argument(
        "--justify-no-evidence",
        default=None,
        help="Required for brain-tier writes that lack evidence refs.",
    )

    # query
    p_query = subparsers.add_parser("query", help="Search short-term memory records")
    p_query.add_argument("--workspace", default="any")
    p_query.add_argument("--intent", default="any")
    p_query.add_argument("--text", required=True)
    p_query.add_argument("--limit", type=int, default=10)
    p_query.add_argument("--kind", default=None)

    # get
    p_get = subparsers.add_parser("get", help="Get a single record by ID")
    p_get.add_argument("--id", required=True)

    # update-status
    p_update = subparsers.add_parser(
        "update-status", help="Update record status"
    )
    p_update.add_argument("--id", required=True)
    p_update.add_argument("--status", required=True)

    # mark-candidate
    p_mark = subparsers.add_parser(
        "mark-candidate", help="Mark record as promotion candidate"
    )
    p_mark.add_argument("--id", required=True)
    p_mark.add_argument("--reason", required=True)

    # set-promote-state
    p_sps = subparsers.add_parser(
        "set-promote-state",
        help="Set promote_state to promoted/rejected (via memory-st interface)",
    )
    p_sps.add_argument("--id", required=True)
    p_sps.add_argument("--state", required=True,
                       help="'promoted', 'rejected', 'proposed', or 'approved'")
    p_sps.add_argument("--reason", default=None,
                       help="Optional reason tag")

    # add-tag
    p_add_tag = subparsers.add_parser(
        "add-tag",
        help="Attach a tag to an existing record",
    )
    p_add_tag.add_argument("--id", required=True)
    p_add_tag.add_argument("--tag", required=True)

    # get-by-fingerprint
    p_gbf = subparsers.add_parser(
        "get-by-fingerprint",
        help="Look up a record by its fingerprint hash",
    )
    p_gbf.add_argument("--fingerprint", required=True)

    # unresolved-help
    p_help = subparsers.add_parser(
        "unresolved-help", help="List unresolved HELP requests"
    )
    p_help.add_argument("--workspace", default="any")

    # packet-context
    p_pctx = subparsers.add_parser(
        "packet-context", help="Get packet context for a run ID"
    )
    p_pctx.add_argument("--run-id", required=True)
    p_pctx.add_argument("--json", action="store_true", default=False)

    # set-decision
    p_sd = subparsers.add_parser(
        "set-decision", help="Record a stumble triage decision"
    )
    p_sd.add_argument("--fingerprint", required=True)
    p_sd.add_argument("--decision", required=True, choices=["fix", "guardrail", "document", "ignore"])
    p_sd.add_argument("--note", default=None)
    p_sd.add_argument("--decided-by", default=None)
    p_sd.add_argument("--spec-path", default=None)

    # get-decisions
    p_gds = subparsers.add_parser(
        "get-decisions", help="List all stumble triage decisions"
    )
    p_gds.add_argument("--decision", default=None, help="Filter by decision type")

    # get-decision
    p_gd = subparsers.add_parser(
        "get-decision", help="Get a decision by fingerprint"
    )
    p_gd.add_argument("--fingerprint", required=True)

    # delete
    p_del = subparsers.add_parser(
        "delete", help="Delete a record and its FTS/tag/cluster entries"
    )
    p_del.add_argument("--id", required=True, help="Record id to delete")

    return parser


# ── Main Entry Point ──────────────────────────────────────────────────────

COMMAND_MAP = {
    "init": cmd_init,
    "write": cmd_write,
    "query": cmd_query,
    "get": cmd_get,
    "update-status": cmd_update_status,
    "mark-candidate": cmd_mark_candidate,
    "set-promote-state": cmd_set_promote_state,
    "add-tag": cmd_add_tag,
    "get-by-fingerprint": cmd_get_by_fingerprint,
    "unresolved-help": cmd_unresolved_help,
    "packet-context": cmd_packet_context,
    "set-decision": cmd_set_decision,
    "get-decisions": cmd_get_decisions,
    "get-decision": cmd_get_decision,
    "delete": cmd_delete,
}


def main():
    parser = build_parser()
    args = parser.parse_args()

    handler = COMMAND_MAP.get(args.command)
    if handler:
        handler(args)
    else:
        print(json.dumps({"ok": False, "error": f"Unknown command: {args.command}"}))
        sys.exit(1)


if __name__ == "__main__":
    main()
