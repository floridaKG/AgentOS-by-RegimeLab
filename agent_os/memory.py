"""Shared memory service adapter for the Agent OS core.

Provides a thin wrapper over the existing short_term.py implementation
for CLI and MCP use. Calls the underlying SQLite functions directly.
"""

from __future__ import annotations

import json
import sqlite3
import time
import random
import string
from pathlib import Path
from typing import Any

from agent_os.paths import (
    get_short_term_db_path,
    get_schema_path,
    ensure_state_dirs,
)
from agent_os.models import MemoryRecord, OperationResult


# Allowed values matching short_term.py
ALLOWED_INTENTS = {
    "OBSERVATION", "LESSON", "DECISION", "STUMBLE", "CONFIRMED",
    "OPS", "HELP", "VERIFICATION", "STATE", "LEARNING", "IMPLEMENT",
    "BUG", "SPEC", "DOCS", "RESEARCH",
}

ALLOWED_KINDS = {
    "packet_summary", "status", "observation", "stumble",
    "confirmed", "help_request", "help_resolution", "verification", "state",
}

MAX_SEARCH_LIMIT = 100
MAX_LIST_LIMIT = 200


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _generate_id() -> str:
    ts = time.strftime("%Y%m%d")
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"st_{ts}_{suffix}"


def _generate_run_id() -> str:
    return f"run_{time.strftime('%Y%m%d')}_" + "".join(
        random.choices(string.ascii_lowercase + string.digits, k=8)
    )


def _sanitize_fts5(query: str) -> str:
    """Strip FTS5 special operators for safe search."""
    import re
    cleaned = re.sub(
        r'[\^"()+\-*]|\b(?:NOT|AND|OR|NEAR)\b',
        " ",
        query,
        flags=re.IGNORECASE,
    )
    tokens = cleaned.split()
    if not tokens:
        return '""'
    return " AND ".join(tokens)


def _get_conn() -> sqlite3.Connection:
    """Get a SQLite connection with proper setup."""
    db_path = get_short_term_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA busy_timeout = 30000;")
    conn.row_factory = sqlite3.Row
    return conn


def ensure_db() -> None:
    """Initialize the database schema if needed."""
    ensure_state_dirs()
    schema_path = get_schema_path()
    if not schema_path.exists():
        raise FileNotFoundError(
            f"Schema file not found: {schema_path}. "
            "Is AGENT_OS_HOME set correctly?"
        )
    conn = _get_conn()
    try:
        schema_sql = schema_path.read_text()
        conn.executescript(schema_sql)
        conn.commit()
    finally:
        conn.close()


