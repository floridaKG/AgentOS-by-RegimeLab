#!/usr/bin/env python3
"""
session_compress.py — Phase 2 Pipe 5

Compress a finished agent session into 3-5 durable facts:
  - Append a single dated entry to agent-os/memory.md
  - Upsert each fact to Pinecone (lessons namespace / category=insight /
    source=session-summary), one vector per fact
  - On any failure, queue the session for retry in
    agent-os/memory/state/pending_summaries.jsonl
  - Skip sessions under MIN_TURNS (default 50)
  - Truncate huge sessions: keep first HEAD_KEEP + last TAIL_KEEP turns

Two entry points:
  - compress_session(messages, session_id) — used by the session-compressor
    plugin (live, on_session_end)
  - CLI: backfill mode scans $AGENT_STATE_DIR/sessions/*.json for sessions
    not seen in the cursor; replay-queue drains pending_summaries.jsonl

LLM: opencode-go/deepseek-v4-flash via OpenAI-compatible API.
Requires OPENCODE_GO_API_KEY in env.
Override model with SESSION_COMPRESS_MODEL env var.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

_AOH = os.environ.get("AGENT_OS_HOME") or os.path.dirname(os.path.abspath(__file__))

# ── Secure temp directory (AGENTS.md: No Temp Writes) ──────────────────────
_SECURE_TMP_DIR = os.path.join(_AOH, ".local", "state", "tmp")


def _ensure_secure_tmp_dir():
    """Create and return the secure temp directory."""
    os.makedirs(_SECURE_TMP_DIR, exist_ok=True)
    return _SECURE_TMP_DIR


# ── Constants ──────────────────────────────────────────────────────────────

NAMESPACE = os.environ.get("LESSONS_NAMESPACE", "agent-os-lessons")
CATEGORY = "insight"
SOURCE_TAG = "session-summary"

MIN_TURNS = 50
HEAD_KEEP = 10
TAIL_KEEP = 30
MAX_FACTS = 5
MIN_FACTS = 3
MAX_CHARS_PER_MSG = 1200

MEMORY_MD = Path(f"{_AOH}/memory.md")
SESSIONS_DIR = Path(f"{_AOH}/{os.environ.get('AGENT_STATE_DIR', '.agent-os')}/sessions")
STATE_DIR = Path(f"{_AOH}/memory/state")
CURSOR_PATH = STATE_DIR / "session_compress_cursor.json"
PENDING_PATH = STATE_DIR / "pending_summaries.jsonl"
HEARTBEAT_PATH = Path(f"{_AOH}/{os.environ.get('AGENT_STATE_DIR', '.agent-os')}/logs/memory/session-compressor.log")
MEMORY_LT = f"{_AOH}/bin/memory-lt"

# ── LLM configuration ──────────────────────────────────────────────────────

# OpenAI-compatible API via opencode-go (replaces Gemini — was getting 429s).
# Override with SESSION_COMPRESS_MODEL or SESSION_COMPRESS_BASE_URL.
# Auth via OPENCODE_GO_API_KEY.
_DEFAULT_MODEL = "deepseek-v4-flash"
_LLM_MODEL = os.environ.get("SESSION_COMPRESS_MODEL", _DEFAULT_MODEL)
_LLM_BASE_URL = os.environ.get(
    "SESSION_COMPRESS_BASE_URL",
    "https://opencode.ai/zen/go/v1",
)
_LLM_URL = f"{_LLM_BASE_URL.rstrip('/')}/chat/completions"
_LLM_API_KEY_ENV = "OPENCODE_GO_API_KEY"

# Max retries before giving up.
MAX_RETRIES = 3
RETRY_BASE_DELAY = 2.0  # seconds, doubles each retry
API_TIMEOUT = 60  # seconds

SYSTEM_INSTRUCTION = (
    "You are condensing a finished agent session into durable knowledge. "
    "Read the conversation below and output a JSON object with a single "
    "key 'facts' containing an array of 3-5 short strings. "
    "Each fact must be: self-contained (readable without the transcript), "
    "specific (names, paths, decisions, numbers — not generic advice), "
    "durable (still true next week; skip in-progress task chatter), "
    "and <= 240 chars. "
    "If the session has nothing durable worth remembering, return "
    '{"facts": []}. '
    "Output ONLY the JSON object, no other text."
)

# ── Helpers ────────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _today_date() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


def _session_date(session_id: str) -> str:
    """Date the memory entry by the SESSION's date, not the run date.

    Session ids start with YYYYMMDD_. Dating blocks with the run date
    launders old facts as fresh (the 20260514-replay poisoning, 2026-06-10).
    """
    m = re.match(r"(\d{4})(\d{2})(\d{2})_", session_id or "")
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return _today_date()


def _heartbeat(msg: str) -> None:
    try:
        HEARTBEAT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with HEARTBEAT_PATH.open("a") as fh:
            fh.write(f"{_now_iso()} {msg}\n")
    except Exception:
        pass


def _load_cursor() -> Dict[str, Any]:
    if not CURSOR_PATH.exists():
        return {"processed_session_ids": []}
    try:
        d = json.loads(CURSOR_PATH.read_text())
        d.setdefault("processed_session_ids", [])
        return d
    except Exception as e:
        _heartbeat(f"cursor-load-failed reason={e!r}; starting fresh")
        return {"processed_session_ids": []}


def _save_cursor(cursor: Dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    if len(cursor.get("processed_session_ids", [])) > 5000:
        cursor["processed_session_ids"] = cursor["processed_session_ids"][-5000:]
    tmp = CURSOR_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cursor, indent=2))
    tmp.replace(CURSOR_PATH)


def _queue_pending(record: Dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with PENDING_PATH.open("a") as fh:
        fh.write(json.dumps(record) + "\n")


def _read_pending() -> List[Dict[str, Any]]:
    if not PENDING_PATH.exists():
        return []
    out = []
    for line in PENDING_PATH.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def _rewrite_pending(rows: List[Dict[str, Any]]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = PENDING_PATH.with_suffix(".jsonl.tmp")
    tmp.write_text("".join(json.dumps(r) + "\n" for r in rows))
    tmp.replace(PENDING_PATH)


def _truncate_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if len(messages) <= HEAD_KEEP + TAIL_KEEP:
        return messages
    head = messages[:HEAD_KEEP]
    tail = messages[-TAIL_KEEP:]
    middle = {
        "role": "system",
        "content": (
            f"[... {len(messages) - HEAD_KEEP - TAIL_KEEP} middle turns "
            f"elided to fit context ...]"
        ),
    }
    return head + [middle] + tail


def _render_transcript(messages: List[Dict[str, Any]]) -> str:
    lines = []
    for m in messages:
        role = (m.get("role") or "?").upper()
        content = m.get("content")
        if isinstance(content, list):
            parts = []
            for c in content:
                if isinstance(c, dict):
                    parts.append(c.get("text") or c.get("content") or json.dumps(c)[:200])
                else:
                    parts.append(str(c))
            content = " ".join(parts)
        if not isinstance(content, str):
            content = json.dumps(content)
        content = content.strip()
        if len(content) > MAX_CHARS_PER_MSG:
            content = content[:MAX_CHARS_PER_MSG] + " […]"
        lines.append(f"[{role}] {content}")
    return "\n\n".join(lines)


def _call_llm(transcript: str) -> Tuple[Optional[List[str]], Optional[str]]:
    """Compress transcript via OpenAI-compatible API (opencode-go).

    Retries up to MAX_RETRIES times with exponential backoff.
    Falls back to alternative model names on failure.
    """
    api_key = os.environ.get(_LLM_API_KEY_ENV)
    if not api_key:
        return None, f"{_LLM_API_KEY_ENV} not set"

    models_to_try = [
        _LLM_MODEL,
        "deepseek-v4-flash",
        "qwen3.6-plus",
        "glm-5",
    ]

    last_error = None

    for model in models_to_try:
        url = _LLM_URL

        for attempt in range(1, MAX_RETRIES + 1):
            body = {
                "model": model,
                "messages": [
                    {"role": "system", "content": SYSTEM_INSTRUCTION},
                    {"role": "user", "content": transcript},
                ],
                "temperature": 0.2,
                "max_tokens": 800,
                "response_format": {"type": "json_object"},
            }

            req = urllib.request.Request(
                url,
                data=json.dumps(body).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                    "User-Agent": "AgentOS/1.0 (session-compressor)",
                    "Accept": "application/json",
                },
                method="POST",
            )

            try:
                with urllib.request.urlopen(req, timeout=API_TIMEOUT) as resp:
                    raw_body = resp.read()
                    payload = json.loads(raw_body)
            except urllib.error.HTTPError as e:
                err_body = e.read().decode("utf-8", errors="replace")[:300]
                last_error = f"[{model}] HTTP {e.code}: {err_body}"
                _heartbeat(f"RETRY session llm={last_error} attempt={attempt}/{MAX_RETRIES}")
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_BASE_DELAY * (2 ** (attempt - 1)))
                    continue
                else:
                    break  # fall through to next model
            except Exception as e:
                last_error = f"[{model}] call failed: {e!r}"
                _heartbeat(f"RETRY session llm={last_error} attempt={attempt}/{MAX_RETRIES}")
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_BASE_DELAY * (2 ** (attempt - 1)))
                    continue
                else:
                    break

            # ── Parse OpenAI-compatible response ──
            try:
                choices = payload.get("choices", [])
                if not choices:
                    last_error = f"[{model}] no choices in response"
                    if attempt < MAX_RETRIES:
                        time.sleep(RETRY_BASE_DELAY * (2 ** (attempt - 1)))
                        continue
                    break

                choice = choices[0]
                message = choice.get("message", {})
                finish_reason = choice.get("finish_reason", "stop")

                if finish_reason in ("length", "content_filter"):
                    last_error = f"[{model}] truncated: finishReason={finish_reason}"
                    if attempt < MAX_RETRIES:
                        time.sleep(RETRY_BASE_DELAY * (2 ** (attempt - 1)))
                        continue
                    break

                text = (message.get("content") or "").strip()
                if not text:
                    last_error = f"[{model}] empty content (finishReason={finish_reason})"
                    if attempt < MAX_RETRIES:
                        time.sleep(RETRY_BASE_DELAY * (2 ** (attempt - 1)))
                        continue
                    break

                # ── Parse the JSON facts ──
                parsed = json.loads(text)
                facts = parsed.get("facts") or []
                if not isinstance(facts, list):
                    last_error = f"[{model}] facts not a list: {str(parsed)[:200]}"
                    if attempt < MAX_RETRIES:
                        time.sleep(RETRY_BASE_DELAY * (2 ** (attempt - 1)))
                        continue
                    break

                facts = [str(f).strip() for f in facts if str(f).strip()]
                if model != _DEFAULT_MODEL:
                    _heartbeat(f"FALLBACK model={model} facts={len(facts)}")
                return facts[:MAX_FACTS], None

            except json.JSONDecodeError as e:
                last_error = f"[{model}] JSON parse error: {e!r}"
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_BASE_DELAY * (2 ** (attempt - 1)))
                    continue
                break

        # Exhausted retries for this model; fall through to next model.
        _heartbeat(f"FALLBACK from {model} (exhausted {MAX_RETRIES} retries)")

    # All models exhausted.
    return None, f"all models exhausted: {last_error}"


def _append_memory_md(session_id: str, facts: List[str]) -> None:
    MEMORY_MD.parent.mkdir(parents=True, exist_ok=True)
    # Idempotence guard: one block per session, ever. Replays/backfill
    # re-runs of an already-appended session must not duplicate it.
    if MEMORY_MD.exists() and f"— {session_id}" in MEMORY_MD.read_text():
        _heartbeat(f"SKIP-APPEND session={session_id} already in memory.md")
        return
    block = [
        "",
        f"## {_session_date(session_id)} — session-compressor — {session_id}",
    ] + [f"- {f}" for f in facts] + [""]
    with MEMORY_MD.open("a") as fh:
        fh.write("\n".join(block))


def _upsert_fact(session_id: str, idx: int, fact: str) -> Dict[str, Any]:
    rid = f"{NAMESPACE}::ss_{session_id}_{idx}"
    record = {
        "_id": rid,
        "chunk_text": fact,
        "category": CATEGORY,
        "source_path": f"agent-session://{session_id}#fact{idx}",
        "promoted_by": "session-compressor",
        "scope": "home",
        "tags": [NAMESPACE, SOURCE_TAG, f"session:{session_id}"],
        "created_at": _now_iso(),
        "source": SOURCE_TAG,
        "tier": "vector",
        "promoted_from": session_id,
        "promoted_at": _now_iso(),
    }

    # Sanitize session_id for use as filename prefix (remove path components)
    safe_prefix = re.sub(r'[^a-zA-Z0-9_-]', '_', session_id).strip('_')[:50]

    # Create secure temp file with 0o600 permissions in secure state dir
    fd, tmp = tempfile.mkstemp(prefix=f"session_upsert_{safe_prefix}_{idx}_", suffix=".json", dir=_ensure_secure_tmp_dir())
    try:
        # Set secure permissions immediately
        os.chmod(tmp, 0o600)

        # Write the record
        with os.fdopen(fd, 'w') as f:
            json.dump(record, f)

        proc = subprocess.run(
            [MEMORY_LT, "upsert-vector",
             "--namespace", NAMESPACE,
             "--json-file", tmp],
            capture_output=True, text=True, timeout=30,
        )
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass
    if proc.returncode != 0:
        return {"ok": False, "error": proc.stderr.strip() or proc.stdout.strip()}
    try:
        return json.loads(proc.stdout)
    except Exception:
        return {"ok": True, "raw": proc.stdout.strip()}


# ── Public API (used by plugin + CLI) ──────────────────────────────────────


def compress_session(
    messages: List[Dict[str, Any]],
    session_id: str,
    *,
    dry_run: bool = False,
    source_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Compress a single session. Returns a structured result dict.

    Fail-safe: on any persistence/LLM error, queues the session to
    pending_summaries.jsonl and returns ok=False but does NOT raise.
    """
    n = len(messages)
    if n < MIN_TURNS:
        _heartbeat(f"SKIP session={session_id} reason=under_min_turns turns={n}")
        return {"ok": True, "session_id": session_id, "skipped": "under_min_turns", "turns": n}

    truncated = _truncate_messages(messages)
    transcript = _render_transcript(truncated)
    transcript_hash = hashlib.sha256(transcript.encode("utf-8")).hexdigest()[:16]

    facts, err = _call_llm(transcript)
    if err is not None:
        _heartbeat(f"FAIL session={session_id} llm err={err}")
        if not dry_run:
            _queue_pending({
                "session_id": session_id,
                "source_path": source_path,
                "attempted_at": _now_iso(),
                "stage": "llm",
                "error": err,
                "transcript_hash": transcript_hash,
                "message_count": n,
            })
        return {"ok": False, "session_id": session_id, "stage": "llm", "error": err}

    if not facts:
        _heartbeat(f"EMPTY session={session_id} model_returned_zero_facts")
        return {"ok": True, "session_id": session_id, "skipped": "no_durable_facts", "turns": n}

    if dry_run:
        _heartbeat(f"DRY session={session_id} facts={len(facts)}")
        return {
            "ok": True, "session_id": session_id, "dry_run": True,
            "facts": facts, "turns": n, "truncated_to": len(truncated),
        }

    # Persist to memory.md first (cheap, local, idempotent-ish).
    try:
        _append_memory_md(session_id, facts)
    except Exception as e:
        _heartbeat(f"FAIL session={session_id} memory.md err={e!r}")
        _queue_pending({
            "session_id": session_id,
            "source_path": source_path,
            "attempted_at": _now_iso(),
            "stage": "memory_md",
            "error": str(e),
            "facts": facts,
            "transcript_hash": transcript_hash,
            "message_count": n,
        })
        return {"ok": False, "session_id": session_id, "stage": "memory_md", "error": str(e)}

    # Then upsert each fact. Per-fact failure → queue what's left.
    upserted = []
    failed = []
    for idx, fact in enumerate(facts):
        outcome = _upsert_fact(session_id, idx, fact)
        if outcome.get("ok"):
            upserted.append(idx)
        else:
            failed.append({"idx": idx, "fact": fact, "error": outcome.get("error")})

    if failed:
        _heartbeat(
            f"PARTIAL session={session_id} upserted={len(upserted)} "
            f"failed={len(failed)}"
        )
        _queue_pending({
            "session_id": session_id,
            "source_path": source_path,
            "attempted_at": _now_iso(),
            "stage": "pinecone_partial",
            "facts": facts,
            "failed_indices": [f["idx"] for f in failed],
            "errors": [f["error"] for f in failed],
            "memory_md_already_appended": True,
            "transcript_hash": transcript_hash,
            "message_count": n,
        })
        return {
            "ok": False, "session_id": session_id, "stage": "pinecone_partial",
            "upserted": len(upserted), "failed": len(failed),
            "facts": facts,
        }

    _heartbeat(f"OK session={session_id} facts={len(facts)} turns={n}")
    return {
        "ok": True, "session_id": session_id,
        "facts": facts, "turns": n, "truncated_to": len(truncated),
        "upserted": len(upserted),
    }


