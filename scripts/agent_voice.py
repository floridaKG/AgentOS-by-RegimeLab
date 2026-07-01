#!/usr/bin/env python3
"""
Agent Voice AV-1 — insight event contract + shared append-only JSONL buffer.

Any Agent OS agent emits a candidate *insight* (a proactive observation about
how Agent OS should evolve) into one shared, append-only buffer with a stable
schema, evidence, and a self-declared confidence. This is the foundation the
AV-2 (passive) and AV-3 (active) delivery surfaces read from.

Spec: $AGENT_OS_HOME/docs/specs/active/2026-06-15-agent-voice-av1-insight-contract.md

Storage: append-only JSONL, one insight per line, fcntl.flock around appends so
parallel agents cannot interleave a partial line. No daemon, no network — emit
is a pure local file write so sandboxed agents can use it.
"""

import argparse
import contextlib
import fcntl
import json
import os
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_AOH = os.environ.get("AGENT_OS_HOME") or os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

KIND_ENUM = ("friction", "improvement", "risk", "pattern", "question")
CONFIDENCE_ENUM = ("low", "medium", "high")
DEFAULT_CONFIDENCE = "low"


def buffer_dir() -> Path:
    """Buffer directory. AGENT_VOICE_DIR overrides for tests/isolation."""
    override = os.environ.get("AGENT_VOICE_DIR")
    if override:
        return Path(override)
    return Path.home() / ".local" / "state" / "agent-os" / "agent-voice"


def buffer_path() -> Path:
    return buffer_dir() / "insights.jsonl"


def emitting_agent() -> str:
    return (
        os.environ.get("AGENT_VOICE_ID")
        or os.environ.get("AGENT_MAIL_ID")
        or os.environ.get("USER")
        or "unknown"
    )


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_id() -> str:
    compact = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"iv_{compact}_{secrets.token_hex(4)}"


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

@contextlib.contextmanager
def _buffer_lock():
    """Exclusive advisory lock on a dedicated lock file.

    Both append (AV-1 emit) and full-rewrite (AV-2 mark) take this lock, so an
    emit can never append into a file that a mark is about to rename away — the
    rename-vs-open-append race that would otherwise lose writes (AV-2 AC6).
    """
    lp = buffer_dir() / ".insights.lock"
    lp.parent.mkdir(parents=True, exist_ok=True)
    with open(lp, "w") as lf:
        fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lf.fileno(), fcntl.LOCK_UN)


def append_insight(record: Dict[str, Any]) -> None:
    """Append one insight as a JSON line under the shared buffer lock."""
    path = buffer_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False) + "\n"
    with _buffer_lock():
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())


def write_all_insights(records: List[Dict[str, Any]]) -> None:
    """Rewrite the buffer atomically: write to .tmp then rename, under the lock.

    Honors the no-rm / atomic-replace convention — the append log is never
    destructively edited in place.
    """
    path = buffer_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(path) + ".tmp")
    with _buffer_lock():
        with open(tmp, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)


def read_insights() -> List[Dict[str, Any]]:
    """Read all insight entries, returning a flattened view.

    The buffer is append-only. Feedback entries (kind="feedback") are folded
    into their target insight: the latest owner_feedback wins. This gives
    readers a single per-insight view while preserving the audit trail in the
    raw JSONL (read_insights_raw for that).
    """
    raw = read_insights_raw()
    # Index of insight records by id, in the order they were emitted
    out_by_id: Dict[str, Dict[str, Any]] = {}
    feedback_by_target: Dict[str, List[Dict[str, Any]]] = {}

    for r in raw:
        if r.get("kind") == "feedback" and r.get("target_id"):
            feedback_by_target.setdefault(r["target_id"], []).append(r)
        else:
            out_by_id[r["id"]] = dict(r)  # shallow copy

    # Apply last-write-wins feedback
    for target_id, fbs in feedback_by_target.items():
        if target_id in out_by_id:
            latest = fbs[-1]
            if latest.get("owner_feedback"):
                out_by_id[target_id]["owner_feedback"] = latest["owner_feedback"]
                if latest.get("source_ref"):
                    out_by_id[target_id]["feedback_reason"] = latest["source_ref"]
                out_by_id[target_id]["feedback_at"] = latest.get("created_at")
                out_by_id[target_id]["feedback_id"] = latest.get("id")

    # Return in original emit order
    return [out_by_id[r["id"]] for r in raw if r.get("id") in out_by_id]


