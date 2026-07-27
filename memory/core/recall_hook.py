#!/usr/bin/python3
"""
recall_hook.py — Auto-inject relevant prior lessons into Claude Code / Codex
on every UserPromptSubmit via the hook additionalContext contract.

Usage:
    echo '{"prompt":"..."}' | recall_hook.py [--agent cc|codex]

Env:
    AGENT_OS_RECALL_HOOK_DISABLED=1  →  exit 0, no output (kill switch)

Design:
    1. Read prompt from stdin (per-agent shape)
    2. Check health gate (cached golden-canary verdict)
    3. Recall via memory-recall-safe --limit 8
    4. Filter, rank, keep top 3
    5. Format <agent_os_memory> block
    6. Emit hookSpecificOutput.additionalContext
    7. Append telemetry JSONL line

Fail-safe: on ANY internal error, print nothing to stdout, log the error,
exit 0. The hook must never block a prompt.
"""

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_AOH = os.environ.get("AGENT_OS_HOME") or os.path.dirname(os.path.abspath(__file__))


# ── Constants ──────────────────────────────────────────────────────────────

MEMORY_RECALL_SAFE = f"{_AOH}/bin/memory-recall"
_STATE_ROOT = Path(os.environ.get("AGENT_STATE_DIR", Path.home() / ".local/state/agent-os"))
if not _STATE_ROOT.is_absolute():
    _STATE_ROOT = Path(_AOH) / _STATE_ROOT
GOLDEN_CANARY_LOG = str(_STATE_ROOT / "logs/memory/golden-canary.jsonl")
TELEMETRY_LOG = str(_STATE_ROOT / "logs/memory/recall-hook.jsonl")
GOLDEN_CACHE_MAX_AGE_S = int(os.environ.get("AGENT_OS_RECALL_CACHE_MAX_AGE_S", str(26 * 60 * 60)))  # 26h default
INLINE_FALLBACK_TIMEOUT_S = 4
# Baseline recall is 3.3-4.7s (sequential tiers + hosted rerank); 6s tipped
# over under load and every prompt 20:51-21:38Z 2026-06-10 timed out with 0
# injected. Keep headroom above worst observed, env-overridable.
RECALL_TIMEOUT_S = int(os.environ.get("AGENT_OS_RECALL_TIMEOUT_S", "10"))
RECALL_LIMIT = 8
BUDGET = 3  # max results to inject (MemCoder: >8 degrades)
MAX_SUMMARY_LEN = 240
MIN_SUMMARY_LEN = 25

# Per-tier score semantics — scores are NOT comparable across tiers, and a
# single floor silently zeroed injection for 100% of live fires (handoff F4,
# root-caused 2026-06-10): short_term emits raw BM25 (negative = better),
# graph emits a constant 0.5, semantic emits e5 cosine clustered ~0.81-0.84
# — all of which sat below the old 0.80/0.86 floors forever.
#
#   claude_memory: honest token-overlap [0,1]; backend already floors at 0.34.
#   short_term:    FTS5 match = lexical relevance; presence is the signal.
#   graph:         Neo4j hit on query/entity = the signal; score carries none.
#   semantic:      two score scales since 2026-06-10. Reranked results
#                  (result["reranked"]=True, hosted bge-reranker-v2-m3) are
#                  discriminative: relevant ≳0.1, irrelevant ≈0.00 — floor at
#                  RERANK_FLOOR. Un-reranked e5 cosine clusters ~0.82 for
#                  everything — keep the 0.86 dam so mush can't inject.
SEMANTIC_FLOOR = float(os.environ.get("AGENT_OS_RECALL_SEMANTIC_FLOOR", "0.86"))
RERANK_FLOOR = float(os.environ.get("AGENT_OS_RECALL_RERANK_FLOOR", "0.10"))
CLAUDE_MEMORY_FLOOR = float(os.environ.get("AGENT_OS_RECALL_CLAUDE_FLOOR", "0.34"))
PRESENCE_TIERS = {"short_term", "graph"}  # match itself is the relevance signal

# Tier priority: lower number = higher priority (injected first when budgeting).
TIER_PRIORITY = {
    "claude_memory": 0,
    "short_term": 1,
    "graph": 2,
    "semantic": 3,
}
DEFAULT_TIER_PRIORITY = 2  # for unknown tiers

# Boilerplate / web cruft patterns to filter out (case-insensitive).
BOILERPLATE_PATTERNS = re.compile(
    r"sign in with google|cookie|subscribe|privacy policy|"
    r"terms of service|all rights reserved|©|newsletter|"
    r"advertisement|click here|read more|loading\.\.\.|"
    r"redirect|stale-warning|this file.*merged|this doc was written|"
    r"content was merged",
    re.IGNORECASE,
)


