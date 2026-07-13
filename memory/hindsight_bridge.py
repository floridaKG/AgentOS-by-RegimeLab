#!/usr/bin/env python3
"""
hindsight_bridge.py — Hindsight -> Agent OS short-term memory digest bridge.

DEFERRED FROM V1 OSS: This module requires the Hermes + Hindsight API stack,
which is not part of the open-source Agent OS distribution. It is provided
here for reference and will be activated in a future release when the
Hindsight adapter is open-sourced.

DO NOT use this bridge in production OSS deployments. It depends on:
  - hindsight_client Python package (not in requirements.txt)
  - Hindsight API running locally (http://127.0.0.1:9177)
  - Hermes runtime (not bundled)

For local-core memory, use `memory-st` and `recall` which work with SQLite
only and require no external services.

Original docstring follows:
---
hindsight_bridge.py — Hindsight -> Agent OS short-term memory digest bridge.

Exports filtered Hindsight memories into Agent OS short-term memory with
explicit provenance. This is the only supported seam from a Hindsight memory
bank into the shared Agent OS memory plane.

Requires Hermes + Hindsight API running locally. Configure via environment:

    HINDSIGHT_API_URL=http://127.0.0.1:9177                (default)
    HINDSIGHT_BANK=<your-bank-id>                            (required)
    HINDSIGHT_PROFILE=hermes                                 (default)
    AGENT_OS_HOME=/path/to/agent-os                          (required)

Usage:

    # Run via the Python environment that has hindsight_client installed:
    python3 hindsight_bridge.py --dry-run
    python3 hindsight_bridge.py --limit 50
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List


# ── Configuration from environment ──────────────────────────────────────────

AGENT_OS_HOME = os.environ.get("AGENT_OS_HOME", "").strip()
HINDSIGHT_API_URL = os.environ.get("HINDSIGHT_API_URL", "http://127.0.0.1:9177")
HINDSIGHT_BANK = os.environ.get("HINDSIGHT_BANK", "").strip()
HINDSIGHT_PROFILE = os.environ.get("HINDSIGHT_PROFILE", "hermes")

if not AGENT_OS_HOME:
    print("FATAL: AGENT_OS_HOME environment variable must be set.", file=sys.stderr)
    sys.exit(2)
if not HINDSIGHT_BANK:
    print("FATAL: HINDSIGHT_BANK environment variable must be set.", file=sys.stderr)
    sys.exit(2)

MEMORY_ST = os.environ.get("MEMORY_ST_BIN", f"{AGENT_OS_HOME}/bin/memory-st")
STATE_DIR = Path(os.environ.get("HINDSIGHT_STATE_DIR", f"{AGENT_OS_HOME}/memory/state"))
CURSOR_PATH = STATE_DIR / "hindsight_cursor.json"
HEARTBEAT_PATH = Path(
    os.environ.get(
        "HINDSIGHT_HEARTBEAT_LOG",
        str(Path.home() / ".hermes/logs/memory/hindsight-bridge.log"),
    )
)

DENIED_PATTERNS = [
    ".ssh/",
    ".mssh/",
    ".env",
    "_ed25519",
    "_rsa",
    ".pem",
    "credential",
    "credentials.json",
]


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _heartbeat(msg: str) -> None:
    try:
        HEARTBEAT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with HEARTBEAT_PATH.open("a") as fh:
            fh.write(f"{_now_iso()} {msg}\n")
    except Exception:
        pass


def _load_cursor() -> Dict[str, Any]:
    if not CURSOR_PATH.exists():
        return {"last_exported_at": None, "exported_ids": []}
    try:
        data = json.loads(CURSOR_PATH.read_text())
        if not isinstance(data, dict):
            raise ValueError("cursor not a dict")
        data.setdefault("last_exported_at", None)
        data.setdefault("exported_ids", [])
        return data
    except Exception as exc:
        _heartbeat(f"cursor-load-failed reason={exc!r}; starting fresh")
        return {"last_exported_at": None, "exported_ids": []}


def _save_cursor(cursor: Dict[str, Any]) -> None:
    CURSOR_PATH.parent.mkdir(parents=True, exist_ok=True)
    ids = cursor.get("exported_ids", [])
    if len(ids) > 5000:
        cursor["exported_ids"] = ids[-5000:]
    tmp = CURSOR_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cursor, indent=2))
    tmp.replace(CURSOR_PATH)


def _normalize_text(text: str) -> str:
    return " ".join((text or "").strip().split())


def _contains_denied(text: str) -> str | None:
    lowered = (text or "").lower()
    for pattern in DENIED_PATTERNS:
        if pattern.lower() in lowered:
            return pattern
    return None


def _source_ref(unit: Dict[str, Any]) -> str:
    bank = HINDSIGHT_BANK
    return f"hindsight://{HINDSIGHT_PROFILE}/{bank}/{unit['id']}"


def _summary(unit: Dict[str, Any]) -> str:
    fact_type = unit.get("fact_type") or "memory"
    text = _normalize_text(unit.get("text") or "")
    excerpt = text[:140]
    if len(text) > 140:
        excerpt += "..."
    return f"Hindsight {fact_type}: {excerpt or unit['id']}"


def _content(unit: Dict[str, Any]) -> str:
    tags = ", ".join(unit.get("tags") or [])
    bank = HINDSIGHT_BANK
    lines = [
        f"Hindsight digest from {HINDSIGHT_PROFILE}/{bank}/{unit['id']}",
        f"Fact type: {unit.get('fact_type') or 'memory'}",
    ]
    if tags:
        lines.append(f"Tags: {tags}")
    lines.append("")
    lines.append((unit.get("text") or "").strip())
    text = "\n".join(lines).strip()
    if len(text) > 2000:
        text = text[:2000] + "\n\n[truncated]"
    return text


def _fingerprint(summary: str, content: str, source_ref: str) -> str:
    raw = f"{content}|||{summary}|||{source_ref}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


CONTRADICTION_LOG = HEARTBEAT_PATH.parent / "contradictions.log"
CONTRADICTION_THRESHOLD = 0.85
_EMBED_CACHE = None
_EMBED_MODEL = "multilingual-e5-large"


def _get_embed_client():
    global _EMBED_CACHE
    if _EMBED_CACHE is not None:
        return _EMBED_CACHE
    try:
        from pinecone import Pinecone

        pc = Pinecone()
        pc.inference.embed(
            model=_EMBED_MODEL,
            inputs=["probe"],
            parameters={"input_type": "passage", "truncate": "END"},
        )
        _EMBED_CACHE = pc
        return pc
    except Exception:
        _EMBED_CACHE = False
        return None


def _cosine_similarity(a: list, b: list) -> float:
    import math

    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0


def _embed_texts(texts: list[str]) -> list[list[float]]:
    pc = _get_embed_client()
    if not pc or not texts:
        return []
    try:
        result = pc.inference.embed(
            model=_EMBED_MODEL,
            inputs=texts,
            parameters={"input_type": "passage", "truncate": "END"},
        )
        return [e.values for e in result.data]
    except Exception:
        return []


def _word_trigrams(text: str) -> set:
    words = text.lower().split()
    if len(words) < 3:
        return set(words)
    return {" ".join(words[i : i + 3]) for i in range(len(words) - 2)}


def _jaccard_similarity(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _check_contradiction(
    new_summary: str, new_content: str, existing_facts: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Check if new fact contradicts existing facts (LOG-ONLY). Never mutates."""
    new_text = f"{new_summary} {new_content}".strip()
    candidates = []
    fact_texts = []
    fact_indices = []
    for i, fact in enumerate(existing_facts):
        fact_text = fact.get("text", "") or fact.get("summary", "")
        if fact_text:
            fact_texts.append(fact_text)
            fact_indices.append(i)

    new_vecs = _embed_texts([new_text])
    if new_vecs and fact_texts:
        fact_vecs = _embed_texts(fact_texts)
        if fact_vecs and len(fact_vecs) == len(fact_texts):
            new_vec = new_vecs[0]
            for j, (fact_idx, fact_vec) in enumerate(zip(fact_indices, fact_vecs)):
                sim = _cosine_similarity(new_vec, fact_vec)
                if sim >= CONTRADICTION_THRESHOLD:
                    fact_text = fact_texts[j]
                    candidates.append(
                        {
                            "new_summary": new_summary[:120],
                            "existing_text": fact_text[:120],
                            "existing_id": existing_facts[fact_idx].get("id", "unknown"),
                            "similarity": round(sim, 4),
                            "method": "cosine_e5_large",
                            "timestamp": _now_iso(),
                        }
                    )
            return candidates

    new_trigrams = _word_trigrams(new_text.lower())
    for i, fact in enumerate(existing_facts):
        fact_text = fact.get("text", "") or fact.get("summary", "")
        if not fact_text:
            continue
        fact_trigrams = _word_trigrams(fact_text.lower())
        sim = _jaccard_similarity(new_trigrams, fact_trigrams)
        if sim >= CONTRADICTION_THRESHOLD:
            candidates.append(
                {
                    "new_summary": new_summary[:120],
                    "existing_text": fact_text[:120],
                    "existing_id": fact.get("id", "unknown"),
                    "similarity": round(sim, 4),
                    "method": "jaccard_trigram",
                    "timestamp": _now_iso(),
                }
            )
    return candidates


