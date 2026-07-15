#!/usr/bin/env python3
"""
quality-gates.py — WP3 Rule-based Quality Checks for Agent OS.

Three independent quality gates that verify:
  1. Stale file references — are stumbles referencing deleted files?
  2. Contradictions — do active stumbles contradict resolved ones?
  3. Completion — are promoted stumbles missing corresponding decisions?

Usage:
  python3 quality-gates.py                        # Run all checks, human-readable
  python3 quality-gates.py --check stale           # Run specific check
  python3 quality-gates.py --json                  # JSON output
  python3 quality-gates.py --compact               # Compact one-line-per-check (for cron)
  python3 quality-gates.py --help                  # Show this help

Exit code: 0 if all PASS, 1 if any FAIL, 0 if only WARN.

Environment:
  AGENT_OS_HOME    Install root (defaults to parent of scripts/)
  AGENT_OS_ST_DB   Override short-term SQLite path (preferred)
  ST_DB            Legacy override for short-term SQLite path
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
from pathlib import Path

# Allow `from stumble_contract import ...` when invoked as a script path.
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from stumble_contract import VALID_DECISIONS

# ── Paths ─────────────────────────────────────────────────────────────────────

_SCRIPT_PATH = Path(__file__).resolve()
AGENT_OS_HOME = Path(
    os.environ.get("AGENT_OS_HOME") or str(_SCRIPT_PATH.parent.parent)
).resolve()
os.environ.setdefault("AGENT_OS_HOME", str(AGENT_OS_HOME))

_DEFAULT_ST_DB = str(
    Path.home() / ".local" / "state" / "agent-os" / "memory" / "short_term.sqlite"
)
ST_DB = Path(
    os.path.expanduser(
        os.environ.get("AGENT_OS_ST_DB")
        or os.environ.get("ST_DB")
        or _DEFAULT_ST_DB
    )
)

# ── Helpers ───────────────────────────────────────────────────────────────────

PASS = "PASS"
FAIL = "FAIL"
WARN = "WARN"


def get_conn() -> sqlite3.Connection:
    """Open a connection to the short-term memory database."""
    if not ST_DB.is_file():
        raise FileNotFoundError(f"Short-term memory DB not found: {ST_DB}")
    conn = sqlite3.connect(str(ST_DB))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    """Check if a table exists in the database."""
    try:
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (name,),
        )
        return cur.fetchone() is not None
    except sqlite3.Error:
        return False


def get_st_records(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Fetch all stumble records."""
    if not table_exists(conn, "st_records"):
        return []
    return conn.execute(
        "SELECT id, run_id, content, summary, source_ref, intent, kind, "
        "status, promote_state, fingerprint, created_at "
        "FROM st_records"
    ).fetchall()


def path_patterns(text: str) -> list[str]:
    """Extract plausible file path patterns from text.

    Matches:
      - Absolute paths starting with / (filtered further to avoid URLs)
      - ~/ prefixed paths (home-relative)
      - /tmp/ paths

    Skips URL-like patterns and obvious non-file references.
    """
    if not text:
        return []

    found: set[str] = set()

    # Match absolute paths: /something/... (but not http://, git@, etc.)
    for m in re.finditer(
        r"(?<!\w)(/[\w./\-_~]+(?:/[\w.\-_:~]+)+/?)(?!\w)",
        text,
    ):
        candidate = m.group(1)
        # Strip trailing sentence punctuation (e.g. "roles.toml:" in prose)
        # that the path regex captures but is not part of the filename.
        candidate = re.sub(r"[.:,;]+$", "", candidate)
        if _is_plausible_file_path(candidate):
            found.add(candidate)

    # Match ~/ prefixed paths
    for m in re.finditer(
        r"(?<!\w)(~/(?:[\w.\-_:~]+/)*[\w.\-_:~]+)(?!\w)",
        text,
    ):
        candidate = m.group(1)
        # Strip trailing sentence punctuation (e.g. "roles.toml:" in prose)
        # that the path regex captures but is not part of the filename.
        candidate = re.sub(r"[.:,;]+$", "", candidate)
        if _is_plausible_file_path(candidate):
            found.add(candidate)

    # Match /tmp/... specifically
    for m in re.finditer(
        r"(?<!\w)(/tmp/[\w.\-_:~/]+)(?!\w)",
        text,
    ):
        candidate = m.group(1)
        # Strip trailing sentence punctuation (e.g. "roles.toml:" in prose)
        # that the path regex captures but is not part of the filename.
        candidate = re.sub(r"[.:,;]+$", "", candidate)
        if _is_plausible_file_path(candidate):
            found.add(candidate)

    return sorted(found)