def read_insights_raw() -> List[Dict[str, Any]]:
    """Read the raw JSONL buffer without folding feedback entries.

    Use this when you need the audit trail (e.g. for replay or forensics).
    """
    path = buffer_path()
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            try:
                out.append(json.loads(raw))
            except json.JSONDecodeError:
                # A corrupt line should not break readers; skip it.
                continue
    return out


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_emit(args: argparse.Namespace) -> int:
    if not (args.kind or "").strip():
        print("error: --kind must be a non-empty string", file=sys.stderr)
        return 2
    if args.kind not in KIND_ENUM:
        # AV-5 loosens the AV-1 closed enum: subsystems (skill-health, moe,
        # agent-mail) need their own stable category names ("skill-staleness",
        # "moe-degradation") for per-category ranking. The known KIND_ENUM
        # remains the documented default; unknown values still append but
        # get a stderr hint to encourage using a known kind.
        print(
            f"warning: --kind {args.kind!r} is not in the documented enum "
            f"({', '.join(KIND_ENUM)}). It will be accepted for subsystem "
            f"integrations (AV-5) but consider using a known kind.",
            file=sys.stderr,
        )

    statement = (args.statement or "").strip()
    if not statement:
        print("error: --statement must be a non-empty string", file=sys.stderr)
        return 2

    confidence = args.confidence or DEFAULT_CONFIDENCE
    if confidence not in CONFIDENCE_ENUM:
        print(
            f"error: --confidence must be one of {', '.join(CONFIDENCE_ENUM)} (got {confidence!r})",
            file=sys.stderr,
        )
        return 2

    evidence = list(args.evidence or [])
    tags = list(args.tag or [])

    record = {
        "id": new_id(),
        "created_at": now_iso(),
        "agent": args.source or emitting_agent(),
        "workspace": args.workspace or "agent-os",
        "kind": args.kind,
        "statement": statement,
        "evidence": evidence,
        "confidence": confidence,
        "tags": tags,
        "source_ref": args.source_ref,
        "status": "new",
    }

    append_insight(record)

    if not evidence:
        print(
            f"warning: insight {record['id']} has no --evidence; it will be "
            f"treated as low-trust by the review surfaces.",
            file=sys.stderr,
        )

    print(record["id"])
    return 0


def _filter(insights: List[Dict[str, Any]], args: argparse.Namespace) -> List[Dict[str, Any]]:
    out = insights
    if args.kind:
        out = [i for i in out if i.get("kind") == args.kind]
    if args.agent:
        out = [i for i in out if i.get("agent") == args.agent]
    if args.status:
        out = [i for i in out if i.get("status") == args.status]
    if args.since:
        out = [i for i in out if str(i.get("created_at", "")) >= args.since]
    return out


def cmd_list(args: argparse.Namespace) -> int:
    insights = _filter(read_insights(), args)
    if args.json:
        print(json.dumps(insights, ensure_ascii=False, indent=2))
        return 0
    if not insights:
        print("(no insights)")
        return 0
    for i in insights:
        ev = f"{len(i.get('evidence', []))} ev"
        print(
            f"{i.get('id','?')}  [{i.get('kind','?'):11}] "
            f"({i.get('confidence','?'):6}) {i.get('status','?'):8} "
            f"{i.get('agent','?'):10} {ev:6} {i.get('statement','')}"
        )
    print(f"\nTotal: {len(insights)} insight(s)")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    for i in read_insights():
        if i.get("id") == args.id:
            print(json.dumps(i, ensure_ascii=False, indent=2))
            return 0
    print(f"error: no insight with id {args.id!r}", file=sys.stderr)
    return 1