def _log_contradiction(candidate: Dict[str, Any]) -> None:
    try:
        CONTRADICTION_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(CONTRADICTION_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(candidate) + "\n")
    except OSError:
        pass


def _fetch_existing_facts(client, bank_id: str, tag_scope: str, limit: int = 200) -> List[Dict[str, Any]]:
    """Fetch existing facts from Hindsight for contradiction comparison."""
    try:
        resp = client.list_memories(bank_id=bank_id, limit=limit, offset=0)
        items = resp.items or []
        facts = []
        for raw in items:
            data = raw.model_dump() if hasattr(raw, "model_dump") else dict(raw)
            tags = data.get("tags") or []
            if tag_scope and tag_scope not in tags:
                continue
            facts.append(data)
        return facts
    except Exception:
        return []


def _run_cli(cmd_args: List[str], timeout: int = 30):
    try:
        result = subprocess.run(
            cmd_args,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode, result.stdout, result.stderr
    except FileNotFoundError:
        return 127, "", f"Command not found: {cmd_args[0]}"
    except subprocess.TimeoutExpired:
        return 124, "", "Command timed out"


def _already_written(fingerprint: str) -> bool:
    rc, stdout, _stderr = _run_cli(
        [MEMORY_ST, "get-by-fingerprint", "--fingerprint", fingerprint]
    )
    if rc != 0:
        return False
    try:
        payload = json.loads(stdout)
    except Exception:
        return False
    return bool(payload.get("ok") and payload.get("found"))


def _write_digest(unit: Dict[str, Any], summary: str, content: str, fingerprint: str) -> Dict[str, Any]:
    source_ref = _source_ref(unit)
    tmp_path = Path(f"/tmp/hindsight_digest_{unit['id']}.txt")
    fd = os.open(str(tmp_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(content)
    cmd = [
        MEMORY_ST,
        "write",
        "--run-id", "hindsight-bridge",
        "--agent-id", "hindsight-bridge",
        "--workspace", "home",
        "--intent", "LESSON",
        "--kind", "observation",
        "--summary", summary,
        "--content-file", str(tmp_path),
        "--source-ref", source_ref,
        "--fingerprint", fingerprint,
        "--boundary-kind", "brain",
        "--justify-no-evidence", "hindsight_digest_export",
        "--tag", "origin:hindsight",
        "--tag", "hindsight",
        "--tag", f"hs_id:{unit['id']}",
        "--tag", f"fact_type:{unit.get('fact_type') or 'memory'}",
    ]
    for tag in unit.get("tags") or []:
        cmd.extend(["--tag", f"hindsight_tag:{tag}"])
    try:
        rc, stdout, stderr = _run_cli(cmd)
    finally:
        archive_dir = Path("/tmp/agent-os-hindsight/archive")
        archive_dir.mkdir(parents=True, exist_ok=True)
        try:
            tmp_path.replace(archive_dir / f"{tmp_path.name}.{int(time.time())}")
        except OSError:
            pass
    if rc != 0:
        return {"ok": False, "error": stdout.strip() or stderr.strip() or f"rc={rc}"}
    try:
        return json.loads(stdout)
    except Exception:
        return {"ok": True, "raw": stdout.strip()}


def _iter_new_memories(client, bank_id: str, cursor: Dict[str, Any], hard_limit: int):
    last_at = cursor.get("last_exported_at")
    already = set(cursor.get("exported_ids") or [])
    page_size = 50
    offset = 0
    seen = 0
    collected: List[Dict[str, Any]] = []
    while seen < hard_limit:
        resp = client.list_memories(bank_id=bank_id, limit=page_size, offset=offset)
        items = resp.items or []
        if not items:
            break
        for raw in items:
            data = raw.model_dump() if hasattr(raw, "model_dump") else dict(raw)
            mentioned = str(data.get("mentioned_at") or data.get("date") or "")
            if last_at and mentioned and mentioned <= last_at:
                continue
            if data.get("id") in already:
                continue
            collected.append(data)
            seen += 1
            if seen >= hard_limit:
                break
        if len(items) < page_size:
            break
        offset += page_size
    collected.sort(key=lambda d: str(d.get("mentioned_at") or d.get("date") or ""))
    return collected


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Export filtered Hindsight digests into Agent OS short-term memory"
    )
    ap.add_argument("--dry-run", action="store_true", default=False)
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--sleep", type=float, default=0.1)
    args = ap.parse_args()

    try:
        from hindsight_client import Hindsight
    except ImportError as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": (
                        f"hindsight_client not on path. "
                        f"Install it in your Hermes Python environment. ({exc})"
                    ),
                }
            )
        )
        sys.exit(2)

    cursor = _load_cursor()
    bank_id = HINDSIGHT_BANK

    _heartbeat(
        f"start dry_run={args.dry_run} limit={args.limit} "
        f"cursor_last={cursor.get('last_exported_at')}"
    )

    with Hindsight(HINDSIGHT_API_URL) as client:
        try:
            candidates = _iter_new_memories(client, bank_id, cursor, args.limit)
        except Exception as exc:
            _heartbeat(f"FAIL hindsight-list err={exc!r}")
            print(json.dumps({"ok": False, "error": f"hindsight list failed: {exc}"}))
            sys.exit(1)
        existing_facts = _fetch_existing_facts(client, bank_id, tag_scope="", limit=200)

    written = deduped = filtered = contradictions = errors = 0
    results = []

    for unit in candidates:
        source_ref = _source_ref(unit)
        summary = _summary(unit)
        content = _content(unit)
        combined = "\n".join([summary, content, source_ref])
        denied = _contains_denied(combined)
        if denied:
            filtered += 1
            results.append({"id": unit["id"], "action": "filtered", "reason": f"denied:{denied}"})
            continue

        fingerprint = _fingerprint(summary, content, source_ref)
        if _already_written(fingerprint):
            deduped += 1
            cursor.setdefault("exported_ids", []).append(unit["id"])
            results.append({"id": unit["id"], "action": "deduped"})
            continue

        contradiction_pairs = _check_contradiction(summary, content, existing_facts)
        if contradiction_pairs:
            for pair in contradiction_pairs:
                _log_contradiction(pair)
            contradictions += 1
            results.append(
                {
                    "id": unit["id"],
                    "action": "contradiction_logged",
                    "pairs": len(contradiction_pairs),
                    "max_similarity": max(p["similarity"] for p in contradiction_pairs),
                }
            )

        if args.dry_run:
            results.append(
                {
                    "id": unit["id"],
                    "action": "dry_run",
                    "summary": summary,
                    "source_ref": source_ref,
                }
            )
            continue

        payload = _write_digest(unit, summary, content, fingerprint)
        if payload.get("ok"):
            written += 1
            cursor.setdefault("exported_ids", []).append(unit["id"])
            cursor["last_exported_at"] = (
                unit.get("mentioned_at") or unit.get("date") or cursor.get("last_exported_at")
            )
            results.append(
                {
                    "id": unit["id"],
                    "action": "written",
                    "st_record_id": payload.get("id"),
                }
            )
        else:
            errors += 1
            results.append(
                {
                    "id": unit["id"],
                    "action": "error",
                    "error": payload.get("error", "unknown error"),
                }
            )
        time.sleep(args.sleep)

    if not args.dry_run:
        _save_cursor(cursor)

    summary = {
        "ok": True,
        "action": "hindsight-to-st",
        "dry_run": args.dry_run,
        "candidates": len(candidates),
        "written": written,
        "deduped": deduped,
        "filtered": filtered,
        "contradictions": contradictions,
        "errors": errors,
        "results": results,
    }
    _heartbeat(
        f"end written={written} deduped={deduped} filtered={filtered} "
        f"errors={errors} dry_run={args.dry_run}"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