def _is_plausible_file_path(path: str) -> bool:
    """Filter out URLs, git refs, and other non-file references."""
    # Skip obvious URLs
    if re.match(r'^(https?://|git@|ssh://|ftp://)', path):
        return False
    # Skip paths that look like git refs (e.g., origin/main, refs/heads/...)
    if re.match(r'^(refs/|origin/|upstream/)', path):
        return False
    # Skip paths with common URL extensions that appear in logs
    if re.match(r'.*\.(com|org|net|io|dev|app|ai)/', path):
        # Could be a URL without scheme; check more aggressively
        if re.match(r'^[\w-]+\.(com|org|net|io|dev|app|ai)/', path):
            return False
    # Skip email-like strings
    if '@' in path:
        return False
    # Skip very short paths (less than 3 chars beyond leading / or ~/)
    stripped = path.lstrip('/~')
    if len(stripped) < 3:
        return False
    # Skip paths that are clearly command-line flags
    if path.startswith('/') and not path.startswith(
        ('/home/', '/tmp/', '/etc/', '/usr/', '/var/', '/opt/', '/bin/', '/sbin/', '/run/')
    ):
        return False
    return True


def resolve_path(path: str) -> Path | None:
    """Resolve a path string to an absolute Path, handling ~ prefix."""
    try:
        path = re.sub(r":\d+(?:-\d+)?$", "", path)
        resolved = Path(path).expanduser().resolve()
        return resolved
    except (OSError, RuntimeError):
        return None


# ── Check 1: Stale file references ──────────────────────────────────────────

def check_stale_file_refs(conn: sqlite3.Connection) -> dict:
    """Check stumbles for references to files that no longer exist."""
    records = get_st_records(conn)

    if not records:
        return {
            "check_name": "stale_file_refs",
            "status": WARN,
            "detail": "No stumble records to scan",
            "items": [],
        }

    stale_refs: list[dict] = []
    paths_checked = 0
    max_checks = 500  # Performance limit

    for row in records:
        if paths_checked >= max_checks:
            break

        # Only check STUMBLE records — LESSON and OBSERVATION records
        # contain incidental path mentions in command output and JSON
        # data that aren't actionable stale references.
        # Also skip resolved and discarded stumbles — the issue was already handled.
        intent = (row["intent"] or "").upper()
        status = (row["status"] or "").lower()
        if intent != "STUMBLE" or status in ("resolved", "discarded"):
            continue

        content = row["content"] or ""
        source_ref = row["source_ref"] or ""
        summary = row["summary"] or ""

        combined = f"{summary} {source_ref}"
        if content:
            combined += " " + content
        paths = path_patterns(combined)

        for p in paths:
            if paths_checked >= max_checks:
                break
            paths_checked += 1

            resolved = resolve_path(p)
            if resolved is None:
                continue

            exists = resolved.exists()
            if not exists:
                stale_refs.append({
                    "stumble_id": row["id"],
                    "summary": (summary or "")[:120],
                    "stale_path": p,
                    "resolved_path": str(resolved),
                })

    # Deduplicate by (stumble_id, stale_path)
    seen = set()
    deduped = []
    for item in stale_refs:
        key = (item["stumble_id"], item["stale_path"])
        if key not in seen:
            seen.add(key)
            deduped.append(item)

    total_checked = paths_checked
    status = PASS
    detail = f"No stale file references found (checked {total_checked} path(s))"
    if deduped:
        status = FAIL
        detail = f"{len(deduped)} stale file reference(s) found (checked {total_checked} path(s))"

    return {
        "check_name": "stale_file_refs",
        "status": status,
        "detail": detail,
        "items": deduped,
    }


# ── Check 2: Contradictions ────────────────────────────────────────────────