# ---------------------------------------------------------------------------
# AV-2 — passive review surface (review + mark)
# ---------------------------------------------------------------------------

TRIAGE_STATES = ("reviewed", "dismissed")


def _effective_kind(insight: Dict[str, Any]) -> str:
    """Return the 'category' field used for ranking.

    The shipped schema uses 'kind' as the categorical slot. If a future revision
    adds a real 'category' field it wins; otherwise we fall back to 'kind'.
    """
    return str(insight.get("category") or insight.get("kind") or "?")


def _category_scores(insights: List[Dict[str, Any]]) -> Dict[str, Dict[str, int]]:
    """Aggregate owner_feedback per category.

    Returns a dict: {category: {"useful": n, "not_useful": m, "total": n+m}}.
    The score itself is computed on demand by `_category_score()`.
    """
    out: Dict[str, Dict[str, int]] = {}
    for i in insights:
        fb = i.get("owner_feedback")
        if fb not in ("useful", "not-useful"):
            continue
        cat = _effective_kind(i)
        if cat not in out:
            out[cat] = {"useful": 0, "not_useful": 0, "total": 0}
        out[cat][fb.replace("-", "_")] += 1
        out[cat]["total"] += 1
    return out


def _category_score(scores: Dict[str, Dict[str, int]], category: str) -> float:
    """Useful minus not_useful, divided by total. 0.0 when no feedback yet."""
    s = scores.get(category)
    if not s or s.get("total", 0) == 0:
        return 0.0
    return (s["useful"] - s["not_useful"]) / s["total"]


def cmd_review(args: argparse.Namespace) -> int:
    insights = read_insights()
    if args.all:
        scope = insights
    elif args.status:
        scope = [i for i in insights if i.get("status") == args.status]
    else:
        scope = [i for i in insights if i.get("status") == "new"]

    scores = _category_scores(insights)

    if args.json:
        groups: Dict[str, List[Dict[str, Any]]] = {}
        for i in scope:
            groups.setdefault(_effective_kind(i), []).append(i)
        # Sort groups: highest category score first, ties broken by group size desc
        ordered_keys = sorted(
            groups.keys(),
            key=lambda k: (-_category_score(scores, k), -len(groups[k])),
        )
        ordered: Dict[str, List[Dict[str, Any]]] = {k: groups[k] for k in ordered_keys}
        print(json.dumps(ordered, ensure_ascii=False, indent=2))
        return 0

    conf_counts = {c: sum(1 for i in scope if i.get("confidence") == c) for c in CONFIDENCE_ENUM}
    label = "all" if args.all else (args.status or "new")
    print(f"Agent Voice review — {len(scope)} insight(s) [{label}]  "
          f"(high={conf_counts['high']} medium={conf_counts['medium']} low={conf_counts['low']})")
    if not scope:
        print("  (queue empty)")
        return 0
    by_kind: Dict[str, List[Dict[str, Any]]] = {}
    for i in scope:
        by_kind.setdefault(_effective_kind(i), []).append(i)
    # Sort categories by score desc (most-useful first), ties broken by group size
    for kind in sorted(by_kind, key=lambda k: (-_category_score(scores, k), -len(by_kind[k]))):
        s = _category_score(scores, kind)
        score_str = f" score={s:+.2f}" if scores.get(kind) else ""
        print(f"\n## {kind} ({len(by_kind[kind])}){score_str}")
        # Within a category: sort by owner_feedback (useful first), then created_at desc
        fb_rank = {"useful": 0, "not-useful": 1}
        for i in sorted(
            by_kind[kind],
            key=lambda r: (fb_rank.get(r.get("owner_feedback"), 99),
                           r.get("created_at", "")),
            reverse=False,
        ):
            ev = len(i.get("evidence", []))
            stmt = i.get("statement", "")
            if len(stmt) > 90:
                stmt = stmt[:87] + "..."
            fb_marker = ""
            if i.get("owner_feedback"):
                fb_marker = f" [FB:{i['owner_feedback']}]"
            print(f"  {i.get('id','?')}  ({i.get('confidence','?'):6}) "
                  f"{i.get('status','?'):9} {ev}ev  {stmt}{fb_marker}")
    return 0


