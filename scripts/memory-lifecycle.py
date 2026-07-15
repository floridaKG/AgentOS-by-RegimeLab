#!/usr/bin/env python3
"""memory-lifecycle.py — Cross-tier stale detection and lifecycle management.

Subcommands:
  detect-stale   Report-only stale candidates across all memory tiers.
  consolidate    Find cross-tier similar entries and propose merges.
  ttl-report     Report TTL adjustment recommendations (never mutates config).

Each tier has a pluggable scanner class with scan() -> list of candidates.
Candidates are scored and ranked by staleness. detect-stale NEVER deletes.

Exit codes:
  0 — success (stale candidates may be present)
  1 — error

Environment:
  AGENT_OS_HOME              Install root (defaults to parent of scripts/)
  AGENT_OS_ST_DB / ST_DB     Short-term SQLite path
  AGENT_OS_STATE_DIR         State/log root (default: ~/.local/state/agent-os)
  AGENT_OS_MEMORY_MD         Optional MEMORY.md path for filesystem tier
  HINDSIGHT_API_URL          Optional Hindsight API base (default 127.0.0.1:9177)
  HINDSIGHT_BANK             Optional bank id; Hindsight scan skipped if unset
  LIFECYCLE_DELETE_ENABLED   Set to 1 to archive consolidation proposals (still
                             does not hard-delete tier data)
  MEMORY_LT_BIN              Override path to memory-lt facade
  MEMORY_NEO4J_BIN           Override path to optional neo4j prune CLI
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# ── Paths / env ─────────────────────────────────────────────────────────────

_SCRIPT_PATH = Path(__file__).resolve()
AGENT_OS_HOME = Path(
    os.environ.get("AGENT_OS_HOME") or str(_SCRIPT_PATH.parent.parent)
).resolve()
os.environ.setdefault("AGENT_OS_HOME", str(AGENT_OS_HOME))

STATE_DIR = Path(
    os.path.expanduser(
        os.environ.get(
            "AGENT_OS_STATE_DIR",
            str(Path.home() / ".local" / "state" / "agent-os"),
        )
    )
)

_DEFAULT_ST_DB = str(STATE_DIR / "memory" / "short_term.sqlite")
ST_DB = Path(
    os.path.expanduser(
        os.environ.get("AGENT_OS_ST_DB")
        or os.environ.get("ST_DB")
        or _DEFAULT_ST_DB
    )
)

MEMORY_LT = Path(
    os.environ.get("MEMORY_LT_BIN")
    or str(AGENT_OS_HOME / "bin" / "memory-lt")
)
# Optional private-style neo4j prune CLI; not required for OSS open-core.
MEMORY_NEO4J = Path(
    os.environ.get("MEMORY_NEO4J_BIN")
    or str(AGENT_OS_HOME / "bin" / "memory-neo4j")
)
HEALTH_GATE = AGENT_OS_HOME / "scripts" / "memory-health-gate.py"

HINDSIGHT_API_URL = os.environ.get("HINDSIGHT_API_URL", "http://127.0.0.1:9177").rstrip("/")
HINDSIGHT_BANK = os.environ.get("HINDSIGHT_BANK", "").strip()


# ── Base Scanner Interface ─────────────────────────────────────────────────

class StaleCandidate:
    """A single stale item detected by a tier scanner."""

    def __init__(
        self,
        tier: str,
        item_id: str,
        summary: str,
        age_days: float,
        score: float = 0.0,
        metadata: dict | None = None,
    ):
        self.tier = tier
        self.item_id = item_id
        self.summary = summary[:200]
        self.age_days = age_days
        self.score = score
        self.metadata = metadata or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "tier": self.tier,
            "id": self.item_id,
            "summary": self.summary,
            "age_days": round(self.age_days, 1),
            "score": round(self.score, 3),
            "metadata": self.metadata,
        }


class TierScanner:
    """Base class for tier scanners."""

    tier_name: str = "unknown"

    def scan(self) -> list[StaleCandidate]:
        """Return list of stale candidates. Must not raise."""
        return []

    def _score_age(self, age_days: float) -> float:
        """Score staleness by age (0= fresh, 1= very stale)."""
        if age_days < 7:
            return 0.0
        elif age_days < 30:
            return 0.3
        elif age_days < 90:
            return 0.6
        elif age_days < 180:
            return 0.8
        else:
            return 1.0


# ── Tier Scanners ──────────────────────────────────────────────────────────

class ShortTermScanner(TierScanner):
    """Scan short-term SQLite for old records."""

    tier_name = "short_term"

    def scan(self) -> list[StaleCandidate]:
        db_path = ST_DB
        if not db_path.is_file():
            return []

        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            # Query records older than 30 days with no recent access
            cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
            rows = conn.execute(
                "SELECT id, summary, created_at, updated_at "
                "FROM st_records WHERE created_at < ? "
                "ORDER BY created_at LIMIT 100",
                (cutoff,),
            ).fetchall()
            conn.close()

            candidates = []
            now = datetime.now(timezone.utc)
            for row in rows:
                try:
                    created = datetime.fromisoformat(
                        row["created_at"].replace("Z", "+00:00")
                    )
                    age = (now - created).total_seconds() / 86400
                except (ValueError, TypeError, AttributeError):
                    age = 999

                score = self._score_age(age)
                candidates.append(
                    StaleCandidate(
                        tier=self.tier_name,
                        item_id=str(row["id"]),
                        summary=row["summary"] or "",
                        age_days=age,
                        score=score,
                        metadata={"created_at": row["created_at"]},
                    )
                )
            return candidates
        except Exception:
            return []


class HindsightScanner(TierScanner):
    """Scan Hindsight facts for old items via the daemon API (optional)."""

    tier_name = "hindsight"

    def scan(self) -> list[StaleCandidate]:
        if not HINDSIGHT_BANK:
            return []
        try:
            list_url = (
                f"{HINDSIGHT_API_URL}/v1/default/banks/"
                f"{HINDSIGHT_BANK}/memories/list?limit=500"
            )
            result = subprocess.run(
                ["curl", "-s", "-m", "5", list_url],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                return []
            data = json.loads(result.stdout)
            items = data.get("items", [])

            candidates = []
            now = datetime.now(timezone.utc)
            for item in items:
                mentioned = item.get("mentioned_at") or item.get("date")
                if not mentioned:
                    continue
                try:
                    dt = datetime.fromisoformat(mentioned.replace("Z", "+00:00"))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    age = (now - dt).total_seconds() / 86400
                except (ValueError, TypeError):
                    continue

                if age > 30:
                    score = self._score_age(age)
                    candidates.append(
                        StaleCandidate(
                            tier=self.tier_name,
                            item_id=item.get("id", "unknown"),
                            summary=item.get("text", "")[:200],
                            age_days=age,
                            score=score,
                            metadata={"fact_type": item.get("fact_type")},
                        )
                    )
            return candidates
        except Exception:
            return []


class PineconeScanner(TierScanner):
    """Scan Pinecone for vectors approaching TTL expiry (optional)."""

    tier_name = "pinecone"

    def scan(self) -> list[StaleCandidate]:
        # Pinecone doesn't expose creation timestamps directly via query.
        # Probe the public memory-lt facade (or long_term.py if present);
        # TTL-based pruning is handled elsewhere.
        if not os.environ.get("PINECONE_API_KEY"):
            return []

        probe_cmds: list[list[str]] = []
        if MEMORY_LT.is_file():
            # memory-lt has no dedicated health subcommand in OSS; a no-op
            # search-vector with empty text is not safe. Presence + key is
            # enough for the probe (original private path returned [] after
            # health). Fall through to empty candidate list.
            return []

        long_term = AGENT_OS_HOME / "memory" / "long_term.py"
        if long_term.is_file():
            probe_cmds.append([sys.executable, str(long_term), "health"])

        for cmd in probe_cmds:
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=20,
                )
                if result.returncode != 0:
                    return []
                data = json.loads(result.stdout)
                vector = data.get("vector", {})
                if vector.get("status") != "ready":
                    return []
            except Exception:
                return []

        # No direct TTL query available — return empty for now
        return []


class Neo4jScanner(TierScanner):
    """Scan Neo4j for orphan nodes (optional prune CLI)."""

    tier_name = "neo4j"

    def scan(self) -> list[StaleCandidate]:
        if not MEMORY_NEO4J.is_file():
            return []
        if any(not os.environ.get(k) for k in ("NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD")):
            return []
        try:
            result = subprocess.run(
                [sys.executable, str(MEMORY_NEO4J), "prune", "--orphans"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                return []
            data = json.loads(result.stdout)
            if not data.get("ok"):
                return []

            # Parse orphan data from the archive if available
            archive = data.get("archive")
            if archive and Path(archive).is_file():
                with open(archive) as f:
                    export = json.load(f)
                candidates = []
                for orphan in export.get("orphans", []):
                    created = orphan.get("created_at")
                    age = 999
                    if created:
                        try:
                            dt = datetime.fromisoformat(
                                str(created).replace("Z", "+00:00")
                            )
                            age = (
                                datetime.now(timezone.utc) - dt
                            ).total_seconds() / 86400
                        except (ValueError, TypeError):
                            pass
                    candidates.append(
                        StaleCandidate(
                            tier=self.tier_name,
                            item_id=orphan.get("id", "unknown"),
                            summary=f"orphan node: {orphan.get('labels', [])}",
                            age_days=age,
                            score=self._score_age(age),
                        )
                    )
                return candidates
            return []
        except Exception:
            return []


class MemoryMdScanner(TierScanner):
    """Scan MEMORY.md for old entries (by position — later = newer)."""

    tier_name = "memory_md"

    def scan(self) -> list[StaleCandidate]:
        env_path = os.environ.get("AGENT_OS_MEMORY_MD", "").strip()
        candidates_paths: list[Path] = []
        if env_path:
            candidates_paths.append(Path(os.path.expanduser(env_path)))
        candidates_paths.append(STATE_DIR / "memories" / "MEMORY.md")
        # Common optional adapter location (not owner-specific profile)
        candidates_paths.append(
            Path.home() / ".local" / "state" / "agent-os" / "memories" / "MEMORY.md"
        )

        mem_file = next((p for p in candidates_paths if p.is_file()), None)
        if mem_file is None:
            return []

        try:
            content = mem_file.read_text(encoding="utf-8")
            entries = [e.strip() for e in content.split("\n§\n") if e.strip()]
            if not entries:
                return []

            candidates = []
            for i, entry in enumerate(entries):
                # Score by position (earlier = older = more stale)
                position_frac = i / len(entries) if len(entries) > 0 else 0
                age_days = (1 - position_frac) * 90  # approximate
                score = self._score_age(age_days)

                # Short entries score higher (likely fragments)
                if len(entry) < 30:
                    score = min(score + 0.2, 1.0)

                candidates.append(
                    StaleCandidate(
                        tier=self.tier_name,
                        item_id=f"entry_{i}",
                        summary=entry[:200],
                        age_days=age_days,
                        score=score,
                        metadata={
                            "position": i,
                            "total": len(entries),
                            "path": str(mem_file),
                        },
                    )
                )
            return candidates
        except Exception:
            return []


# ── Detect-Stale Mode ──────────────────────────────────────────────────────

SCANNERS = [
    ShortTermScanner(),
    HindsightScanner(),
    PineconeScanner(),
    Neo4jScanner(),
    MemoryMdScanner(),
]


def cmd_detect_stale(args: argparse.Namespace) -> int:
    """Run all tier scanners and report ranked stale candidates."""
    all_candidates: list[StaleCandidate] = []
    tier_summary: dict[str, Any] = {}

    for scanner in SCANNERS:
        try:
            candidates = scanner.scan()
            all_candidates.extend(candidates)
            tier_summary[scanner.tier_name] = {
                "scanned": True,
                "stale_count": len(candidates),
            }
        except Exception as exc:
            tier_summary[scanner.tier_name] = {
                "scanned": False,
                "error": str(exc)[:100],
            }

    # Sort by score descending (most stale first)
    all_candidates.sort(key=lambda c: c.score, reverse=True)

    # Limit output
    limit = args.limit or 50
    output_candidates = [c.to_dict() for c in all_candidates[:limit]]

    result: dict[str, Any] = {
        "ok": True,
        "mode": "detect-stale",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_candidates": len(all_candidates),
        "returned": len(output_candidates),
        "tier_summary": tier_summary,
        "candidates": output_candidates,
    }

    # Write report to log file
    log_dir = STATE_DIR / "logs" / "memory" / "stale-detect"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{datetime.now().strftime('%Y%m%dT%H%M%S')}.json"
    with open(log_file, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    result["report_file"] = str(log_file)

    print(json.dumps(result, indent=2))
    return 0


# ── Consolidate Mode (gated by LIFECYCLE_DELETE_ENABLED) ───────────────────

CONSOLIDATION_THRESHOLD = 0.9
LIFECYCLE_DELETE_ENABLED = os.environ.get("LIFECYCLE_DELETE_ENABLED", "0") == "1"


def _jaccard_similarity(a: set, b: set) -> float:
    """Jaccard index between two sets."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _word_trigrams(text: str) -> set:
    """Extract word-level trigrams from text."""
    words = text.lower().split()
    if len(words) < 3:
        return set(words)
    return {" ".join(words[i : i + 3]) for i in range(len(words) - 2)}