def _similarity_key(summary: str) -> str:
    """Normalize a summary for similarity comparison."""
    if not summary:
        return ""
    s = summary.lower().strip()
    # Remove punctuation and extra whitespace
    s = re.sub(r'[^\w\s]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    # Extract key tokens (remove common noise words)
    stop_words = {
        'a', 'an', 'the', 'in', 'on', 'at', 'to', 'for', 'of', 'with',
        'by', 'from', 'is', 'was', 'are', 'were', 'be', 'been', 'being',
        'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
        'could', 'should', 'may', 'might', 'this', 'that', 'these', 'those',
        'it', 'its', 'and', 'or', 'but', 'not', 'no', 'if', 'then', 'else',
    }
    words = [w for w in s.split() if w not in stop_words and len(w) > 2]
    return ' '.join(words)


def _status_is_resolved(status: str) -> bool:
    """Check if a status value indicates resolution."""
    resolved_indicators = {'resolved', 'closed', 'done', 'fixed', 'completed', 'inactive'}
    return status.lower().strip() in resolved_indicators


def _status_is_open(status: str) -> bool:
    """Check if a status value indicates an open/active state."""
    open_indicators = {'open', 'active', 'new', 'pending', 'unresolved', 'in_progress'}
    return status.lower().strip() in open_indicators


def check_contradictions(conn: sqlite3.Connection) -> dict:
    """Find pairs of stumbles that contradict each other."""
    records = get_st_records(conn)

    if not records:
        return {
            "check_name": "contradictions",
            "status": WARN,
            "detail": "No stumble records to check for contradictions",
            "items": [],
        }

    contradictions: list[dict] = []

    # Strategy 1: Use semantic cluster members if available
    has_clusters = table_exists(conn, "st_semantic_cluster_members")
    if has_clusters:
        try:
            cluster_rows = conn.execute(
                """SELECT m.cluster_id, m.st_record_id, m.similarity_score,
                          r1.summary AS sum_a, r1.status AS status_a,
                          r1.intent AS intent_a
                   FROM st_semantic_cluster_members m
                   JOIN st_records r1 ON r1.id = m.st_record_id
                   WHERE m.cluster_id IN (
                       SELECT DISTINCT cluster_id FROM st_semantic_cluster_members
                       GROUP BY cluster_id
                       HAVING COUNT(*) >= 2
                   )
                """
            ).fetchall()

            # Group by cluster_id
            cluster_map: dict[str, list[dict]] = {}
            for row in cluster_rows:
                cid = row["cluster_id"]
                if cid not in cluster_map:
                    cluster_map[cid] = []
                cluster_map[cid].append(dict(row))

            for cid, members in cluster_map.items():
                for i in range(len(members)):
                    for j in range(i + 1, len(members)):
                        a, b = members[i], members[j]
                        if _status_is_resolved(a.get("status_a", "")) and _status_is_open(b.get("status_a", "")):
                            contradictions.append({
                                "record_a_id": a["st_record_id"],
                                "record_b_id": b["st_record_id"],
                                "similarity": a.get("similarity_score", 0),
                                "conflict_type": "status_contradiction",
                                "detail": f"'{a.get('sum_a','')[:60]}' vs '{b.get('sum_a','')[:60]}' "
                                          f"(status: {a.get('status_a')} vs {b.get('status_a')})",
                            })
                        elif _status_is_resolved(b.get("status_a", "")) and _status_is_open(a.get("status_a", "")):
                            contradictions.append({
                                "record_a_id": a["st_record_id"],
                                "record_b_id": b["st_record_id"],
                                "similarity": a.get("similarity_score", 0),
                                "conflict_type": "status_contradiction",
                                "detail": f"'{a.get('sum_a','')[:60]}' vs '{b.get('sum_a','')[:60]}' "
                                          f"(status: {a.get('status_a')} vs {b.get('status_a')})",
                            })
        except sqlite3.Error:
            pass  # Fall through to heuristic approach below

    # Strategy 2: Heuristic - find records with similar summaries and opposite statuses
    # Group records by normalized summary and check for contradictions
    summary_groups: dict[str, list[sqlite3.Row]] = {}
    for row in records:
        key = _similarity_key(row["summary"] or "")
        if not key:
            continue
        # Only group if the summary has enough meaningful content
        words = key.split()
        if len(words) < 2:
            continue
        # Use first 5 words as the grouping key for broad similarity
        group_key = ' '.join(words[:5])
        if group_key not in summary_groups:
            summary_groups[group_key] = []
        summary_groups[group_key].append(row)

    for group_key, group in summary_groups.items():
        if len(group) < 2:
            continue
        # Look for pairs with conflicting statuses
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = group[i], group[j]
                a_resolved = _status_is_resolved(a["status"])
                a_open = _status_is_open(a["status"])
                b_resolved = _status_is_resolved(b["status"])
                b_open = _status_is_open(b["status"])

                if (a_resolved and b_open) or (b_resolved and a_open):
                    # Avoid duplicates from both methods
                    pair_key = tuple(sorted([a["id"], b["id"]]))
                    already_found = any(
                        (item["record_a_id"], item["record_b_id"]) == pair_key or
                        (item["record_b_id"], item["record_a_id"]) == pair_key
                        for item in contradictions
                    )
                    if not already_found:
                        contradictions.append({
                            "record_a_id": a["id"],
                            "record_b_id": b["id"],
                            "similarity": 0.0,  # Heuristic match, no score
                            "conflict_type": "status_contradiction",
                            "detail": f"'{a['summary'][:60]}' (status: {a['status']}) vs "
                                      f"'{b['summary'][:60]}' (status: {b['status']})",
                        })

    # (intent-based contradiction detection reserved for future expansion)

    status = PASS
    detail = "No contradictions found"
    if contradictions:
        status = FAIL
        detail = f"{len(contradictions)} contradiction(s) found"

    return {
        "check_name": "contradictions",
        "status": status,
        "detail": detail,
        "items": contradictions,
    }


# ── Check 3: Completion ────────────────────────────────────────────────────

def check_completion(conn: sqlite3.Connection) -> dict:
    """Find stumbles with promoted state but no matching decision."""
    records = get_st_records(conn)

    if not records:
        return {
            "check_name": "completion",
            "status": WARN,
            "detail": "No stumble records to check for completion",
            "items": [],
        }

    incomplete: list[dict] = []

    # Check if st_decisions table exists
    has_decisions = table_exists(conn, "st_decisions")

    # Get all decision fingerprints for fast lookup
    decision_fingerprints: set[str] = set()
    if has_decisions:
        try:
            placeholders = ", ".join("?" for _ in VALID_DECISIONS)
            decision_rows = conn.execute(
                f"SELECT fingerprint FROM st_decisions WHERE decision IN ({placeholders})",
                VALID_DECISIONS,
            ).fetchall()
            decision_fingerprints = {r["fingerprint"] for r in decision_rows}
        except sqlite3.Error:
            pass

    # Find stumbles with promote_state != 'none' but no matching decision
    # LESSON intents are excluded — they're durable learnings, not issues needing resolution
    for row in records:
        intent = (row["intent"] or "").upper()
        if intent == "LESSON":
            continue
        promote_state = row["promote_state"] or "none"
        fingerprint = row["fingerprint"]

        # Only "promoted" stumbles need a recorded triage decision.
        # "rejected" is itself a conscious decision and must not be
        # flagged as missing one (it inflates the completion gap).
        if promote_state.lower() == "promoted" and fingerprint:
            if fingerprint not in decision_fingerprints:
                incomplete.append({
                    "stumble_id": row["id"],
                    "summary": (row["summary"] or "")[:120],
                    "fingerprint": fingerprint,
                    "promote_state": promote_state,
                    "missing_decision": True,
                })

    # Also check: stumbles with intent=STUMBLE that have resolved status but no decision
    for row in records:
        intent = (row["intent"] or "").upper()
        status = (row["status"] or "").lower()
        fingerprint = row["fingerprint"]

        if intent == "STUMBLE" and _status_is_resolved(status) and fingerprint:
            if fingerprint not in decision_fingerprints:
                # Already captured above if promote_state was set
                existing_ids = {item["stumble_id"] for item in incomplete}
                if row["id"] not in existing_ids:
                    incomplete.append({
                        "stumble_id": row["id"],
                        "summary": (row["summary"] or "")[:120],
                        "fingerprint": fingerprint,
                        "promote_state": row["promote_state"] or "none",
                        "missing_decision": True,
                    })

    # Check session_telemetry for unresolved failures (if table exists)
    telemetry_incomplete: list[dict] = []
    if table_exists(conn, "session_telemetry"):
        try:
            # Find tool failures that have no corresponding success
            telemetry_fails = conn.execute(
                """SELECT id, session_id, tool_name, workspace, intent,
                          error_message, created_at
                   FROM session_telemetry
                   WHERE success = 0
                   ORDER BY created_at DESC
                   LIMIT 100
                """
            ).fetchall()

            for fail_row in telemetry_fails:
                session_id = fail_row["session_id"]
                # Check if there's a corresponding success or resolution
                # (A later successful call to the same tool in the same session)
                has_success = conn.execute(
                    """SELECT COUNT(*) as cnt FROM session_telemetry
                       WHERE session_id = ?
                         AND tool_name = ?
                         AND success = 1
                         AND created_at > ?
                    """,
                    (session_id, fail_row["tool_name"], fail_row["created_at"]),
                ).fetchone()["cnt"]

                if has_success == 0:
                    telemetry_incomplete.append({
                        "session_id": session_id,
                        "tool_name": fail_row["tool_name"],
                        "error_message": (fail_row["error_message"] or "")[:120],
                        "created_at": fail_row["created_at"],
                    })
        except sqlite3.Error:
            pass

    total_items = len(incomplete) + len(telemetry_incomplete)

    # Merge telemetry items into the main items list
    all_items = incomplete[:]
    for ti in telemetry_incomplete[:10]:  # Limit to avoid noise
        all_items.append({
            "stumble_id": f"telemetry:{ti['session_id']}:{ti['tool_name']}",
            "summary": f"Unresolved tool failure: {ti['tool_name']} - {ti['error_message'][:80]}",
            "fingerprint": "",
            "missing_decision": True,
            "source": "session_telemetry",
        })

    status = PASS
    detail = "All promoted stumbles have corresponding decisions"
    if all_items:
        # Check if any are real decisions missing vs just telemetry noise
        real_missing = [i for i in all_items if i.get("missing_decision") and i.get("fingerprint")]
        if real_missing:
            status = FAIL
        else:
            status = WARN  # Only telemetry failures with no resolution
        detail = f"{len(all_items)} incomplete resolution(s) found (promoted with no decision)"

    return {
        "check_name": "completion",
        "status": status,
        "detail": detail,
        "items": all_items,
    }


# ── CLI ──────────────────────────────────────────────────────────────────────

def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Run quality checks on agent OS data.",
    )
    p.add_argument(
        "--check",
        choices=["stale", "contradictions", "completion", "all"],
        default="all",
        help="Run a specific quality check (default: all)",
    )
    p.add_argument("--json", action="store_true", help="Output as JSON")
    p.add_argument(
        "--compact",
        action="store_true",
        help="Compact one-line-per-check output (for cron)",
    )
    return p.parse_args(argv)


