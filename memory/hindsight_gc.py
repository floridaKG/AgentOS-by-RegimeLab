#!/usr/bin/env python3
"""hindsight_gc.py — lifecycle management for the Hindsight memory bank.

DEFERRED FROM V1 OSS: This module requires the Hermes + Hindsight API stack,
which is not part of the open-source Agent OS distribution. It is provided
here for reference only.

For local-core memory lifecycle management, use `stumble-triage` and
`stumble-cleanup` which work with SQLite only.

Original docstring follows:
---
Manages the Hindsight memory lifecycle: reporting stats, staleness probing,
export backup, observation rebuild, and document pruning.

Configure via environment:

    HINDSIGHT_API_URL=http://127.0.0.1:9177               (default)
    HINDSIGHT_BANK=<your-bank-id>                           (required)
    HINDSIGHT_GC_ARCHIVE_DIR=/path/to/archive               (default: $AGENT_OS_HOME/memory/archive/hindsight-gc)
    AGENT_OS_HOME=/path/to/agent-os                         (required)

Modes:
  report   (default) — stats, staleness probes, age distribution
  export   — full-fidelity backup to archive dir
  rebuild  — export, ensure directives, wipe observations, trigger consolidation
  prune-doc <id> — delete one session document and its derived facts
  auto     — report -> rebuild if stale >= threshold
"""

import argparse
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path


# ── Configuration from environment ──────────────────────────────────────────

AGENT_OS_HOME = os.environ.get("AGENT_OS_HOME", "").strip()
HINDSIGHT_API_URL = os.environ.get("HINDSIGHT_API_URL", "http://127.0.0.1:9177")
HINDSIGHT_BANK = os.environ.get("HINDSIGHT_BANK", "").strip()

if not AGENT_OS_HOME:
    print("FATAL: AGENT_OS_HOME environment variable must be set.", file=sys.stderr)
    sys.exit(2)
if not HINDSIGHT_BANK:
    print("FATAL: HINDSIGHT_BANK environment variable must be set.", file=sys.stderr)
    sys.exit(2)

LIFECYCLE_DELETE_ENABLED = os.environ.get("LIFECYCLE_DELETE_ENABLED", "0") == "1"
AUTO_STALE_THRESHOLD = int(os.environ.get("GC_AUTO_STALE_THRESHOLD", "10"))

LOG_DIR = Path(os.environ.get("HINDSIGHT_LOG_DIR", str(Path.home() / ".hermes/logs/memory")))
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    filename=str(LOG_DIR / "gc-auto.log"),
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
auto_logger = logging.getLogger("hindsight-gc-auto")

API = HINDSIGHT_API_URL
BANK = HINDSIGHT_BANK
ARCHIVE_DIR = Path(
    os.environ.get(
        "HINDSIGHT_GC_ARCHIVE_DIR",
        f"{AGENT_OS_HOME}/memory/archive/hindsight-gc",
    )
)

# Staleness probes — customize these for your own known-false claims.
# If recall surfaces any of these markers, the bank needs a rebuild.
STALENESS_PROBES = [
    # Replace these with your own known-false claims:
    # {
    #     "query": "example stale claim query",
    #     "stale_markers": ["stale text marker 1", "stale text marker 2"],
    # },
]

GC_DIRECTIVES = [
    {
        "name": "retention-durable-only",
        "content": (
            "When consolidating, keep only DURABLE knowledge: architectural "
            "facts, file paths, commands, decisions and their reasons, bugs "
            "with root causes and fixes, user preferences. Do NOT produce "
            "observations for: one-time requests, session work narration "
            "('user asked', 'agent reviewed', 'document was created'), or "
            "conversational events with no future operational value."
        ),
        "priority": 10,
        "tags": ["gc", "retention"],
    },
    {
        "name": "supersede-contradictions",
        "content": (
            "When facts conflict, the MOST RECENT fact wins. Never restate "
            "the older claim as current. If an observation would contradict "
            "a newer fact, drop it or rewrite it as 'previously X, now Y'."
        ),
        "priority": 9,
        "tags": ["gc", "supersede"],
    },
    {
        "name": "counts-are-point-in-time",
        "content": (
            "Counts, versions and statuses (vector counts, memory totals, "
            "service up/down, N skills) are POINT-IN-TIME, not durable. "
            "Either anchor them to their date or omit them. Never present "
            "an old count as the current state."
        ),
        "priority": 8,
        "tags": ["gc", "freshness"],
    },
]


def _req(method, path, body=None, timeout=120):
    url = f"{API}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    return json.loads(raw) if raw.strip() else {}