# ── Helpers ────────────────────────────────────────────────────────────────

def _now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _now_ms():
    return int(time.time() * 1000)


def _read_stdin_prompt():
    """Read JSON from stdin, extract prompt text. Returns str or empty."""
    try:
        raw = sys.stdin.read()
    except Exception:
        return ""
    if not raw.strip():
        return ""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return ""
    for key in ("prompt", "user_prompt", "input"):
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def _append_jsonl(path, record):
    """Append one JSON dict as a line to a JSONL file. Best-effort."""
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a") as f:
            f.write(json.dumps(record) + "\n")
    except Exception:
        pass  # telemetry must never crash the hook


def _basename_source(source_path):
    """Derive a short, human-readable source label from a source_path.

    Examples:
        f"{_AOH}/handoffs/memory-architecture-review__2026-06-05.md"
            → "memory-architecture-review__2026-06-05.md"
        "legacy:$AGENT_OS_HOME/lessons.md#L140-L142"
            → "lessons.md"
        "session://20260514_151143_491d23#fact4"
            → "session://…#fact4"
    """
    if not source_path:
        return "unknown"
    # Strip known prefixes
    s = source_path
    for prefix in ("legacy:", "session://", "acp:"):
        if s.startswith(prefix):
            s = s[len(prefix):]
            break
    # Take the basename portion
    s = Path(s).name if "/" in s else s
    # Truncate long IDs
    if len(s) > 60:
        s = s[:57] + "..."
    return s


