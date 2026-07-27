#!/usr/bin/python3
"""
citation.py — Citation token module for memory provenance v2 WP1.1.

Every retrieval from a memory backend is wrapped with a CitationRef whose
`ref_id` is `cit-<uuid7>`. Refs are persisted to a small SQLite DB so they
can be resolved later for audit. Rows older than 90 days are pruned by a
nightly cron entry that calls `prune_expired()`.

Python 3.12.3 lacks `uuid.uuid7()`, so we hand-roll a minimal v7 generator.
"""

import hashlib
import json
import os
import random
import sqlite3
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

_AOH = os.environ.get("AGENT_OS_HOME") or os.path.dirname(os.path.abspath(__file__))


# ── Constants ──────────────────────────────────────────────────────────────

_DB_PATH = f"{_AOH}/.local/state/agent-os/memory/citations.sqlite"
_SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema_citations.sql")
_SNIPPET_MAX = 200
_EXPIRY_DAYS = 90


# ── uuid7 hand-roll ────────────────────────────────────────────────────────

def uuid7():
    """Minimal UUID v7: 48-bit ms timestamp + version + 74 random bits."""
    timestamp_ms = int(time.time() * 1000)
    rand_bits = random.getrandbits(74)
    u = uuid.UUID(int=(timestamp_ms << 80) | (1 << 76) | (rand_bits & ((1 << 76) - 1)))
    return str(u)


# ── DB plumbing ────────────────────────────────────────────────────────────

def _db_path():
    p = Path(_DB_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    return str(p)


def _get_conn():
    """Open the citations SQLite db, applying schema on first connect."""
    path = _db_path()
    first_init = not os.path.exists(path) or os.path.getsize(path) == 0
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    if first_init and os.path.isfile(_SCHEMA_PATH):
        with open(_SCHEMA_PATH, "r") as f:
            conn.executescript(f.read())
        conn.commit()
    else:
        # Ensure table exists even if file was created blank elsewhere.
        if os.path.isfile(_SCHEMA_PATH):
            with open(_SCHEMA_PATH, "r") as f:
                conn.executescript(f.read())
            conn.commit()
    return conn


def _now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── Public API ─────────────────────────────────────────────────────────────

def generate_ref(backend, namespace, record_id, snippet, agent_id, run_id):
    """Create a CitationRef dict and persist it to SQLite."""
    ref_id = "cit-" + uuid7()
    snippet_str = "" if snippet is None else str(snippet)
    snippet_trim = snippet_str[:_SNIPPET_MAX]
    retrieved_at = _now_iso()
    ref = {
        "ref_id": ref_id,
        "source_backend": str(backend or ""),
        "source_namespace": str(namespace or ""),
        "source_record_id": str(record_id or ""),
        "snippet": snippet_trim,
        "retrieved_at": retrieved_at,
        "agent_id": str(agent_id or ""),
        "run_id": str(run_id or ""),
    }
    try:
        conn = _get_conn()
        try:
            conn.execute(
                "INSERT INTO citations "
                "(ref_id, source_backend, source_namespace, source_record_id, "
                " snippet, retrieved_at, agent_id, run_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    ref["ref_id"],
                    ref["source_backend"],
                    ref["source_namespace"],
                    ref["source_record_id"],
                    ref["snippet"],
                    ref["retrieved_at"],
                    ref["agent_id"],
                    ref["run_id"],
                ),
            )
            conn.commit()
        finally:
            conn.close()
    except sqlite3.Error:
        # Persistence failure should not break retrieval — return ref anyway.
        pass
    return ref


def resolve(ref_id):
    """Look up a CitationRef by ref_id. Returns dict or None."""
    try:
        conn = _get_conn()
        try:
            row = conn.execute(
                "SELECT ref_id, source_backend, source_namespace, source_record_id, "
                "snippet, retrieved_at, agent_id, run_id "
                "FROM citations WHERE ref_id = ?",
                (ref_id,),
            ).fetchone()
        finally:
            conn.close()
    except sqlite3.Error:
        return None
    if row is None:
        return None
    return dict(row)


def _derive_record_id(result):
    for key in ("id", "_id", "record_id", "node_id"):
        if key in result and result[key]:
            return str(result[key])
    return hashlib.sha1(repr(result).encode("utf-8")).hexdigest()[:16]


def _derive_snippet(result):
    for key in ("snippet", "chunk_text", "content", "summary", "text"):
        if key in result and result[key]:
            return str(result[key])
    return repr(result)


def wrap_results(results, backend, namespace, agent_id, run_id):
    """For each result dict, attach a `citation_ref` field."""
    wrapped = []
    if not results:
        return wrapped
    for r in results:
        if not isinstance(r, dict):
            wrapped.append(r)
            continue
        rec_id = _derive_record_id(r)
        snip = _derive_snippet(r)
        ref = generate_ref(
            backend=backend,
            namespace=namespace,
            record_id=rec_id,
            snippet=snip,
            agent_id=agent_id,
            run_id=run_id,
        )
        new_r = dict(r)
        new_r["citation_ref"] = ref
        wrapped.append(new_r)
    return wrapped


def prune_expired(now=None):
    """Delete citations whose created_at is older than 90 days. Returns count."""
    if now is None:
        now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=_EXPIRY_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
    try:
        conn = _get_conn()
        try:
            cur = conn.execute(
                "DELETE FROM citations WHERE created_at < ?",
                (cutoff,),
            )
            conn.commit()
            return cur.rowcount or 0
        finally:
            conn.close()
    except sqlite3.Error:
        return 0


# ── CLI ────────────────────────────────────────────────────────────────────

def _main(argv):
    if len(argv) < 2:
        print("usage: citation.py {prune-expired|resolve <ref_id>}", file=sys.stderr)
        return 2
    cmd = argv[1]
    if cmd == "prune-expired":
        n = prune_expired()
        print(json.dumps({"ok": True, "pruned": n}))
        return 0
    if cmd == "resolve":
        if len(argv) < 3:
            print("usage: citation.py resolve <ref_id>", file=sys.stderr)
            return 2
        ref = resolve(argv[2])
        print(json.dumps({"ok": ref is not None, "ref": ref}))
        return 0 if ref is not None else 1
    print(f"unknown subcommand: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