def add_memory(
    text: str,
    *,
    intent: str = "LESSON",
    kind: str = "observation",
    workspace: str = "default",
    agent_id: str = "user",
    run_id: str | None = None,
    source_ref: str = "cli:agent-os",
    summary: str | None = None,
) -> OperationResult:
    """Add a memory record to the short-term store.

    Uses safe defaults for all optional metadata fields.
    """
    # Validate
    intent_upper = intent.upper()
    if intent_upper not in ALLOWED_INTENTS:
        return OperationResult(
            ok=False,
            error=f"Invalid intent '{intent}'. Allowed: {', '.join(sorted(ALLOWED_INTENTS))}",
        )
    kind_lower = kind.lower()
    if kind_lower not in ALLOWED_KINDS:
        return OperationResult(
            ok=False,
            error=f"Invalid kind '{kind}'. Allowed: {', '.join(sorted(ALLOWED_KINDS))}",
        )

    record_id = _generate_id()
    actual_run_id = run_id or _generate_run_id()
    actual_summary = summary or text[:200]
    now = _now_iso()

    try:
        ensure_db()
        conn = _get_conn()
        try:
            conn.execute(
                """INSERT INTO st_records
                   (id, run_id, message_id, agent_id, workspace, intent, kind,
                    content, summary, source_ref, status, promote_state,
                    fingerprint, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record_id, actual_run_id, None, agent_id, workspace,
                    intent_upper, kind_lower, text, actual_summary,
                    source_ref, "active", "none", None, now, now,
                ),
            )
            conn.execute(
                "INSERT INTO st_records_fts(id, content, summary) VALUES (?, ?, ?)",
                (record_id, text, actual_summary),
            )
            conn.commit()
            return OperationResult(
                ok=True,
                data={"id": record_id, "intent": intent_upper, "kind": kind_lower},
            )
        finally:
            conn.close()
    except Exception as e:
        return OperationResult(ok=False, error=str(e))


def search_memory(
    query: str,
    *,
    tier: str = "short_term",
    limit: int = 10,
    workspace: str | None = None,
    intent: str | None = None,
) -> OperationResult:
    """Search memory records using FTS5 full-text search."""
    if limit < 1:
        limit = 1
    if limit > MAX_SEARCH_LIMIT:
        limit = MAX_SEARCH_LIMIT

    try:
        ensure_db()
        conn = _get_conn()
        try:
            safe_query = _sanitize_fts5(query)
            conditions = ["fts.id = r.id", "st_records_fts MATCH ?"]
            params: list[Any] = [safe_query]

            if workspace and workspace != "any":
                conditions.append("r.workspace = ?")
                params.append(workspace)
            if intent and intent.upper() != "ANY":
                conditions.append("r.intent = ?")
                params.append(intent.upper())

            where = " AND ".join(conditions)
            sql = f"""
                SELECT r.id, r.workspace, r.intent, r.kind, r.summary,
                       r.content, r.source_ref, r.status, r.agent_id,
                       r.created_at, rank as score
                FROM st_records_fts fts
                JOIN st_records r ON fts.id = r.id
                WHERE {where}
                ORDER BY rank
                LIMIT ?
            """
            params.append(limit)

            rows = conn.execute(sql, params).fetchall()
            results = []
            for row in rows:
                d = dict(row)
                results.append(MemoryRecord(
                    id=d["id"],
                    summary=d.get("summary", ""),
                    content=d.get("content", ""),
                    intent=d.get("intent", ""),
                    kind=d.get("kind", ""),
                    workspace=d.get("workspace", ""),
                    agent_id=d.get("agent_id", ""),
                    source_ref=d.get("source_ref", ""),
                    status=d.get("status", ""),
                    created_at=d.get("created_at", ""),
                    score=round(d.get("score", 0), 2),
                ).to_dict())

            return OperationResult(ok=True, data={"results": results})
        finally:
            conn.close()
    except Exception as e:
        return OperationResult(ok=False, error=str(e))


def list_memory(
    *,
    intent: str | None = None,
    workspace: str | None = None,
    limit: int = 20,
) -> OperationResult:
    """List memory records with optional filters."""
    if limit < 1:
        limit = 1
    if limit > MAX_LIST_LIMIT:
        limit = MAX_LIST_LIMIT

    try:
        ensure_db()
        conn = _get_conn()
        try:
            conditions: list[str] = []
            params: list[Any] = []

            if intent and intent.upper() != "ANY":
                conditions.append("intent = ?")
                params.append(intent.upper())
            if workspace and workspace != "any":
                conditions.append("workspace = ?")
                params.append(workspace)

            where = ""
            if conditions:
                where = "WHERE " + " AND ".join(conditions)

            sql = f"""
                SELECT id, workspace, intent, kind, summary, content,
                       source_ref, status, agent_id, created_at
                FROM st_records
                {where}
                ORDER BY created_at DESC
                LIMIT ?
            """
            params.append(limit)

            rows = conn.execute(sql, params).fetchall()
            results = []
            for row in rows:
                d = dict(row)
                results.append(MemoryRecord(
                    id=d["id"],
                    summary=d.get("summary", ""),
                    content=d.get("content", ""),
                    intent=d.get("intent", ""),
                    kind=d.get("kind", ""),
                    workspace=d.get("workspace", ""),
                    agent_id=d.get("agent_id", ""),
                    source_ref=d.get("source_ref", ""),
                    status=d.get("status", ""),
                    created_at=d.get("created_at", ""),
                ).to_dict())

            return OperationResult(ok=True, data={"results": results, "count": len(results)})
        finally:
            conn.close()
    except Exception as e:
        return OperationResult(ok=False, error=str(e))


def memory_health() -> OperationResult:
    """Check the health of the local memory subsystem."""
    from agent_os.paths import get_agent_os_home
    from agent_os.models import DiagnosticItem, DiagnosticReport

    report = DiagnosticReport()
    db_path = get_short_term_db_path()
    schema_path = get_schema_path()

    # Schema file check
    if schema_path.exists():
        report.add(DiagnosticItem(
            name="schema_file",
            status="ok",
            message=f"Schema found at {schema_path}",
        ))
    else:
        report.add(DiagnosticItem(
            name="schema_file",
            status="error",
            message=f"Schema not found at {schema_path}",
        ))

    # Database file check
    if db_path.exists():
        report.add(DiagnosticItem(
            name="database_file",
            status="ok",
            message=f"Database exists at {db_path}",
        ))
    else:
        report.add(DiagnosticItem(
            name="database_file",
            status="warn",
            message=f"Database not initialized at {db_path}. Run 'agent-os init'.",
        ))
        return OperationResult(ok=True, data=report.to_dict())

    # Connectivity check
    try:
        conn = _get_conn()
        try:
            # Check schema has required tables
            tables = {
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            required = {"st_records", "st_tags", "st_help_requests"}
            missing = required - tables
            if missing:
                report.add(DiagnosticItem(
                    name="schema_tables",
                    status="error",
                    message=f"Missing tables: {', '.join(sorted(missing))}",
                    details={"missing": sorted(missing)},
                ))
            else:
                report.add(DiagnosticItem(
                    name="schema_tables",
                    status="ok",
                    message="All required tables present",
                ))

            # Record count
            count = conn.execute(
                "SELECT COUNT(*) FROM st_records"
            ).fetchone()[0]
            report.add(DiagnosticItem(
                name="record_count",
                status="ok",
                message=f"{count} records in short-term store",
                details={"count": count},
            ))

            # WAL mode check
            journal = conn.execute("PRAGMA journal_mode").fetchone()[0]
            if journal.lower() == "wal":
                report.add(DiagnosticItem(
                    name="journal_mode",
                    status="ok",
                    message="WAL mode enabled",
                ))
            else:
                report.add(DiagnosticItem(
                    name="journal_mode",
                    status="warn",
                    message=f"Journal mode is '{journal}', expected 'wal'",
                ))

        finally:
            conn.close()
    except Exception as e:
        report.add(DiagnosticItem(
            name="database_connectivity",
            status="error",
            message=f"Cannot connect to database: {e}",
        ))

    return OperationResult(ok=True, data=report.to_dict())