def cmd_export(_args):
    """Full-fidelity backup — paginated memories/list dump."""
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    out = ARCHIVE_DIR / f"export-{stamp}.json"
    items, offset = [], 0
    while True:
        page = _req("GET", f"/v1/default/banks/{BANK}/memories/list"
                           f"?limit=500&offset={offset}", timeout=120)
        batch = page.get("items", [])
        items.extend(batch)
        total = page.get("total", 0)
        offset += len(batch)
        if not batch or offset >= total:
            break
    config = _req("GET", f"/v1/default/banks/{BANK}/export", timeout=60)
    out.write_text(json.dumps({"memories": items, "config_template": config},
                              indent=1))
    print(f"exported {len(items)} memories to {out} ({out.stat().st_size} bytes)")
    if not items:
        raise RuntimeError("export returned 0 memories — refusing to treat "
                           "this as a valid backup")
    return out


def _stats():
    return _req("GET", f"/v1/default/banks/{BANK}/stats")


def _age_distribution(items):
    now = datetime.now(timezone.utc)
    buckets = {"<7d": 0, "7-21d": 0, "21-60d": 0, ">60d": 0, "unknown": 0}
    for it in items:
        d = it.get("date") or it.get("mentioned_at")
        try:
            dt = datetime.fromisoformat(str(d).replace("Z", "+00:00"))
            age = (now - dt).days
        except (ValueError, TypeError):
            buckets["unknown"] += 1
            continue
        if age < 7:
            buckets["<7d"] += 1
        elif age < 21:
            buckets["7-21d"] += 1
        elif age < 60:
            buckets["21-60d"] += 1
        else:
            buckets[">60d"] += 1
    return buckets


def _run_probes():
    """Recall each probe query; flag if known-false claims surface."""
    hits = []
    for probe in STALENESS_PROBES:
        try:
            r = _req("POST", f"/v1/default/banks/{BANK}/memories/recall",
                     {"query": probe["query"], "types": ["observation"],
                      "max_tokens": 800})
        except Exception as exc:
            hits.append({"query": probe["query"], "error": str(exc)[:120]})
            continue
        results = r.get("results") or r.get("memories") or []
        for res in results:
            text = (res.get("text") or "").lower()
            for marker in probe["stale_markers"]:
                if marker in text:
                    hits.append({
                        "query": probe["query"],
                        "marker": marker,
                        "text": (res.get("text") or "")[:160],
                    })
    return hits


def cmd_report(_args):
    st = _stats()
    listing = _req("GET", f"/v1/default/banks/{BANK}/memories/list?limit=5000")
    items = listing.get("items", [])
    by_type = {}
    for it in items:
        by_type[it.get("fact_type", "?")] = by_type.get(it.get("fact_type", "?"), 0) + 1
    probes = _run_probes()
    report = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_memories": listing.get("total", len(items)),
        "by_type": by_type,
        "age_distribution": _age_distribution(items),
        "stats": {k: st.get(k) for k in
                  ("total_documents", "total_nodes", "pending_consolidation",
                   "failed_consolidation") if k in st},
        "stale_probe_hits": probes,
    }
    print(json.dumps(report, indent=2))
    if probes:
        print(f"\nSTALE: {len(probes)} known-false claim(s) still surfacing "
              f"in observation recall — consider `hindsight_gc.py rebuild --yes`",
              file=sys.stderr)
        return 1
    return 0


def _ensure_directives():
    existing = _req("GET", f"/v1/default/banks/{BANK}/directives?limit=100")
    have = {d.get("name") for d in existing.get("items", existing.get("directives", []))}
    created = []
    for d in GC_DIRECTIVES:
        if d["name"] in have:
            continue
        _req("POST", f"/v1/default/banks/{BANK}/directives",
             {**d, "is_active": True})
        created.append(d["name"])
    return created


def cmd_rebuild(args):
    if not args.yes:
        print("rebuild wipes ALL observations and re-consolidates from raw "
              "memories. Raw world/experience facts are NOT touched. "
              "Re-run with --yes to proceed.", file=sys.stderr)
        return 2
    backup = cmd_export(args)
    created = _ensure_directives()
    print(f"directives ensured (created: {created or 'none — already present'})")
    before = _stats()
    _req("DELETE", f"/v1/default/banks/{BANK}/observations")
    print(f"observations wiped (was total_nodes={before.get('total_nodes')})")
    r = _req("POST", f"/v1/default/banks/{BANK}/consolidate", {})
    print(f"consolidation triggered: {json.dumps(r)[:200]}")
    print(f"backup at {backup}; monitor with: "
          f"curl -s {API}/v1/default/banks/{BANK}/stats")
    return 0


def cmd_prune_doc(args):
    if not args.yes:
        doc = _req("GET", f"/v1/default/banks/{BANK}/documents/{args.doc_id}")
        print(json.dumps(doc, indent=2, default=str)[:1500])
        print(f"\nDeletes this document AND its derived facts. "
              f"Re-run with --yes to proceed.", file=sys.stderr)
        return 2
    cmd_export(args)
    r = _req("DELETE", f"/v1/default/banks/{BANK}/documents/{args.doc_id}")
    print(json.dumps(r))
    return 0