def cmd_mark(args: argparse.Namespace) -> int:
    if args.state not in TRIAGE_STATES:
        print(f"error: state must be one of {', '.join(TRIAGE_STATES)} (got {args.state!r})",
              file=sys.stderr)
        return 2
    # Work on raw records to preserve the append-only audit trail (feedback
    # entries, multiple status entries for the same id, etc.).
    records = read_insights_raw()
    found = False
    for r in records:
        if r.get("id") == args.id:
            r["status"] = args.state
            r["reviewed_at"] = now_iso()
            found = True
            break
    if not found:
        print(f"error: no insight with id {args.id!r}", file=sys.stderr)
        return 1
    write_all_insights(records)
    print(f"{args.id} -> {args.state}")
    return 0


# ---------------------------------------------------------------------------
# AV-4 — feedback + ranking loop
# ---------------------------------------------------------------------------

FEEDBACK_STATES = ("useful", "not-useful")


def cmd_feedback(args: argparse.Namespace) -> int:
    """Record owner_feedback for one insight.

    Appends a feedback entry to the buffer; the latest entry per insight_id
    wins on read (last-write-wins). This preserves the append-only audit trail
    while letting the owner change their mind without rewriting history.
    """
    if args.feedback not in FEEDBACK_STATES:
        print(
            f"error: feedback must be one of {', '.join(FEEDBACK_STATES)} "
            f"(got {args.feedback!r})",
            file=sys.stderr,
        )
        return 2

    records = read_insights()
    target_id = args.id
    if not any(r.get("id") == target_id for r in records):
        print(f"error: no insight with id {target_id!r}", file=sys.stderr)
        return 1

    record = {
        "id": new_id(),
        "created_at": now_iso(),
        "agent": emitting_agent(),
        "workspace": "agent-os",
        "kind": "feedback",
        "target_id": target_id,
        "owner_feedback": args.feedback,
        "statement": f"feedback: {target_id} -> {args.feedback}",
        "evidence": [],
        "confidence": "high",
        "tags": [],
        "source_ref": args.reason,
        "status": "applied",
    }
    append_insight(record)
    print(record["id"])
    return 0


# ---------------------------------------------------------------------------
# AV-3 — active surface (surfaced gate)
# ---------------------------------------------------------------------------

def _surfaced_records() -> List[Dict[str, Any]]:
    """Insights passing the active gate: status=new AND confidence=high AND
    >=1 evidence AND novel (statement not already reviewed/dismissed).

    AV-4 adds a secondary ranking signal: each category (kind) has a score
    derived from owner_feedback. A category with net positive feedback
    surfaces higher; a category with net negative feedback is deprioritised
    but still surfaces (the gate is permissive, ranking is just order).
    Categories with no feedback yet score 0.0 (neutral).
    """
    insights = read_insights()
    scores = _category_scores(insights)

    triaged_statements = {
        i.get("statement") for i in insights if i.get("status") in TRIAGE_STATES
    }
    out = []
    for i in insights:
        if i.get("status") != "new":
            continue
        if i.get("confidence") != "high":
            continue
        if len(i.get("evidence", [])) < 1:
            continue
        if i.get("statement") in triaged_statements:  # novelty / recurrence guard
            continue
        # Annotate with category score for downstream sorting
        i["_category_score"] = _category_score(scores, _effective_kind(i))
        out.append(i)
    return out