# ── Session file loading (CLI backfill) ────────────────────────────────────


def _load_session_file(path: Path) -> Optional[Tuple[str, List[Dict[str, Any]]]]:
    try:
        d = json.loads(path.read_text())
    except Exception as e:
        _heartbeat(f"BAD-SESSION-FILE path={path} err={e!r}")
        return None
    sid = d.get("session_id") or path.stem
    msgs = d.get("messages") or d.get("history") or []
    if not isinstance(msgs, list):
        return None
    return sid, msgs


def _iter_session_files() -> Iterable[Path]:
    if not SESSIONS_DIR.exists():
        return []
    return sorted(SESSIONS_DIR.glob("session_*.json"))


# ── CLI ────────────────────────────────────────────────────────────────────


def _cmd_one(args) -> int:
    sf = Path(args.session_file)
    loaded = _load_session_file(sf)
    if not loaded:
        print(json.dumps({"ok": False, "error": f"could not load {sf}"}))
        return 2
    sid, msgs = loaded
    r = compress_session(msgs, sid, dry_run=args.dry_run, source_path=str(sf))
    # Mark in cursor on real success so backfill doesn't re-pick it.
    if r.get("ok") and not args.dry_run:
        cursor = _load_cursor()
        if sid not in cursor["processed_session_ids"]:
            cursor["processed_session_ids"].append(sid)
            _save_cursor(cursor)
    print(json.dumps(r, indent=2))
    return 0 if r.get("ok") else 1