def cmd_consolidate(args: argparse.Namespace) -> int:
    """Find cross-tier similar entries and propose merges.

    When LIFECYCLE_DELETE_ENABLED=0: report proposed merges only, mutate nothing.
    When ON: archive sources first, then mark CONSOLIDATED.
    """
    # Collect all facts from all tiers
    all_facts = []
    for scanner in SCANNERS:
        try:
            candidates = scanner.scan()
            for c in candidates:
                all_facts.append(
                    {
                        "tier": c.tier,
                        "id": c.item_id,
                        "summary": c.summary,
                        "trigrams": _word_trigrams(c.summary),
                        "age_days": c.age_days,
                    }
                )
        except Exception:
            continue

    if not all_facts:
        print(
            json.dumps(
                {
                    "ok": True,
                    "mode": "consolidate",
                    "proposed_merges": 0,
                    "message": "No facts to compare",
                }
            )
        )
        return 0

    # Find pairs with similarity > threshold
    proposed_merges = []
    seen_pairs: set[tuple] = set()
    for i, fact_a in enumerate(all_facts):
        for j, fact_b in enumerate(all_facts):
            if j <= i:
                continue
            pair_key = tuple(sorted([fact_a["id"], fact_b["id"]]))
            if pair_key in seen_pairs:
                continue

            sim = _jaccard_similarity(fact_a["trigrams"], fact_b["trigrams"])
            if sim >= CONSOLIDATION_THRESHOLD:
                seen_pairs.add(pair_key)
                # Merge winner: newest (lower age_days)
                if fact_a["age_days"] <= fact_b["age_days"]:
                    winner, loser = fact_a, fact_b
                else:
                    winner, loser = fact_b, fact_a
                proposed_merges.append(
                    {
                        "similarity": round(sim, 4),
                        "winner": {
                            "tier": winner["tier"],
                            "id": winner["id"],
                            "summary": winner["summary"][:120],
                        },
                        "loser": {
                            "tier": loser["tier"],
                            "id": loser["id"],
                            "summary": loser["summary"][:120],
                        },
                        "method": "jaccard_trigram",
                    }
                )

    if not proposed_merges:
        print(
            json.dumps(
                {
                    "ok": True,
                    "mode": "consolidate",
                    "proposed_merges": 0,
                    "message": f"No pairs above {CONSOLIDATION_THRESHOLD} threshold",
                }
            )
        )
        return 0

    if not LIFECYCLE_DELETE_ENABLED:
        print(
            json.dumps(
                {
                    "ok": True,
                    "mode": "consolidate",
                    "dry_run": True,
                    "proposed_merges": len(proposed_merges),
                    "merges": proposed_merges,
                    "message": "Set LIFECYCLE_DELETE_ENABLED=1 to apply merges",
                }
            )
        )
        return 0

    # LIVE MODE: archive sources, mark CONSOLIDATED
    archive_dir = AGENT_OS_HOME / "memory" / "archive" / "consolidation"
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_file = (
        archive_dir / f"consolidate-{datetime.now().strftime('%Y%m%dT%H%M%S')}.json"
    )
    with open(archive_file, "w", encoding="utf-8") as f:
        json.dump(
            {
                "archived_at": datetime.now(timezone.utc).isoformat(),
                "proposed_merges": proposed_merges,
            },
            f,
            indent=2,
        )

    print(
        json.dumps(
            {
                "ok": True,
                "mode": "consolidate",
                "dry_run": False,
                "proposed_merges": len(proposed_merges),
                "archive": str(archive_file),
                "message": (
                    f"Archived {len(proposed_merges)} merge proposals. "
                    "CONSOLIDATED marking deferred to optional long-term API."
                ),
            }
        )
    )
    return 0