def cmd_surfaced(args: argparse.Namespace) -> int:
    records = _surfaced_records()
    # Secondary ranking signal (AV-4): category score, then confidence, then recency
    conf_rank = {"high": 0, "medium": 1, "low": 2}
    records.sort(
        key=lambda r: (
            -r.get("_category_score", 0.0),
            conf_rank.get(r.get("confidence", "low"), 99),
            r.get("created_at", ""),
        ),
        reverse=False,
    )
    if args.count:
        print(len(records))
        return 0
    if args.json:
        print(json.dumps(records, ensure_ascii=False, indent=2))
        return 0
    if not records:
        print("(no insights have broken through the active gate)")
        return 0
    print(f"Agent Voice — {len(records)} high-confidence insight(s) broke through "
          f"(gate: confidence=high + evidence + novel; rank: category_score desc):")
    for i in records:
        score_str = f"  [cat_score={i.get('_category_score', 0.0):+.2f}]" if i.get("_category_score") else ""
        print(f"  {i.get('id','?')}  [{i.get('kind','?')}] {i.get('statement','')}{score_str}")
    return 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-voice",
        description="Agent Voice AV-1 — emit/list/show candidate insights.",
    )
    sub = parser.add_subparsers(dest="command")

    p_emit = sub.add_parser("emit", help="Emit a candidate insight into the shared buffer")
    p_emit.add_argument("--kind", required=True, help=f"one of: {', '.join(KIND_ENUM)}")
    p_emit.add_argument("--statement", required=True, help="the insight, 1-2 sentences")
    p_emit.add_argument("--evidence", action="append", help="evidence ref (repeatable)")
    p_emit.add_argument("--confidence", help=f"one of: {', '.join(CONFIDENCE_ENUM)} (default {DEFAULT_CONFIDENCE})")
    p_emit.add_argument("--workspace", help="workspace slug (default agent-os)")
    p_emit.add_argument("--tag", action="append", help="free tag (repeatable)")
    p_emit.add_argument("--source-ref", help="optional provenance pointer")
    # AV-5: subsystems (skill-health, moe, agent-mail) call emit with a stable
    # --source name. Maps to the existing 'agent' field — no schema change.
    p_emit.add_argument(
        "--source",
        help="emitting subsystem/source name (e.g. skill-health, moe, agent-mail). "
             "Defaults to AGENT_VOICE_ID / AGENT_MAIL_ID / $USER.",
    )

    p_list = sub.add_parser("list", help="List insights in the buffer")
    p_list.add_argument("--kind")
    p_list.add_argument("--agent")
    p_list.add_argument("--status")
    p_list.add_argument("--since", help="ISO timestamp lower bound")
    p_list.add_argument("--json", action="store_true")

    p_show = sub.add_parser("show", help="Show one insight by id")
    p_show.add_argument("id")

    # AV-2: passive review surface
    p_review = sub.add_parser("review", help="Grouped digest of queued insights (passive surface)")
    p_review.add_argument("--all", action="store_true", help="include reviewed/dismissed")
    p_review.add_argument("--status", help="filter to a single status")
    p_review.add_argument("--json", action="store_true")

    p_mark = sub.add_parser("mark", help="Triage an insight: reviewed | dismissed")
    p_mark.add_argument("id")
    p_mark.add_argument("state", help="reviewed | dismissed")

    # AV-4: feedback + ranking loop
    p_feedback = sub.add_parser(
        "feedback",
        help="Record owner_feedback (useful|not-useful) for an insight",
    )
    p_feedback.add_argument("id", help="the insight id to give feedback on")
    p_feedback.add_argument("feedback", help="useful | not-useful")
    p_feedback.add_argument(
        "--reason", help="optional short reason (stored as source_ref, not used in ranking)"
    )

    # AV-3: active surface gate
    p_surfaced = sub.add_parser("surfaced", help="Insights past the active gate (high+evidence+novel)")
    p_surfaced.add_argument("--json", action="store_true")
    p_surfaced.add_argument("--count", action="store_true", help="print only the integer count")

    sub.add_parser("help", help="Show this help")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "emit":
        return cmd_emit(args)
    if args.command == "list":
        return cmd_list(args)
    if args.command == "show":
        return cmd_show(args)
    if args.command == "review":
        return cmd_review(args)
    if args.command == "mark":
        return cmd_mark(args)
    if args.command == "feedback":
        return cmd_feedback(args)
    if args.command == "surfaced":
        return cmd_surfaced(args)
    # help / no command
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