def run_checks(conn: sqlite3.Connection, checks: list[str]) -> dict[str, dict]:
    """Run specified checks and return results."""
    results: dict[str, dict] = {}

    check_map = {
        "stale": ("stale_file_refs", check_stale_file_refs),
        "contradictions": ("contradictions", check_contradictions),
        "completion": ("completion", check_completion),
    }

    for name, (check_name, func) in check_map.items():
        if "all" in checks or name in checks:
            try:
                results[check_name] = func(conn)
            except Exception as e:
                results[check_name] = {
                    "check_name": check_name,
                    "status": WARN,
                    "detail": f"Check error: {e}",
                    "items": [],
                }

    return results


def compute_overall(results: dict[str, dict]) -> str:
    """Compute overall status from individual check results."""
    has_fail = any(r.get("status") == FAIL for r in results.values())
    if has_fail:
        return FAIL
    return PASS


def print_human(results: dict[str, dict]) -> None:
    """Print human-readable output."""
    for check_name, result in results.items():
        status = result.get("status", "ERROR")
        detail = result.get("detail", "")
        icon = {"PASS": "✓", "FAIL": "✗", "WARN": "⚠", "ERROR": "?"}.get(status, "?")
        print(f"  {icon} [{status}] {check_name}: {detail}")
        for item in result.get("items", []):
            print(f"    - {json.dumps(item)[:140]}")
        print()


def print_compact(results: dict[str, dict]) -> None:
    """Print compact one-line-per-check output (for cron)."""
    overall = compute_overall(results)
    parts = [f"OVERALL={overall}"]
    for check_name, result in results.items():
        status = result.get("status", "ERROR")
        n = len(result.get("items", []))
        parts.append(f"{check_name}={status}({n})")
    print(" | ".join(parts))


def main() -> None:
    args = parse_args(sys.argv[1:])

    checks = ["stale", "contradictions", "completion"] if args.check == "all" else [args.check]

    try:
        conn = get_conn()
    except FileNotFoundError as e:
        result = {
            "overall": WARN,
            "checks": {},
            "error": str(e),
        }
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"⚠ [WARN] Database not found: {e}")
        sys.exit(0)

    try:
        results = run_checks(conn, checks)
        overall = compute_overall(results)

        if args.json:
            output = {
                "overall": overall,
                "checks": results,
            }
            print(json.dumps(output, indent=2))
        elif args.compact:
            print_compact(results)
        else:
            print(f"Quality gates: {overall}")
            print()
            print_human(results)

        # Exit code: 0 if all PASS, 1 if any FAIL, 0 if only WARN
        if overall == FAIL:
            sys.exit(1)
        sys.exit(0)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
