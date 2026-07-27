#!/usr/bin/env python3
"""
memory-health-gate.py — Memory stack health gate for public Agent OS.

Checks short-term FTS, FTS consistency, optional Pinecone/Neo4j connectivity,
optional semantic retrieval, and (when present) behavioral contracts. Designed
for open installs: optional backends are SKIPPED when env vars are absent, not
treated as failures.

Exit codes:
  0 - HEALTHY: core short-term memory is trustworthy; optional tiers either
      GREEN or intentionally SKIPPED.
  1 - DEGRADED: usable, but a configured optional tier is unhealthy and/or
      FTS consistency needed repair / reported drift.
  2 - CRITICAL: short-term FTS failed, or a present behavioral suite regressed.

Usage:
  python3 scripts/memory-health-gate.py [--json] [--golden] [--read-only]
    --json              Pretty-print JSON (default: compact single-line)
    --golden            Run optional golden retrieval canaries
    --read-only         Do not self-heal FTS orphans; report drift only
    --check-consistency Run only marker-vs-live consistency, then exit
    --help              Show this help

Environment:
  AGENT_OS_HOME         Install root (defaults to parent of scripts/)
  AGENT_OS_ST_DB        Override short-term SQLite path
  PINECONE_API_KEY      Optional; enables Pinecone checks
  PINECONE_INDEX        Optional; default agent-vault
  NEO4J_URI/USER/PASSWORD  Optional; enables Neo4j checks

Private runtime bridges are intentionally not checked here. For the optional
public Hindsight adapter, use scripts/hindsight-health-check.py.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


# ── Paths / env ─────────────────────────────────────────────────────────────

_SCRIPT_PATH = Path(__file__).resolve()
AGENT_OS_HOME = Path(
    os.environ.get("AGENT_OS_HOME") or str(_SCRIPT_PATH.parent.parent)
).resolve()

# Keep process env consistent for child CLIs that resolve via AGENT_OS_HOME.
os.environ.setdefault("AGENT_OS_HOME", str(AGENT_OS_HOME))

MEMORY_ST = AGENT_OS_HOME / "bin" / "memory-st"
MEMORY_LT = AGENT_OS_HOME / "bin" / "memory-lt"
MEMORY_RECALL = AGENT_OS_HOME / "bin" / "memory-recall"

ST_DB = Path(
    os.path.expanduser(
        os.environ.get(
            "AGENT_OS_ST_DB",
            str(Path.home() / ".local" / "state" / "agent-os" / "memory" / "short_term.sqlite"),
        )
    )
)

TOMBSTONE = AGENT_OS_HOME / "memory" / "short_term.db.tombstone"

BACKEND_TIMEOUT = 45
BEHAVIORAL_TIMEOUT = 180
GOLDEN_TIMEOUT = 20
GATE_OVERALL_TIMEOUT = 300

# Optional modules live under memory/core (short_term, _envload).
_CORE_DIR = AGENT_OS_HOME / "memory" / "core"
if _CORE_DIR.is_dir():
    sys.path.insert(0, str(_CORE_DIR))


def _load_env() -> None:
    """Load optional env files without failing if loaders/deps are missing."""
    try:
        from _envload import load_env  # type: ignore

        load_env()
    except Exception:
        pass

    # Public install path used by install.sh / SETUP.md
    config_env = Path.home() / ".config" / "agent-os" / "config.env"
    if config_env.is_file():
        try:
            for raw in config_env.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("export "):
                    line = line[7:]
                if "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key:
                    os.environ.setdefault(key, val)
        except OSError:
            pass


_load_env()


def _alarm_handler(signum: int, frame: Any) -> None:
    output = {
        "gate": "memory-health-gate",
        "overall": "TIMEOUT",
        "detail": f"exceeded {GATE_OVERALL_TIMEOUT}s hard limit",
        "tiers": {},
        "exit_code": 2,
    }
    print(json.dumps(output))
    sys.exit(2)


if hasattr(signal, "SIGALRM"):
    signal.signal(signal.SIGALRM, _alarm_handler)
    signal.alarm(GATE_OVERALL_TIMEOUT)


def _run_cmd(
    cmd: list[str],
    timeout: int = BACKEND_TIMEOUT,
) -> tuple[int, str, str]:
    """Run a command; never raises. Returns (returncode, stdout, stderr)."""
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()
    except subprocess.TimeoutExpired:
        return -1, "", f"timed out after {timeout}s"
    except FileNotFoundError as exc:
        return -1, "", f"not found: {exc}"
    except Exception as exc:  # noqa: BLE001 — gate must never crash
        return -1, "", str(exc)[:160]


def _is_executable(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)


def _pinecone_configured() -> bool:
    key = (os.environ.get("PINECONE_API_KEY") or "").strip()
    if not key:
        return False
    lowered = key.lower()
    return "your-" not in lowered and "placeholder" not in lowered


def _neo4j_configured() -> bool:
    return all(
        (os.environ.get(name) or "").strip()
        for name in ("NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD")
    )


# ── Tier checks ─────────────────────────────────────────────────────────────

def check_st_fts() -> tuple[str, str]:
    """Check short-term memory FTS query works. GREEN or RED."""
    if not _is_executable(MEMORY_ST):
        return "RED", f"binary not found or not executable: {MEMORY_ST}"

    rc, out, err = _run_cmd(
        [str(MEMORY_ST), "query", "--text", "state", "--limit", "1"],
        timeout=BACKEND_TIMEOUT,
    )
    if rc == -1 and err.startswith("timed out"):
        return "RED", err
    if rc != 0:
        detail = err[:160] or out[:160] or f"exit code {rc}"
        return "RED", detail

    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return "RED", f"non-JSON output: {out[:160]}"

    if not data.get("ok"):
        return "RED", str(data.get("error", "ok=false"))[:160]

    count = len(data.get("results") or [])
    return "GREEN", f"query returned {count} result(s)"


def check_st_fts_consistency(read_only: bool = False) -> tuple[str, str]:
    """Verify FTS5 index and tags stay in sync with st_records.

    GREEN  = every shadow id exists in st_records
    YELLOW = orphans found (healed this run, or reported in --read-only)
    RED    = orphans found and removal failed
    SKIPPED = ST db not found
    """
    if not ST_DB.is_file():
        return "SKIPPED", f"ST db not found: {ST_DB}"

    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(str(ST_DB), timeout=30)
        conn.execute("PRAGMA busy_timeout = 30000;")
        conn.execute("PRAGMA foreign_keys = ON;")
        cur = conn.cursor()

        # Tables may be missing on a fresh / partial install.
        tables = {
            row[0]
            for row in cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if "st_records" not in tables:
            return "RED", "st_records table missing (run memory-st init)"

        fts_orphans = 0
        tag_orphans = 0
        prop_orphans = 0

        if "st_records_fts" in tables:
            fts_orphans = cur.execute(
                "SELECT COUNT(*) FROM st_records_fts f "
                "WHERE f.id NOT IN (SELECT id FROM st_records)"
            ).fetchone()[0]
        if "st_tags" in tables:
            tag_orphans = cur.execute(
                "SELECT COUNT(*) FROM st_tags t "
                "WHERE t.record_id NOT IN (SELECT id FROM st_records)"
            ).fetchone()[0]
        if "memory_proposals" in tables:
            prop_orphans = cur.execute(
                "SELECT COUNT(*) FROM memory_proposals p "
                "WHERE p.st_record_id NOT IN (SELECT id FROM st_records)"
            ).fetchone()[0]

        total = fts_orphans + tag_orphans + prop_orphans
        if total == 0:
            return "GREEN", "FTS/tags/proposals in sync with st_records"

        if read_only:
            return "YELLOW", (
                f"orphans present (read-only, not healed): "
                f"{total} total ({fts_orphans} fts + {tag_orphans} tags "
                f"+ {prop_orphans} proposals); repair via non-read-only run"
            )

        try:
            from short_term import sync_fts_to_base  # type: ignore
        except Exception as exc:  # noqa: BLE001
            return "RED", (
                f"orphans present ({total}) but short_term.sync_fts_to_base "
                f"unavailable: {exc!r}"
            )

        removed = sync_fts_to_base(conn)
        return "YELLOW", (
            f"removed {removed} orphan shadow row(s) "
            f"(was {total}; {fts_orphans} fts + {tag_orphans} tags "
            f"+ {prop_orphans} proposals)"
        )
    except Exception as exc:  # noqa: BLE001
        return "RED", f"consistency check error: {exc!r}"
    finally:
        if conn is not None:
            conn.close()


def check_graph() -> tuple[str, str]:
    """Check optional Neo4j graph backend.

    SKIPPED when env is unset. GREEN when live connection works.
    """
    if not _neo4j_configured():
        return "SKIPPED", "Neo4j env vars not configured; graph tier optional"

    try:
        from neo4j import GraphDatabase  # type: ignore
    except ImportError:
        return "YELLOW", "neo4j Python package not installed (pip install neo4j)"
    except Exception as exc:  # noqa: BLE001
        return "YELLOW", f"neo4j import error: {exc!r}"

    uri = os.environ["NEO4J_URI"]
    user = os.environ["NEO4J_USER"]
    password = os.environ["NEO4J_PASSWORD"]
    try:
        driver = GraphDatabase.driver(uri, auth=(user, password))
        try:
            with driver.session() as session:
                session.run("RETURN 1 AS ok").single()
        finally:
            driver.close()
        return "GREEN", "Neo4j connection live"
    except Exception as exc:  # noqa: BLE001
        return "YELLOW", f"connection failed: {str(exc)[:160]}"


def check_pinecone_connectivity() -> tuple[str, str]:
    """Check optional Pinecone SDK and index connectivity."""
    if not _pinecone_configured():
        return "SKIPPED", "PINECONE_API_KEY not set; Pinecone optional"

    try:
        from pinecone import Pinecone  # type: ignore
    except ImportError:
        return "YELLOW", "pinecone Python package not installed (pip install pinecone)"
    except Exception as exc:  # noqa: BLE001
        return "YELLOW", f"pinecone import error: {exc!r}"

    index_name = os.environ.get("PINECONE_INDEX", "agent-vault")
    try:
        pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"], source_tag="agent_os_public")
        if hasattr(pc, "describe_index"):
            pc.describe_index(index_name)
            return "GREEN", f"Pinecone SDK available, index reachable ({index_name})"
        # Older/newer SDK surface: open Index and describe_index_stats
        index = pc.Index(index_name)
        if hasattr(index, "describe_index_stats"):
            index.describe_index_stats()
        return "GREEN", f"Pinecone SDK available, index reachable ({index_name})"
    except Exception as exc:  # noqa: BLE001
        return "YELLOW", f"Pinecone index check failed: {str(exc)[:160]}"


def check_semantic_retrieval() -> tuple[str, str]:
    """Real semantic search probe via memory-lt (optional)."""
    if not _pinecone_configured():
        return "SKIPPED", "PINECONE_API_KEY not set; skipping semantic probe"

    if not _is_executable(MEMORY_LT):
        return "SKIPPED", f"binary not found: {MEMORY_LT}"

    rc, out, err = _run_cmd(
        [
            str(MEMORY_LT),
            "search-vector",
            "--namespace",
            "agent-os-docs",
            "--text",
            "memory health gate semantic probe",
            "--limit",
            "1",
        ],
        timeout=BACKEND_TIMEOUT,
    )
    payload_text = out or err
    if rc == -1 and "timed out" in err:
        return "YELLOW", err

    try:
        data = json.loads(payload_text)
    except json.JSONDecodeError:
        return "RED", f"invalid probe output: {payload_text[:160]}"

    errors = data.get("namespace_errors") or []
    if rc != 0 or not data.get("ok"):
        joined_err = str(data.get("error") or payload_text)[:160]
        if "RESOURCE_EXHAUSTED" in joined_err or "429" in joined_err:
            return "YELLOW", f"quota-exhausted: {joined_err}"
        if "not configured" in joined_err.lower():
            return "SKIPPED", joined_err
        return "RED", joined_err

    if errors:
        joined = "; ".join(
            f"{e.get('namespace', '?')}: {str(e.get('error', ''))[:120]}" for e in errors
        )
        if "RESOURCE_EXHAUSTED" in joined or "429" in joined:
            return "YELLOW", f"quota-exhausted: {joined}"
        return "RED", joined

    total_found = data.get("total_found")
    if total_found is None:
        total_found = data.get("result_count", len(data.get("results") or []))
    if total_found == 0:
        return "YELLOW", "probe succeeded but returned 0 results"
    return "GREEN", f"probe returned {total_found} result(s)"


def check_behavioral_contracts() -> tuple[str, str]:
    """Run offline behavioral suite when present; otherwise SKIPPED.

    Public OSS does not ship the private memory/tests suite. When a suite
    exists under memory/tests or tests/memory, pytest is invoked fail-closed.
    """
    candidates = [
        AGENT_OS_HOME / "memory" / "tests",
        AGENT_OS_HOME / "tests" / "memory",
    ]
    tests_dir = next((p for p in candidates if p.is_dir()), None)
    if tests_dir is None:
        return "SKIPPED", "no memory behavioral test suite present (optional)"

    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", str(tests_dir), "-q", "--no-header"],
            capture_output=True,
            text=True,
            timeout=BEHAVIORAL_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return "RED", f"behavioral suite timed out after {BEHAVIORAL_TIMEOUT}s"
    except FileNotFoundError:
        return "YELLOW", "pytest not available (pip install pytest)"
    except Exception as exc:  # noqa: BLE001
        return "YELLOW", f"behavioral suite error: {exc!r}"

    last = ((proc.stdout or "").strip().splitlines() or ["no output"])[-1]
    if proc.returncode == 0:
        return "GREEN", f"behavioral contracts pass ({last})"
    return "RED", f"behavioral contract FAILURE: {last}"


# ── Golden retrieval (opt-in, public-safe) ──────────────────────────────────

# Generic canaries only — no private workspace names, paths, or secrets.
GOLDEN_QUERIES: list[dict[str, Any]] = [
    {
        "query": "lesson",
        "tier": "short_term",
        "min_results": 0,
        "note": "short_term probe (0 results allowed on empty installs)",
    },
    {
        "query": "agent memory",
        "tier": "semantic",
        "min_results": 1,
        "requires": "pinecone",
    },
    {
        "query": "memory",
        "tier": "graph",
        "min_results": 1,
        "requires": "neo4j",
    },
]


def _expect_label(gq: dict[str, Any]) -> str:
    if gq.get("expect_any"):
        return " | ".join(gq["expect_any"])
    return f"tier:{gq.get('tier')}>={gq.get('min_results', 1)} result(s)"


def check_golden_retrieval() -> tuple[str, str, list[dict[str, Any]]]:
    """Optional golden queries. Tiers not configured are skipped."""
    if not _is_executable(MEMORY_RECALL):
        return "RED", f"memory-recall binary not found: {MEMORY_RECALL}", []

    hits = 0
    queries: list[dict[str, Any]] = []

    for gq in GOLDEN_QUERIES:
        query_text = gq["query"]
        requires = gq.get("requires")
        if requires == "pinecone" and not _pinecone_configured():
            queries.append(
                {
                    "query": query_text,
                    "expect": _expect_label(gq),
                    "tier": gq.get("tier"),
                    "hit": False,
                    "skipped": True,
                    "skip_reason": "Pinecone not configured",
                    "top_source": None,
                }
            )
            continue
        if requires == "neo4j" and not _neo4j_configured():
            queries.append(
                {
                    "query": query_text,
                    "expect": _expect_label(gq),
                    "tier": gq.get("tier"),
                    "hit": False,
                    "skipped": True,
                    "skip_reason": "Neo4j not configured",
                    "top_source": None,
                }
            )
            continue

        expects = [e.lower() for e in gq.get("expect_any", [])]
        tier_pin = gq.get("tier")
        min_results = int(gq.get("min_results", 0))
        cmd = [str(MEMORY_RECALL), "--text", query_text, "--limit", "5"]
        if tier_pin:
            cmd += ["--tier", tier_pin]

        rc, out, err = _run_cmd(cmd, timeout=GOLDEN_TIMEOUT)
        if rc == -1 and "timed out" in err:
            queries.append(
                {
                    "query": query_text,
                    "expect": _expect_label(gq),
                    "hit": False,
                    "error": err,
                    "top_source": None,
                }
            )
            continue
        if rc != 0 and not out:
            queries.append(
                {
                    "query": query_text,
                    "expect": _expect_label(gq),
                    "hit": False,
                    "error": (err or f"exit {rc}")[:120],
                    "top_source": None,
                }
            )
            continue

        try:
            data = json.loads(out)
        except (json.JSONDecodeError, ValueError):
            queries.append(
                {
                    "query": query_text,
                    "expect": _expect_label(gq),
                    "hit": False,
                    "error": f"non-JSON output: {out[:100]}",
                    "top_source": None,
                }
            )
            continue

        results_list = data.get("results") or data.get("combined") or []
        tier_results = data.get("tier_results") or {}
        if tier_pin and isinstance(results_list, list):
            filtered = [r for r in results_list if r.get("tier") == tier_pin]
            if filtered or tier_pin in tier_results:
                results_list = filtered if filtered else results_list
            pinned = tier_results.get(tier_pin, {}) if isinstance(tier_results, dict) else {}
            pinned_status = pinned.get("status") if isinstance(pinned, dict) else None
            if pinned_status in ("error", "quota_exhausted", "unavailable"):
                queries.append(
                    {
                        "query": query_text,
                        "expect": _expect_label(gq),
                        "tier": tier_pin,
                        "hit": False,
                        "error": f"tier status: {pinned_status}",
                        "top_source": "",
                    }
                )
                continue

        top_source = ""
        if results_list and isinstance(results_list[0], dict):
            top_source = (
                results_list[0].get("source_path")
                or results_list[0].get("source_ref")
                or ""
            )

        if expects:
            matched = any(
                e in (r.get("source_path", "") or "").lower()
                or e in (r.get("summary", "") or "").lower()
                for r in results_list[:5]
                if isinstance(r, dict)
                for e in expects
            )
        else:
            matched = len(results_list) >= min_results

        if matched:
            hits += 1

        queries.append(
            {
                "query": query_text,
                "expect": _expect_label(gq),
                "tier": tier_pin,
                "hit": matched,
                "top_source": top_source,
            }
        )

    skipped = sum(1 for q in queries if q.get("skipped"))
    total = len(GOLDEN_QUERIES) - skipped
    if total == 0:
        status = "SKIPPED"
    elif hits == total:
        status = "GREEN"
    elif hits >= max(1, total // 2):
        status = "DEGRADED"
    else:
        status = "RED"

    skip_note = f" ({skipped} skipped)" if skipped else ""
    detail = f"golden retrieval {hits}/{total} queries hit expected source{skip_note}"
    return status, detail, queries


# ── Lifecycle + marker consistency ──────────────────────────────────────────

def check_lifecycle_metrics() -> tuple[str, str, dict[str, Any]]:
    """Collect read-only lifecycle metrics (ST + optional backends)."""
    metrics: dict[str, Any] = {}
    collected = 0
    attempted = 0

    # Short-term SQLite
    attempted += 1
    if ST_DB.is_file():
        try:
            conn = sqlite3.connect(str(ST_DB), timeout=10)
            count = conn.execute("SELECT COUNT(*) FROM st_records").fetchone()[0]
            conn.close()
            metrics["short_term"] = {
                "st_records": count,
                "db_exists": True,
                "db_path": str(ST_DB),
            }
            collected += 1
        except Exception as exc:  # noqa: BLE001
            metrics["short_term"] = {"error": str(exc)[:120], "db_exists": True}
    else:
        metrics["short_term"] = {"db_exists": False, "error": "DB not found"}

    # Pinecone (optional)
    attempted += 1
    if not _pinecone_configured():
        metrics["pinecone"] = {"skipped": True, "reason": "not configured"}
        collected += 1
    else:
        try:
            from pinecone import Pinecone  # type: ignore

            index_name = os.environ.get("PINECONE_INDEX", "agent-vault")
            pc = Pinecone(
                api_key=os.environ["PINECONE_API_KEY"],
                source_tag="agent_os_public",
            )
            index = pc.Index(index_name)
            stats = index.describe_index_stats() if hasattr(index, "describe_index_stats") else {}
            if hasattr(stats, "to_dict"):
                stats = stats.to_dict()
            namespaces = {}
            if isinstance(stats, dict):
                ns = stats.get("namespaces") or {}
                if isinstance(ns, dict):
                    namespaces = {
                        name: (info.get("vector_count", 0) if isinstance(info, dict) else 0)
                        for name, info in ns.items()
                    }
                total_vectors = stats.get("total_vector_count", sum(namespaces.values()))
            else:
                total_vectors = 0
            metrics["pinecone"] = {
                "index": index_name,
                "total_vectors": total_vectors,
                "namespaces": namespaces,
            }
            collected += 1
        except Exception as exc:  # noqa: BLE001
            metrics["pinecone"] = {"error": str(exc)[:120]}

    # Neo4j (optional)
    attempted += 1
    if not _neo4j_configured():
        metrics["neo4j"] = {"skipped": True, "reason": "not configured"}
        collected += 1
    else:
        try:
            from neo4j import GraphDatabase  # type: ignore

            driver = GraphDatabase.driver(
                os.environ["NEO4J_URI"],
                auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]),
            )
            try:
                with driver.session() as session:
                    node_count = session.run(
                        "MATCH (n) RETURN count(n) AS c"
                    ).single()["c"]
            finally:
                driver.close()
            metrics["neo4j"] = {"connection": "ok", "node_count": node_count}
            collected += 1
        except Exception as exc:  # noqa: BLE001
            metrics["neo4j"] = {"error": str(exc)[:120]}

    if collected == attempted:
        status = "GREEN"
    elif collected > 0:
        status = "YELLOW"
    else:
        status = "RED"

    detail = f"lifecycle metrics: {collected}/{attempted} tiers collected"
    return status, detail, metrics


def check_marker_vs_live() -> tuple[str, str, list[dict[str, Any]]]:
    """Marker-vs-live consistency for public paths only."""
    checks: list[dict[str, Any]] = []
    mismatch = False

    tombstone_exists = TOMBSTONE.is_file()
    live_exists = ST_DB.is_file()
    live_rows = 0
    if live_exists:
        try:
            conn = sqlite3.connect(str(ST_DB), timeout=10)
            live_rows = conn.execute("SELECT COUNT(*) FROM st_records").fetchone()[0]
            conn.close()
        except Exception:
            pass

    if tombstone_exists and live_exists and live_rows > 0:
        checks.append(
            {
                "tier": "short_term_sqlite",
                "marker": str(TOMBSTONE),
                "marker_exists": True,
                "consumer_path": str(ST_DB),
                "consumer_alive": True,
                "consumer_rows": live_rows,
                "consistent": False,
                "detail": "tombstone exists but live DB has data (marker is stale)",
            }
        )
        mismatch = True
    elif not tombstone_exists and live_exists and live_rows > 0:
        checks.append(
            {
                "tier": "short_term_sqlite",
                "marker": str(TOMBSTONE),
                "marker_exists": False,
                "consumer_path": str(ST_DB),
                "consumer_alive": True,
                "consumer_rows": live_rows,
                "consistent": True,
                "detail": "no tombstone, live DB has data",
            }
        )
    elif tombstone_exists and (not live_exists or live_rows == 0):
        checks.append(
            {
                "tier": "short_term_sqlite",
                "marker": str(TOMBSTONE),
                "marker_exists": True,
                "consumer_path": str(ST_DB),
                "consumer_alive": False,
                "consistent": True,
                "detail": "tombstone present, live DB absent/empty (consistent)",
            }
        )
    else:
        checks.append(
            {
                "tier": "short_term_sqlite",
                "marker": str(TOMBSTONE),
                "marker_exists": False,
                "consumer_path": str(ST_DB),
                "consumer_alive": live_exists,
                "consistent": True,
                "detail": "no tombstone, DB status: "
                + ("alive" if live_exists else "absent"),
            }
        )

    # Optional Pinecone marker: env present vs index ready
    if _pinecone_configured():
        pine_status, pine_detail = check_pinecone_connectivity()
        ready = pine_status == "GREEN"
        checks.append(
            {
                "tier": "pinecone",
                "marker": "PINECONE_API_KEY",
                "marker_exists": True,
                "consumer_alive": ready,
                "consistent": True,
                "detail": pine_detail,
            }
        )
    else:
        checks.append(
            {
                "tier": "pinecone",
                "marker": "PINECONE_API_KEY",
                "marker_exists": False,
                "consumer_alive": False,
                "consistent": True,
                "detail": "not configured (optional)",
            }
        )

    if _neo4j_configured():
        graph_status, graph_detail = check_graph()
        checks.append(
            {
                "tier": "neo4j",
                "marker": "NEO4J_* env",
                "marker_exists": True,
                "consumer_alive": graph_status == "GREEN",
                "consistent": True,
                "detail": graph_detail,
            }
        )
    else:
        checks.append(
            {
                "tier": "neo4j",
                "marker": "NEO4J_* env",
                "marker_exists": False,
                "consumer_alive": False,
                "consistent": True,
                "detail": "not configured (optional)",
            }
        )

    if mismatch:
        status = "RED"
        detail = (
            f"marker-vs-live: "
            f"{sum(1 for c in checks if not c.get('consistent', True))} mismatch(es)"
        )
    else:
        status = "GREEN"
        detail = "marker-vs-live: all consistent"

    return status, detail, checks


# ── Gate decision ───────────────────────────────────────────────────────────

def compute_gate_status(tiers: dict[str, dict[str, Any]]) -> tuple[str, int, bool]:
    """Compute overall gate status for a public (optional-backend) install.

    ST-only installs can be HEALTHY. Optional backends that are SKIPPED do not
    demote the gate. Configured-but-unhealthy optional backends demote to
    DEGRADED. Behavioral RED only applies when a suite is present and fails.
    """
    st = tiers.get("short_term_fts", {}).get("status", "RED")
    fts_consistency = tiers.get("short_term_fts_consistency", {}).get("status", "SKIPPED")
    graph = tiers.get("graph", {}).get("status", "SKIPPED")
    pinecone = tiers.get("pinecone_connectivity", {}).get("status", "SKIPPED")
    semantic = tiers.get("semantic_retrieval", {}).get("status", "SKIPPED")
    behavioral = tiers.get("behavioral_contracts", {}).get("status", "SKIPPED")
    golden = tiers.get("golden_retrieval", {}).get("status", "SKIPPED")

    if st != "GREEN":
        return "CRITICAL", 2, False

    if fts_consistency in ("YELLOW", "RED"):
        return "DEGRADED", 1, False

    if behavioral == "RED":
        return "CRITICAL", 2, False

    # Fallback is active when semantic is not cleanly green (including SKIPPED).
    fallback_active = semantic in ("YELLOW", "SKIPPED", "RED")

    optional_configured_bad = any(
        status in ("YELLOW", "RED")
        for status in (graph, pinecone, semantic)
    )

    if golden in ("DEGRADED", "RED"):
        return "DEGRADED", 1, fallback_active

    if optional_configured_bad:
        return "DEGRADED", 1, fallback_active

    # behavioral GREEN or SKIPPED, ST green, optionals green/skipped
    if behavioral in ("GREEN", "SKIPPED"):
        return "HEALTHY", 0, fallback_active if semantic != "GREEN" else False

    return "DEGRADED", 1, fallback_active


# ── CLI / main ──────────────────────────────────────────────────────────────

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="memory-health-gate.py",
        description=(
            "Memory stack health gate for public Agent OS. "
            "Checks short-term FTS plus optional Pinecone/Neo4j backends."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exit codes:\n"
            "  0  HEALTHY\n"
            "  1  DEGRADED\n"
            "  2  CRITICAL / TIMEOUT\n"
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Pretty-print JSON output (default is compact single-line JSON)",
    )
    parser.add_argument(
        "--golden",
        action="store_true",
        help="Run optional golden retrieval canaries (slower)",
    )
    parser.add_argument(
        "--read-only",
        action="store_true",
        help="Do not self-heal FTS orphans; report drift only",
    )
    parser.add_argument(
        "--check-consistency",
        action="store_true",
        help="Run only marker-vs-live consistency check, then exit",
    )
    parser.add_argument(
        "--live-export",
        action="store_true",
        help=argparse.SUPPRESS,  # accepted no-op for private-script CLI compatibility
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    if args.check_consistency:
        status, detail, checks = check_marker_vs_live()
        output = {
            "check": "marker-vs-live-consistency",
            "status": status,
            "detail": detail,
            "checks": checks,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "agent_os_home": str(AGENT_OS_HOME),
        }
        print(json.dumps(output, indent=2 if args.json else None))
        sys.exit(0 if status == "GREEN" else 1)

    tiers: dict[str, dict[str, Any]] = {
        "short_term_fts": {"status": "CHECKING", "detail": ""},
        "short_term_fts_consistency": {"status": "CHECKING", "detail": ""},
        "graph": {"status": "CHECKING", "detail": ""},
        "pinecone_connectivity": {"status": "CHECKING", "detail": ""},
        "semantic_retrieval": {"status": "CHECKING", "detail": ""},
        "behavioral_contracts": {"status": "CHECKING", "detail": ""},
        "golden_retrieval": {
            "status": "SKIPPED",
            "detail": "not requested (pass --golden to run)",
        },
    }

    st_status, st_detail = check_st_fts()
    tiers["short_term_fts"] = {"status": st_status, "detail": st_detail}

    cons_status, cons_detail = check_st_fts_consistency(read_only=args.read_only)
    tiers["short_term_fts_consistency"] = {
        "status": cons_status,
        "detail": cons_detail,
    }

    graph_status, graph_detail = check_graph()
    tiers["graph"] = {"status": graph_status, "detail": graph_detail}

    pine_status, pine_detail = check_pinecone_connectivity()
    tiers["pinecone_connectivity"] = {"status": pine_status, "detail": pine_detail}

    sem_status, sem_detail = check_semantic_retrieval()
    tiers["semantic_retrieval"] = {"status": sem_status, "detail": sem_detail}

    beh_status, beh_detail = check_behavioral_contracts()
    tiers["behavioral_contracts"] = {"status": beh_status, "detail": beh_detail}

    if args.golden:
        g_status, g_detail, g_queries = check_golden_retrieval()
        g_skipped = sum(1 for q in g_queries if q.get("skipped"))
        tiers["golden_retrieval"] = {
            "status": g_status,
            "detail": g_detail,
            "hits": sum(1 for q in g_queries if q.get("hit")),
            "total": len(GOLDEN_QUERIES) - g_skipped,
            "skipped": g_skipped,
            "queries": g_queries,
        }

    overall, exit_code, fallback_active = compute_gate_status(tiers)

    lc_status, lc_detail, lc_metrics = check_lifecycle_metrics()
    if lc_status == "RED" and overall == "HEALTHY":
        overall = "DEGRADED"
        exit_code = 1

    mv_status, mv_detail, mv_checks = check_marker_vs_live()
    if mv_status == "RED" and overall == "HEALTHY":
        overall = "DEGRADED"
        exit_code = 1

    rerank_capacity = "CAPACITY_LIMITED" if fallback_active else "AVAILABLE"
    output = {
        "gate": "memory-health-gate",
        "version": "2.0.0-oss",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "agent_os_home": str(AGENT_OS_HOME),
        "tiers": tiers,
        "overall": overall,
        "fallback_active": fallback_active,
        "exit_code": exit_code,
        "lifecycle": {
            "status": lc_status,
            "detail": lc_detail,
            "metrics": lc_metrics,
        },
        "marker_vs_live": {
            "status": mv_status,
            "detail": mv_detail,
            "checks": mv_checks,
        },
        "snapshot": {
            "connectivity": {
                "st_fts": tiers["short_term_fts"]["status"],
                "pinecone": tiers["pinecone_connectivity"]["status"],
                "neo4j": tiers["graph"]["status"],
            },
            "capacity": {
                "rerank": rerank_capacity,
                "semantic_search": tiers["semantic_retrieval"]["status"],
            },
            "integrity": {
                "marker_vs_live": mv_status,
                "fts_consistency": tiers["short_term_fts_consistency"]["status"],
            },
            "quality": {
                "golden_retrieval": tiers.get("golden_retrieval", {}).get(
                    "status", "SKIPPED"
                ),
                "fallback_active": fallback_active,
                "behavioral_contracts": tiers["behavioral_contracts"]["status"],
            },
        },
        "mode": {
            "read_only": args.read_only,
            "golden": args.golden,
        },
        "notes": [
            "Optional backends (Pinecone, Neo4j) are SKIPPED when env is unset.",
            "Private runtime bridges are out of scope for this gate.",
        ],
    }

    if args.json:
        print(json.dumps(output, indent=2))
    else:
        print(json.dumps(output, separators=(",", ":")))

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