def _gate_status():
    """Read cached golden-canary verdict.

    Returns (status, is_genuine, error_or_None):
      status: HEALTHY | DEGRADED | CRITICAL | STALE
      is_genuine: True if the verdict came from a fresh, valid canary run;
                  False if the cache was stale/missing/unparseable (STALE).
                  Callers use is_genuine to decide whether to trust the verdict
                  or fall back to an inline probe.
    """
    try:
        path = Path(GOLDEN_CANARY_LOG)
        if not path.exists():
            return "STALE", False, f"golden-canary.jsonl not found: {path}"
        # Read last line
        with open(path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            read_size = min(size, 4096)
            f.seek(max(0, size - read_size))
            tail = f.read().decode("utf-8", errors="replace")
        lines = [l for l in tail.strip().split("\n") if l.strip()]
        if not lines:
            return "STALE", False, "golden-canary.jsonl is empty"
        last_line = lines[-1]
        data = json.loads(last_line)
    except (json.JSONDecodeError, ValueError) as exc:
        return "STALE", False, f"golden-canary.jsonl parse error: {exc}"
    except Exception as exc:
        return "STALE", False, f"golden-canary.jsonl read error: {exc}"

    # Check cache age via ts field
    ts_str = data.get("ts")
    if ts_str:
        try:
            ts_dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            age_s = (datetime.now(timezone.utc) - ts_dt).total_seconds()
            if age_s > GOLDEN_CACHE_MAX_AGE_S:
                return "STALE", False, f"golden cache stale: {age_s:.0f}s old (max {GOLDEN_CACHE_MAX_AGE_S})"
        except Exception:
            return "STALE", False, f"golden cache ts unparseable: {ts_str}"

    overall = data.get("overall")
    if overall not in ("HEALTHY", "DEGRADED"):
        # CRITICAL or ERROR from canary — genuine bad verdict
        return overall or "CRITICAL", True, f"overall={overall}"

    return overall, True, None


def _inline_fallback_probe():
    """Fast inline connectivity check: ST-only memory-recall-safe probe.

    Returns True if the stack is reachable (even partially).
    """
    try:
        result = subprocess.run(
            [MEMORY_RECALL_SAFE, "--text", "state", "--limit", "1"],
            capture_output=True,
            text=True,
            timeout=INLINE_FALLBACK_TIMEOUT_S,
        )
        if result.returncode != 0:
            return False
        data = json.loads(result.stdout)
        return data.get("ok", False)
    except Exception:
        return False


def _recall(prompt):
    """Run memory-recall-safe and return per-tier candidates.

    Reads tier_results (per-tier), NOT the combined list: combined is sorted
    by raw cross-tier score, which let uninformative e5 ~0.82s crowd curated
    results out of the candidate pool entirely (handoff F4/F7 root cause).
    """
    try:
        result = subprocess.run(
            [MEMORY_RECALL_SAFE, "--text", prompt, "--limit", str(RECALL_LIMIT)],
            capture_output=True,
            text=True,
            timeout=RECALL_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        return [], "recall timed out"
    except Exception as exc:
        return [], f"recall exception: {exc}"

    if result.returncode != 0:
        err = result.stderr.strip()[:120] or result.stdout.strip()[:120] or f"exit {result.returncode}"
        return [], err

    try:
        data = json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError):
        return [], "non-JSON recall output"

    if not data.get("ok"):
        return [], data.get("error", "recall ok=false")[:120]

    tier_results = data.get("tier_results")
    if isinstance(tier_results, dict) and tier_results:
        candidates = []
        for tier in tier_results.values():
            candidates.extend(tier.get("results", []) or [])
        return candidates, None

    # Old recall-safe without tier_results — fall back to combined.
    return data.get("results", []), None


def _filter(results, drop_semantic=False):
    """Filter candidates: score floors, dedup, expiry, quality, boilerplate.

    Returns (filtered, rejection_stats).
    rejection_stats = {
        "expired": N,
        "by_tier": {"semantic": {"score_floor": N, ...}, ...},
        "by_reason": {"score_floor": N, "too_short": N, ...},
    }
    """
    seen_sources = set()
    filtered = []
    rejection_stats = {
        "expired": 0,
        "by_tier": {},
        "by_reason": {},
    }

    def _inc(reason, tier=None):
        rejection_stats["by_reason"][reason] = rejection_stats["by_reason"].get(reason, 0) + 1
        if tier:
            tdict = rejection_stats["by_tier"].setdefault(tier, {})
            tdict[reason] = tdict.get(reason, 0) + 1

    _now_dt = datetime.now(timezone.utc)
    for r in results:
        tier = r.get("tier", "")
        summary = (r.get("summary") or "").strip()
        source = r.get("source_path", "")
        score = r.get("score", 0)

        # Drop any result whose valid_until is present and in the past
        vu = r.get("valid_until")
        if vu is not None:
            try:
                vu_dt = datetime.fromisoformat(str(vu).replace("Z", "+00:00"))
                if vu_dt < _now_dt:
                    rejection_stats["expired"] += 1
                    _inc("expired", tier)
                    continue
            except (ValueError, TypeError):
                pass  # unparseable timestamp — treat as valid

        # Drop semantic tier when gate is DEGRADED (legacy; now disabled)
        if drop_semantic and tier == "semantic":
            _inc("drop_semantic", tier)
            continue

        # Per-tier score acceptance
        if tier == "claude_memory":
            if score < CLAUDE_MEMORY_FLOOR:
                _inc("score_floor", tier)
                continue
        elif tier in PRESENCE_TIERS:
            pass  # the match itself is the relevance signal
        elif r.get("reranked"):
            if score < RERANK_FLOOR:
                _inc("score_floor", tier)
                continue
        else:
            if score < SEMANTIC_FLOOR:
                _inc("score_floor", tier)
                continue

        # Drop empty / too-short summaries
        if len(summary) < MIN_SUMMARY_LEN:
            _inc("too_short", tier)
            continue

        # Drop boilerplate / web cruft / doc plumbing
        if BOILERPLATE_PATTERNS.search(summary):
            _inc("boilerplate", tier)
            continue

        # Dedup by source_path
        if source in seen_sources:
            _inc("dup_source", tier)
            continue
        seen_sources.add(source)

        filtered.append(r)

    return filtered, rejection_stats


def _rank_and_budget(results):
    """Sort by tier priority (lessons/ST first), then score desc. Keep top BUDGET."""
    def sort_key(r):
        tier = r.get("tier", "")
        priority = TIER_PRIORITY.get(tier, DEFAULT_TIER_PRIORITY)
        score = r.get("score", 0) or 0
        if tier == "short_term":
            score = -score  # raw BM25: more negative = better
        return (priority, -score)  # ascending priority, descending score

    results.sort(key=sort_key)
    return results[:BUDGET]


def _format_block(results):
    """Format the <agent_os_memory> additionalContext block."""
    if not results:
        return ""
    lines = ['<agent_os_memory note="auto-recalled prior lessons; verify before trusting — may be stale">']
    for r in results:
        tier = r.get("tier", "?")
        score = r.get("score", 0)
        summary = (r.get("summary") or "").strip()
        if len(summary) > MAX_SUMMARY_LEN:
            summary = summary[:MAX_SUMMARY_LEN - 3] + "..."
        source = _basename_source(r.get("source_path", ""))
        lines.append(f"- [{tier} {score:.2f}] {summary} (src: {source})")
    lines.append("</agent_os_memory>")
    return "\n".join(lines)


def _output_block(additional_context):
    """Print the hook output envelope for CC/Codex."""
    envelope = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": additional_context,
        }
    }
    print(json.dumps(envelope))


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    # Kill switch
    if os.environ.get("AGENT_OS_RECALL_HOOK_DISABLED") == "1":
        sys.exit(0)

    # Parse --agent flag
    agent = "cc"
    for i, arg in enumerate(sys.argv[1:], 1):
        if arg == "--agent" and i < len(sys.argv) - 1:
            agent = sys.argv[i + 1]
            if agent not in ("cc", "codex", "pi"):
                agent = "cc"

    start_ms = _now_ms()

    # 1. Read prompt from stdin
    prompt = _read_stdin_prompt()
    if not prompt:
        sys.exit(0)

    try:
        # 2. Health gate (cached)
        gate_status, is_genuine, gate_error = _gate_status()
        drop_semantic = False

        if not is_genuine:
            # Cache stale/missing/ERROR — NOT a real canary verdict.
            # Do an inline ST probe. If it passes, proceed optimistically
            # as HEALTHY (all tiers). memory-recall-safe self-degrades if
            # semantic is actually down.
            if _inline_fallback_probe():
                gate_status = "HEALTHY"  # optimistic — no evidence of breakage
            else:
                # ST itself unreachable — truly broken, inject nothing
                _append_jsonl(TELEMETRY_LOG, {
                    "ts": _now_iso(),
                    "agent": agent,
                    "gate_status": "ERROR",
                    "query_chars": len(prompt),
                    "n_candidates": 0,
                    "n_injected": 0,
                    "latency_ms": _now_ms() - start_ms,
                    "error": gate_error or "inline fallback failed",
                })
                sys.exit(0)
        else:
            # Genuine canary verdict — respect it
            if gate_status == "CRITICAL":
                # Genuine CRITICAL — inline probe, fail->silent, ok->HEALTHY-optimistic
                if _inline_fallback_probe():
                    gate_status = "HEALTHY"
                else:
                    _append_jsonl(TELEMETRY_LOG, {
                        "ts": _now_iso(),
                        "agent": agent,
                        "gate_status": "CRITICAL",
                        "query_chars": len(prompt),
                        "n_candidates": 0,
                        "n_injected": 0,
                        "latency_ms": _now_ms() - start_ms,
                        "error": gate_error or "CRITICAL: inline probe failed",
                    })
                    sys.exit(0)
            # DEGRADED: do NOT preemptively drop semantic tier.
            # _filter() already handles un-reranked e5 scores via
            # SEMANTIC_FLOOR (0.86). If semantic is truly dead
            # (quota_exhausted / error), recall returns 0 results.
            elif gate_status == "DEGRADED":
                pass

        # 3. Recall
        candidates, recall_error = _recall(prompt)
        n_candidates = len(candidates)

        # 4. Filter
        filtered, rejection_stats = _filter(candidates, drop_semantic=drop_semantic)
        n_expired_dropped = rejection_stats["expired"]

        # 5. Rank & budget
        budgeted = _rank_and_budget(filtered)
        n_injected = len(budgeted)

        # 6. Format block
        block = _format_block(budgeted)

        # 7. Telemetry (always) — per-tier counts so a contract drift that
        # zeroes one tier's yield is visible in the log, not silent (F4).
        def _by_tier(rs):
            counts = {}
            for r in rs:
                t = r.get("tier", "?")
                counts[t] = counts.get(t, 0) + 1
            return counts

        _append_jsonl(TELEMETRY_LOG, {
            "ts": _now_iso(),
            "agent": agent,
            "gate_status": gate_status,
            "query_chars": len(prompt),
            "n_candidates": n_candidates,
            "n_injected": n_injected,
            "n_expired_dropped": n_expired_dropped,
            "candidates_by_tier": _by_tier(candidates),
            "injected_by_tier": _by_tier(budgeted),
            "rejected_by_tier": rejection_stats.get("by_tier", {}),
            "rejected_by_reason": rejection_stats.get("by_reason", {}),
            "latency_ms": _now_ms() - start_ms,
            "error": recall_error,
        })

        # 8. Output (only when we have something to inject)
        if n_injected > 0 and block:
            _output_block(block)

    except Exception as exc:
        # Fail-safe: never block the prompt
        _append_jsonl(TELEMETRY_LOG, {
            "ts": _now_iso(),
            "agent": agent,
            "gate_status": "ERROR",
            "query_chars": len(prompt),
            "n_candidates": 0,
            "n_injected": 0,
            "latency_ms": _now_ms() - start_ms,
            "error": f"unhandled: {exc!r}",
        })
        sys.exit(0)

    sys.exit(0)


if __name__ == "__main__":
    main()