def cmd_auto(args):
    threshold = args.threshold or AUTO_STALE_THRESHOLD
    auto_logger.info("auto-gc started (threshold=%d, delete_enabled=%s)",
                     threshold, LIFECYCLE_DELETE_ENABLED)

    print("auto-gc: running report...")
    try:
        rc, report_data = _run_report_capture()
    except Exception as exc:
        auto_logger.error("auto-gc: report failed: %s", exc)
        print(f"auto-gc: report failed: {exc}", file=sys.stderr)
        return 1

    stale_count = report_data.get("stale_probe_hits", 0)
    total = report_data.get("total_memories", 0)
    auto_logger.info("auto-gc: report complete: total=%d, stale=%d", total, stale_count)
    print(f"  total={total}, stale={stale_count}")

    if stale_count < threshold:
        auto_logger.info("auto-gc: stale=%d < threshold=%d, no action needed",
                         stale_count, threshold)
        print(f"  stale ({stale_count}) < threshold ({threshold}), clean.")
        return 0

    auto_logger.warning("auto-gc: stale=%d >= threshold=%d", stale_count, threshold)
    print(f"  stale ({stale_count}) >= threshold ({threshold}), action required.")

    if not LIFECYCLE_DELETE_ENABLED:
        auto_logger.info("auto-gc: DRY RUN — would export + rebuild (delete disabled)")
        print("  DRY RUN: LIFECYCLE_DELETE_ENABLED=0, would export + rebuild.")
        return 0

    print("  exporting backup...")
    try:
        backup_path = cmd_export(args)
        auto_logger.info("auto-gc: backup at %s", backup_path)
    except Exception as exc:
        auto_logger.error("auto-gc: export failed: %s", exc)
        print(f"  export failed: {exc}", file=sys.stderr)
        return 1

    print("  rebuilding...")
    args.yes = True
    try:
        rc = cmd_rebuild(args)
        if rc != 0:
            auto_logger.error("auto-gc: rebuild returned %d", rc)
            return rc
    except Exception as exc:
        auto_logger.error("auto-gc: rebuild failed: %s", exc)
        print(f"  rebuild failed: {exc}", file=sys.stderr)
        return 1

    print("  verifying...")
    try:
        _, verify_data = _run_report_capture()
        new_stale = verify_data.get("stale_probe_hits", 0)
    except Exception as exc:
        auto_logger.error("auto-gc: verify failed: %s", exc)
        print(f"  verify failed: {exc}", file=sys.stderr)
        return 1

    auto_logger.info("auto-gc: post-rebuild stale=%d (was %d)", new_stale, stale_count)
    print(f"  post-rebuild stale: {new_stale} (was {stale_count})")

    if new_stale > 100:
        auto_logger.warning("auto-gc: %d archived observations remain", new_stale)
        print(f"  WARNING: {new_stale} stale items remain — operator review recommended.")

    auto_logger.info("auto-gc: complete")
    return 0


def _run_report_capture():
    import subprocess
    result = subprocess.run(
        [sys.executable, __file__, "report"],
        capture_output=True, text=True, timeout=120,
    )
    data = {}
    for line in result.stdout.strip().splitlines():
        try:
            data = json.loads(line)
            break
        except json.JSONDecodeError:
            continue
    stale = 0
    if "STALE:" in (result.stderr or ""):
        try:
            stale = int(result.stderr.split("STALE:")[1].split()[0])
        except (IndexError, ValueError):
            pass
    data["stale_probe_hits"] = stale
    return result.returncode, data


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("report", help="stats + staleness probes (default)")
    sub.add_parser("export", help="full-fidelity backup to archive dir")
    p_rb = sub.add_parser("rebuild", help="export, wipe observations, re-consolidate")
    p_rb.add_argument("--yes", action="store_true")
    p_pd = sub.add_parser("prune-doc", help="delete one document + its derived facts")
    p_pd.add_argument("doc_id")
    p_pd.add_argument("--yes", action="store_true")
    p_auto = sub.add_parser("auto", help="automated GC")
    p_auto.add_argument("--threshold", type=int, default=None)
    args = ap.parse_args()
    cmd = args.cmd or "report"
    if cmd == "report":
        return cmd_report(args)
    if cmd == "export":
        cmd_export(args)
        return 0
    if cmd == "rebuild":
        return cmd_rebuild(args)
    if cmd == "prune-doc":
        return cmd_prune_doc(args)
    if cmd == "auto":
        return cmd_auto(args)
    return 2


if __name__ == "__main__":
    sys.exit(main())
