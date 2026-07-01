#!/usr/bin/env python3
"""
memory-recall-safe.py - Fallback-safe recall across all memory tiers.

Returns local ST FTS results and Neo4j graph results even when Pinecone
semantic search is quota-blocked (RESOURCE_EXHAUSTED). Each tier result is
reported separately, with tier status clearly marked. Results include a
merged/synthesized section for convenience.

Usage:
  $AGENT_OS_HOME/scripts/memory-recall-safe.py --text "query" [--limit N] [--workspace W]

Output: Structured JSON with:
  - tier_results: per-tier results and status
  - combined: deduplicated merged results from available tiers
  - fallback_active: whether semantic tier was unavailable
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from pathlib import Path

# Self-load canonical env
_SCRIPT_PATH = Path(__file__).resolve()
_AOH = os.environ.get("AGENT_OS_HOME") or str(_SCRIPT_PATH.parent.parent)
sys.path.insert(0, str(Path(_AOH) / "memory" / "core"))
from _envload import load_env

load_env()

MEMORY_ST = f"{_AOH}/bin/memory-st"
MEMORY_LT = f"{_AOH}/bin/memory-lt"
CLAUDE_PROJECT_SLUG = re.sub(r"[^A-Za-z0-9_-]+", "-", str(Path(_AOH).resolve())).strip("-")
CLAUDE_MEMORY_DIR = Path.home() / ".claude" / "projects" / f"-{CLAUDE_PROJECT_SLUG}" / "memory"
TIMEOUT = 30
# Per-tier wall-clock budget when tiers run in parallel (WP-1). A slow tier
# (Pinecone rerank, Neo4j cold connect) can no longer serialize behind the
# others; it just reports "timed out" and the rest of the recall proceeds.
TIER_TIMEOUT = float(os.environ.get("AGENT_OS_RECALL_TIER_TIMEOUT", "20"))
RRF_K = 60  # For ranking merged results
MAX_GRAPH_ENTITIES = 5  # Cap entities fanned out to the graph tier.

# Tokens that look proper-noun-ish but carry no graph signal. Kept in sync
# with inject.py; the entity fan-out lives here so every recall consumer
# (inject.py, ACP packets, ad-hoc CLI) benefits from it identically.
_STOPWORDS = {
    "The", "This", "That", "These", "Those", "A", "An", "I", "We", "You",
    "It", "Is", "Are", "Was", "Were", "Be", "Will", "Would", "Should",
    "Could", "Can", "May", "Do", "Does", "Did", "Has", "Have", "Had",
    "If", "When", "Where", "What", "Why", "How", "Who", "And", "Or",
    "But", "For", "With", "From", "Into", "Onto", "Upon", "Note", "Add",
    "Remove", "Fix", "Use", "Run", "Make", "Build", "Check",
    "Wire", "Touch", "Read", "Write", "Edit", "Try", "Get", "Set",
    "See", "Update", "Move", "Show", "Find", "Skip", "Keep", "Send",
    "Open", "Close", "Pull", "Push", "Commit", "Apply", "Drop",
}


def _extract_entities(text, cap=MAX_GRAPH_ENTITIES):
    """Extract candidate graph entities from query text for fan-out.

    Sources: backtick code, double-quoted strings, absolute/~ paths, and
    proper-noun-ish tokens (CamelCase, dotted.identifier, kebab-case).
    Mirrors inject.py:_extract_entities so graph recall does not regress.
    """
    if not text:
        return []
    found = []
    seen = set()

    def _add(token):
        token = token.strip().strip(".,;:!?")
        if not token or len(token) < 3 or token in _STOPWORDS or token in seen:
            return
        seen.add(token)
        found.append(token)

    for m in re.finditer(r"`([^`]{2,80})`", text):
        _add(m.group(1))
    for m in re.finditer(r"\"([^\"]{2,80})\"", text):
        _add(m.group(1))
    for m in re.finditer(r"(?:^|\s)((?:/|~)[\w./\-]{2,200})", text):
        _add(m.group(1))
    for m in re.finditer(r"\b([A-Z][a-zA-Z0-9]{2,}(?:[._-][A-Za-z0-9]+)*)\b", text):
        _add(m.group(1))

    return found[:cap]


def _run_subprocess(cmd, timeout=TIMEOUT):
    """Run a command and return (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"timed out after {timeout}s"
    except Exception as exc:
        return -1, "", str(exc)


def search_st_fts(text, limit, workspace=None):
    """Search short-term memory via FTS5.

    Returns dict with status and results.
    """
    if not os.path.isfile(MEMORY_ST):
        return {"status": "unavailable", "error": f"binary not found: {MEMORY_ST}", "results": []}

    def _st_cmd(query_text):
        cmd = [MEMORY_ST, "query", "--text", query_text, "--limit", str(limit)]
        if workspace and workspace != "any":
            cmd.extend(["--workspace", workspace])
        return cmd

    rc, stdout, stderr = _run_subprocess(_st_cmd(text))
    if rc != 0 and "fts5:" in (stdout + stderr).lower():
        # FTS5 treats punctuation such as ".env.agent-os" as query syntax.
        safe_text = re.sub(r"[^A-Za-z0-9_]+", " ", text).strip()
        if safe_text and safe_text != text:
            rc, stdout, stderr = _run_subprocess(_st_cmd(safe_text))
    if rc != 0:
        return {"status": "error", "error": stderr.strip()[:200] or f"exit code {rc}", "results": []}

    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return {"status": "error", "error": f"non-JSON output: {stdout[:160]}", "results": []}

    if not data.get("ok"):
        return {"status": "error", "error": data.get("error", "ok=false")[:200], "results": []}

    results = data.get("results", [])
    # Normalize fields for consistency
    normalized = []
    for r in results:
        normalized.append({
            "id": r.get("id"),
            "tier": "short_term",
            "summary": r.get("summary", ""),
            "source_path": r.get("source_ref") or r.get("id"),
            "score": r.get("score", 0),
            "workspace": r.get("workspace"),
            "tags": [],
        })
    return {"status": "available", "result_count": len(normalized), "results": normalized}


def _query_graph_once(query_text, limit, workspace=None):
    """Single query-graph call. Returns (status, error, raw_results)."""
    cmd = [MEMORY_LT, "query-graph", "--text", query_text, "--limit", str(limit)]
    if workspace and workspace != "any":
        cmd.extend(["--workspace", workspace])
    rc, stdout, stderr = _run_subprocess(cmd)
    if rc != 0:
        return "error", stderr.strip()[:200] or f"exit code {rc}", []
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return "error", f"non-JSON output: {stdout[:160]}", []
    if not data.get("ok"):
        return "error", data.get("error", "ok=false")[:200], []
    return "available", None, data.get("results", [])


def search_graph(text, limit, workspace=None, entities=None):
    """Search Neo4j graph, fanning out over the query plus extracted entities.

    Returns dict with status and results. Entity fan-out (capped at
    MAX_GRAPH_ENTITIES) restores the pre-facade inject.py behavior so graph
    recall does not silently shrink to a single-term query.
    """
    if not os.path.isfile(MEMORY_LT):
        return {"status": "unavailable", "error": f"binary not found: {MEMORY_LT}", "results": []}

    queries = [text] + [e for e in (entities or []) if e and e != text]
    seen_ids = set()
    normalized = []
    first_error = None
    any_ok = False

    for q in queries:
        status, error, results = _query_graph_once(q, limit, workspace)
        if status != "available":
            # Backend down — one failed call is enough; don't hammer it per entity.
            first_error = first_error or error
            break
        any_ok = True
        for r in results:
            rid = r.get("id") or r.get("source_ref")
            if not rid or rid in seen_ids:
                continue
            seen_ids.add(rid)
            normalized.append({
                "id": r.get("id"),
                "tier": "graph",
                "summary": r.get("summary", ""),
                "source_path": r.get("source_ref") or r.get("id"),
                "score": 0.5,  # default score for graph results
                "workspace": r.get("workspace"),
                "tags": r.get("tags", []),
                "valid_until": r.get("valid_until"),
            })

    if not any_ok and first_error is not None:
        return {"status": "error", "error": first_error, "results": []}
    return {"status": "available", "result_count": len(normalized), "results": normalized[:limit]}


def search_semantic(text, limit, boundary_filter=None, scope=None):
    """Search Pinecone semantic vector index.

    Returns dict with status and results.
    If RESOURCE_EXHAUSTED is detected, returns status "quota_exhausted"
    so the caller knows semantic is unavailable but doesn't fail.

    boundary_filter scopes results by boundary_kind (e.g. excluding brain-tier
    memory from packets that must not see it); scope restricts the workspace
    namespace. Both are forwarded to `memory-lt search-vector`.
    """
    if not os.path.isfile(MEMORY_LT):
        return {"status": "unavailable", "error": f"binary not found: {MEMORY_LT}", "results": []}

    if not os.environ.get("PINECONE_API_KEY"):
        return {"status": "unavailable", "error": "PINECONE_API_KEY not set", "results": []}

    # --rerank: hosted bge reranker gives discriminative scores (relevant
    # ~0.1-1.0, irrelevant ~0.00) where raw e5 clustered at ~0.82 for
    # everything. Downstream floors must key off the per-result "reranked"
    # flag (rerank scale ≈0.1 floor, e5 scale ≈0.86 floor).
    cmd = [MEMORY_LT, "search-vector", "--namespace", "all", "--text", text,
           "--limit", str(limit), "--rerank"]
    if boundary_filter:
        cmd.extend(["--boundary-filter", boundary_filter])
    if scope:
        cmd.extend(["--scope", scope])
    rc, stdout, stderr = _run_subprocess(cmd)
    payload = stdout.strip() or stderr.strip()

    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return {"status": "error", "error": f"non-JSON output: {payload[:160]}", "results": []}

    # Check for RESOURCE_EXHAUSTED in namespace_errors
    errors = data.get("namespace_errors") or []
    warnings = data.get("namespace_warnings") or []
    quota_exhausted = False
    for err in errors:
        err_msg = err.get("error", "")
        if "RESOURCE_EXHAUSTED" in err_msg or "429" in err_msg:
            quota_exhausted = True
            break

    if quota_exhausted:
        return {
            "status": "quota_exhausted",
            "error": "Pinecone integrated-embedding quota exhausted (RESOURCE_EXHAUSTED)",
            "detail": errors,
            "results": [],
        }

    if rc != 0 or not data.get("ok"):
        return {"status": "error", "error": data.get("error", payload[:200]), "results": []}

    results = data.get("results", [])
    normalized = []
    for r in results:
        normalized.append({
            "id": r.get("id"),
            "tier": "semantic",
            "namespace": r.get("namespace"),
            "summary": r.get("summary", ""),
            "source_path": r.get("source_path") or r.get("id"),
            "score": r.get("score", 0),
            "reranked": bool(r.get("reranked")),
            "rerank_unavailable": bool(r.get("rerank_unavailable")),
            "category": r.get("category"),
            "scope": r.get("scope"),
            "tags": [],
        })
    if warnings:
        return {
            "status": "rerank_unavailable",
            "detail": warnings,
            "result_count": len(normalized),
            "results": normalized,
        }
    return {"status": "available", "result_count": len(normalized), "results": normalized}


_WORD_RE = re.compile(r"[a-z0-9]{3,}")

_QUERY_STOPWORDS = {
    "the", "and", "for", "with", "what", "where", "when", "how", "why",
    "who", "which", "this", "that", "these", "those", "are", "was", "were",
    "have", "has", "had", "does", "did", "can", "could", "should", "would",
    "about", "into", "from", "not", "you", "your", "our", "their",
}


def search_claude_memory(text, limit):
    """Search the canonical .claude auto-memory files lexically.

    These are the curated per-fact memory files (one fact per file, with
    name/description frontmatter). They are the canonical store — searched
    in place rather than synced into Pinecone/ST, so there is no derived
    copy to drift (future-proofing handoff 2026-06-10, T3).

    Score is honest token overlap in [0, 1]: fraction of query terms found
    in the file, with frontmatter (name/description) hits weighted double.
    """
    if not CLAUDE_MEMORY_DIR.is_dir():
        return {"status": "unavailable", "error": f"dir not found: {CLAUDE_MEMORY_DIR}", "results": []}

    terms = [t for t in _WORD_RE.findall(text.lower()) if t not in _QUERY_STOPWORDS]
    if not terms:
        return {"status": "available", "result_count": 0, "results": []}

    scored = []
    try:
        for f in sorted(CLAUDE_MEMORY_DIR.glob("*.md")):
            if f.name == "MEMORY.md":
                continue  # the index; session-injected wholesale already
            try:
                body = f.read_text(errors="replace")
            except Exception:
                continue
            lower = body.lower()
            # Frontmatter block (name/description) counts double.
            head = lower[:400]
            hit_weight = 0.0
            for t in terms:
                if t in head:
                    hit_weight += 1.0
                elif t in lower:
                    hit_weight += 0.5
            score = round(hit_weight / len(terms), 4)
            if score < 0.34:  # require ~1/3 of query terms to land
                continue
            # Summary: description line if present, else first body line.
            m = re.search(r"^description:\s*(.+)$", body, re.MULTILINE)
            summary = m.group(1).strip() if m else ""
            if not summary:
                stripped = re.sub(r"^---.*?---\s*", "", body, flags=re.DOTALL)
                summary = stripped.strip().split("\n", 1)[0][:240]
            scored.append({
                "id": f.stem,
                "tier": "claude_memory",
                "summary": summary[:300],
                "source_path": str(f),
                "score": min(score, 1.0),
                "workspace": "home",
                "tags": [],
            })
    except Exception as exc:
        return {"status": "error", "error": str(exc)[:200], "results": []}

    scored.sort(key=lambda r: r["score"], reverse=True)
    return {"status": "available", "result_count": len(scored[:limit]), "results": scored[:limit]}


def _dedup_key(result):
    """Generate a stable deduplication key for a result."""
    key = result.get("source_path") or result.get("id") or ""
    summary = (result.get("summary") or "")[:80]
    return f"{key}:{summary}"


def combine_results(tier_results, limit):
    """Merge results from all tiers with deduplication.

    Uses source_path-based dedup. Results are returned in priority order:
    semantic (highest), graph, short_term (lowest).
    """
    seen = set()
    combined = []

    # Priority order (claude_memory first: curated facts beat scraped chunks
    # regardless of raw score scale — scores are NOT comparable across tiers:
    # claude_memory is overlap [0,1], semantic is e5 cosine clustered ~0.82,
    # graph is a constant 0.5, short_term is raw BM25 (negative = better).
    tier_order = ("claude_memory", "semantic", "graph", "short_term")
    for tier_name in tier_order:
        tier = tier_results.get(tier_name, {})
        for r in tier.get("results", []):
            key = _dedup_key(r)
            if key not in seen:
                seen.add(key)
                combined.append(r)

    # Sort within tier priority, by tier-local score. Raw cross-tier score
    # sorting let uninformative e5 ~0.82s bury curated facts (handoff F7).
    rank = {t: i for i, t in enumerate(tier_order)}

    def _key(r):
        tier = r.get("tier", "")
        score = r.get("score", 0) or 0
        # short_term BM25: lower (more negative) = better → flip sign
        local = -score if tier == "short_term" else score
        return (rank.get(tier, len(tier_order)), -local)

    combined.sort(key=_key)
    return combined[:limit]


def main():
    parser = argparse.ArgumentParser(
        description="Fallback-safe recall across all memory tiers"
    )
    parser.add_argument("--text", required=True, help="Search query text")
    parser.add_argument("--limit", type=int, default=5, help="Max results (default: 5)")
    parser.add_argument("--workspace", default=None,
                        help="Filter by workspace (applied to ST + graph tiers)")
    parser.add_argument("--boundary-filter", default=None,
                        help="Comma-separated boundary kinds to include in the "
                             "semantic tier (brain,memory,legacy_no_provenance). "
                             "Scopes which provenance tiers may surface.")
    parser.add_argument("--scope", default=None,
                        choices=["home", "project-a", "project-b", "vault"],
                        help="Restrict the semantic tier to a workspace scope.")
    parser.add_argument(
        "--canonical-name", default="memory-recall-safe",
        help="Override the command name reported in JSON output "
             "(used by the memory-recall wrapper to surface the canonical name).",
    )
    parser.add_argument(
        "--tier", default=None,
        choices=["claude_memory", "short_term", "graph", "semantic"],
        help="Search ONLY this tier. Used by per-tier canary probes so a "
             "dead tier can't hide behind another tier's results.",
    )
    args = parser.parse_args()

    text = args.text
    limit = args.limit

    # Report whichever binary name invoked the facade (memory-recall or
    # memory-recall-safe). Defaults to the original command name.
    invoked_as = args.canonical_name or "memory-recall-safe"

    # Search each tier (or just the one pinned by --tier). Graph fans out
    # over the query plus extracted entities.
    entities = _extract_entities(text)
    _skip = {"status": "skipped", "results": []}
    only = args.tier

    tier_fns = {
        "short_term": lambda: search_st_fts(text, limit, workspace=args.workspace),
        "graph": lambda: search_graph(text, limit, workspace=args.workspace,
                                      entities=entities),
        "semantic": lambda: search_semantic(
            text, limit, boundary_filter=args.boundary_filter, scope=args.scope),
        "claude_memory": lambda: search_claude_memory(text, limit),
    }
    active = {name: fn for name, fn in tier_fns.items()
              if only in (None, name)}
    fetched = {name: _skip for name in tier_fns}
    with ThreadPoolExecutor(max_workers=len(active)) as pool:
        futures = {name: pool.submit(fn) for name, fn in active.items()}
        for name, fut in futures.items():
            try:
                fetched[name] = fut.result(timeout=TIER_TIMEOUT)
            except FutureTimeout:
                fetched[name] = {
                    "status": "error",
                    "error": f"tier timed out after {TIER_TIMEOUT:g}s",
                    "results": [],
                }
            except Exception as exc:
                fetched[name] = {"status": "error", "error": str(exc)[:200],
                                 "results": []}
    st_result = fetched["short_term"]
    graph_result = fetched["graph"]
    semantic_result = fetched["semantic"]
    claude_memory_result = fetched["claude_memory"]

    # Determine if fallback is active
    fallback_active = semantic_result.get("status") in (
        "quota_exhausted", "rerank_unavailable", "unavailable", "error"
    )

    tier_results = {
        "claude_memory": claude_memory_result,
        "short_term": st_result,
        "graph": graph_result,
        "semantic": semantic_result,
    }

    combined = combine_results(tier_results, limit)

    output = {
        "ok": True,
        "command": invoked_as,
        "query": text,
        "limit": limit,
        "workspace": args.workspace,
        "boundary_filter": args.boundary_filter,
        "scope": args.scope,
        "graph_entities": entities,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "fallback_active": fallback_active,
        "tier_results": tier_results,
        "results": combined,
        "result_count": len(combined),
    }

    print(json.dumps(output))

    # Exit 0 even when semantic is quota-blocked - local results are still useful.
    # Only exit non-zero if ST was actually attempted and failed (not skipped).
    # "skipped" means --tier directed us elsewhere; that's not a failure.
    if st_result.get("status") in ("unavailable", "error"):
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