def _cmd_backfill(args) -> int:
    cursor = _load_cursor()
    seen = set(cursor.get("processed_session_ids") or [])
    files = list(_iter_session_files())
    candidates = []
    aged_out = 0
    for p in files:
        loaded = _load_session_file(p)
        if not loaded:
            continue
        sid, msgs = loaded
        if sid in seen:
            continue
        # Age guard: facts from old sessions are then-true/now-stale and
        # poison memory when compressed late. Mark seen, never compress.
        if args.max_age_days:
            cutoff = time.time() - args.max_age_days * 86400
            sdate = _session_date(sid)
            try:
                stime = time.mktime(time.strptime(sdate, "%Y-%m-%d"))
            except ValueError:
                stime = p.stat().st_mtime
            if stime < cutoff:
                cursor["processed_session_ids"].append(sid)
                aged_out += 1
                continue
        candidates.append((sid, msgs, p))
        if args.limit and len(candidates) >= args.limit:
            break
    if aged_out and not args.dry_run:
        _save_cursor(cursor)
        _heartbeat(f"backfill aged-out={aged_out} marked seen without compressing")

    _heartbeat(
        f"backfill start dry_run={args.dry_run} candidates={len(candidates)} "
        f"min_turns={MIN_TURNS}"
    )

    if args.enumerate_only:
        print(json.dumps({
            "ok": True, "action": "backfill-enumerate",
            "candidates": len(candidates),
            "session_ids": [sid for sid, _, _ in candidates],
        }, indent=2))
        return 0

    summary = {"ok": True, "action": "backfill", "dry_run": args.dry_run,
               "candidates": len(candidates), "compressed": 0, "skipped": 0,
               "failed": 0, "results": []}
    for sid, msgs, p in candidates:
        r = compress_session(msgs, sid, dry_run=args.dry_run, source_path=str(p))
        if r.get("ok"):
            if r.get("skipped"):
                summary["skipped"] += 1
            else:
                summary["compressed"] += 1
            if not args.dry_run:
                cursor["processed_session_ids"].append(sid)
                # Save per-session: the cron's 600s timeout used to kill the
                # run before the single end-of-loop save, so every run
                # re-processed the same sessions (20260514-replay poisoning).
                _save_cursor(cursor)
        else:
            summary["failed"] += 1
        summary["results"].append({k: r[k] for k in r if k != "facts"} | (
            {"fact_count": len(r["facts"])} if "facts" in r else {}
        ))
        time.sleep(args.sleep)

    if not args.dry_run:
        _save_cursor(cursor)

    _heartbeat(
        f"backfill end compressed={summary['compressed']} "
        f"skipped={summary['skipped']} failed={summary['failed']}"
    )
    print(json.dumps(summary, indent=2))
    return 0 if summary["failed"] == 0 else 1