# ── TTL Report Mode (report-only, never changes config) ────────────────────

def cmd_ttl_report(args: argparse.Namespace) -> int:
    """Read lifecycle metrics and emit TTL adjustment recommendations.

    Report-only: never writes to config. Auto-tune disabled (stub).
    """
    # Read lifecycle metrics from health gate
    metrics: dict[str, Any] = {}
    if HEALTH_GATE.is_file():
        try:
            result = subprocess.run(
                [sys.executable, str(HEALTH_GATE), "--json"],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                metrics = data.get("lifecycle", {}).get("metrics", {})
        except Exception:
            pass

    # Public default namespace TTLs (no private workspace names)
    current_ttls = {
        "default": 180,
        "lessons": 60,
        "skills": 365,
        "docs": 180,
    }

    # Analyze and recommend
    recommendations = []
    for namespace, current_ttl in current_ttls.items():
        # No data-driven tuning yet (Phase 1-2 metrics insufficient)
        recommendations.append(
            {
                "namespace": namespace,
                "current_ttl_days": current_ttl,
                "recommended_ttl_days": current_ttl,
                "confidence": "low",
                "reason": (
                    "insufficient operational data (Phase 1-2); "
                    "defer to 1-month data"
                ),
            }
        )

    output = {
        "ok": True,
        "mode": "ttl-report",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "current_ttls": current_ttls,
        "recommendations": recommendations,
        "metrics_present": bool(metrics),
        "auto_tune_enabled": False,
        "auto_tune_stub": (
            "Auto-tune disabled. Enable via LIFECYCLE_AUTO_TUNE=1 "
            "after 1 month of operational data."
        ),
    }
    print(json.dumps(output, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Cross-tier stale detection and lifecycle management for Agent OS.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Subcommands:\n"
            "  detect-stale   Report-only stale candidates across all tiers\n"
            "  consolidate    Propose cross-tier merges (delete-gated)\n"
            "  ttl-report     Report TTL adjustment recommendations\n"
        ),
    )
    parser.add_argument(
        "--mode",
        dest="mode_override",
        default=None,
        help="Alternative mode spec (e.g. --mode detect-stale)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="No-op; detect-stale is always read-only",
    )
    sub = parser.add_subparsers(dest="cmd")

    p_detect = sub.add_parser(
        "detect-stale",
        help="Report stale candidates across all tiers",
    )
    p_detect.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Max candidates to return",
    )

    sub.add_parser(
        "consolidate",
        help="Find similar entries and propose merges",
    )

    sub.add_parser(
        "ttl-report",
        help="Report TTL adjustment recommendations",
    )

    args = parser.parse_args()

    # Support --mode <name> as alternative to positional subcommand
    if args.mode_override and not args.cmd:
        args.cmd = args.mode_override
    if not hasattr(args, "limit"):
        args.limit = 50

    if args.cmd == "detect-stale":
        return cmd_detect_stale(args)
    if args.cmd == "consolidate":
        return cmd_consolidate(args)
    if args.cmd == "ttl-report":
        return cmd_ttl_report(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