def _is_permanent_upsert_error(err: Any) -> bool:
    """Errors that will NEVER succeed on retry (e.g. secrets-filter denial).

    Re-queueing these loops forever: 140 of 151 pending rows on 2026-06-10
    were retries of facts the vector store had permanently rejected.
    """
    return "denied pattern" in str(err or "").lower()


def _cmd_replay(args) -> int:
    rows = _read_pending()
    # Dedupe by session_id, keep the latest row. compress_session re-queues
    # on every failed replay, so the queue accumulates copies of the same
    # few sessions (151 rows / 13 unique sessions on 2026-06-10).
    latest: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        latest[row.get("session_id") or ""] = row
    rows = [r for k, r in latest.items() if k]
    if not rows:
        if not args.dry_run:
            _rewrite_pending([])
        print(json.dumps({"ok": True, "action": "replay-queue", "pending": 0}))
        return 0

    _heartbeat(f"replay start pending={len(rows)} dry_run={args.dry_run}")
    keep: List[Dict[str, Any]] = []
    results = []
    for row in rows:
        sid = row.get("session_id")
        src = row.get("source_path")
        facts = row.get("facts")

        # Persistence-stage rows carry their facts: replay ONLY the failed
        # persistence. Re-running compress_session here re-burned an LLM call
        # and re-appended a duplicate memory.md block on every run.
        if facts:
            if args.dry_run:
                results.append({"session_id": sid, "action": "dry_run_would_retry_upserts"})
                keep.append(row)
                continue
            _append_memory_md(sid, facts)  # idempotent: no-op if present
            failed_idx = row.get("failed_indices")
            if not isinstance(failed_idx, list):
                failed_idx = list(range(len(facts)))
            still_failing, dropped = [], []
            for idx in failed_idx:
                if not isinstance(idx, int) or idx >= len(facts):
                    continue
                outcome = _upsert_fact(sid, idx, facts[idx])
                if outcome.get("ok"):
                    continue
                if _is_permanent_upsert_error(outcome.get("error")):
                    dropped.append(idx)
                    _heartbeat(f"DROP-FACT session={sid} idx={idx} permanent: "
                               f"{str(outcome.get('error'))[:120]}")
                else:
                    still_failing.append({"idx": idx, "error": outcome.get("error")})
            if still_failing:
                row = dict(row)
                row["failed_indices"] = [f["idx"] for f in still_failing]
                row["errors"] = [f["error"] for f in still_failing]
                row["memory_md_already_appended"] = True
                row["attempted_at"] = _now_iso()
                keep.append(row)
                results.append({"session_id": sid, "action": "still_failing",
                                "remaining": len(still_failing), "dropped_permanent": len(dropped)})
            else:
                results.append({"session_id": sid, "action": "resolved",
                                "dropped_permanent": len(dropped)})
            time.sleep(args.sleep)
            continue

        # LLM-stage rows (no facts yet) need the full pipeline.
        if not src or not Path(src).exists():
            results.append({"session_id": sid, "action": "drop_missing_source"})
            continue
        loaded = _load_session_file(Path(src))
        if not loaded:
            keep.append(row)
            results.append({"session_id": sid, "action": "kept_unreadable"})
            continue
        _, msgs = loaded
        r = compress_session(msgs, sid, dry_run=args.dry_run, source_path=src)
        if r.get("ok"):
            results.append({"session_id": sid, "action": "resolved"})
        else:
            # compress_session already queued a fresh entry; don't double-queue.
            results.append({"session_id": sid, "action": "still_failing",
                            "stage": r.get("stage"), "error": r.get("error")})
        time.sleep(args.sleep)

    if not args.dry_run:
        _rewrite_pending(keep)
    _heartbeat(f"replay end results={len(results)} kept={len(keep)}")
    print(json.dumps({"ok": True, "action": "replay-queue",
                      "processed": len(results), "kept": len(keep),
                      "results": results}, indent=2))
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Phase 2 Pipe 5 — session compressor")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_one = sub.add_parser("one", help="Compress one session file")
    p_one.add_argument("--session-file", required=True)
    p_one.add_argument("--dry-run", action="store_true")
    p_one.set_defaults(func=_cmd_one)

    p_bf = sub.add_parser("backfill", help="Scan sessions dir for unseen sessions")
    p_bf.add_argument("--dry-run", action="store_true")
    p_bf.add_argument("--enumerate-only", action="store_true",
                       help="List candidate session_ids and exit (no LLM calls)")
    p_bf.add_argument("--limit", type=int, default=0)
    p_bf.add_argument("--sleep", type=float, default=0.2)
    p_bf.add_argument("--max-age-days", type=int, default=0,
                      help="Sessions older than this are marked seen and never compressed (0 = off)")
    p_bf.set_defaults(func=_cmd_backfill)

    p_rp = sub.add_parser("replay-queue", help="Drain pending_summaries.jsonl")
    p_rp.add_argument("--dry-run", action="store_true")
    p_rp.add_argument("--sleep", type=float, default=0.2)
    p_rp.set_defaults(func=_cmd_replay)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
