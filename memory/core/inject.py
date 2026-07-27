#!/usr/bin/python3
"""
inject.py — Packet memory injection for agent OS dual memory system (P9 WP4)

Queries short-term memory (SQLite), long-term graph memory (Neo4j),
and semantic memory (Pinecone) via the canonical memory-recall facade
to produce a scoped memory_context
for agent packets.

CLI interface for $AGENT_OS_HOME/bin/memory-inject.

Command:
  --packet <packet.json|packet.yaml> --token-budget <n> --out <context.json>

Query path:
  1. memory-recall facade via $AGENT_OS_HOME/bin/memory-recall
  2. Tier-preserving budget fit over short-term, graph, and semantic results

Returns agent.memory_context.v1 JSON.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time

# Local citation module (Memory Provenance v2 WP1.1). Importing via path
# keeps inject.py runnable as a script without depending on a package layout.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)
try:
    import citation as _citation  # type: ignore
except Exception:  # pragma: no cover — fail open, no citations wrapped
    _citation = None

# ── AGENT_OS_HOME resolution ──────────────────────────────────────────────
_AOH = os.environ.get("AGENT_OS_HOME") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── Constants ──────────────────────────────────────────────────────────────

MEMORY_ST = f"{_AOH}/bin/memory-st"
MEMORY_LT = f"{_AOH}/bin/memory-lt"
MEMORY_RECALL = f"{_AOH}/bin/memory-recall"

SCHEMA_VERSION = "agent.memory_context.v1"

# Default token budgets per intent (from DUAL_MEMORY_SPEC.md)
DEFAULT_BUDGETS = {
    "BUG": 900,
    "IMPLEMENT": 1000,
    "SPEC": 1400,
    "DOCS": 900,
    "RESEARCH": 1600,
    "HELP": 1200,
    "OPS": 900,
    "REVIEW": 1000,
}

# Phase 2 Pipe 3 budget split: vector / short-term / graph (Q6 = 60/25/15).
BUDGET_SPLIT = {"vector": 0.60, "short_term": 0.25, "graph": 0.15}

# Cap how many extracted entities we fan-out to query-graph with.
MAX_GRAPH_ENTITIES = 5

# Stopwords filtered from proper-noun extraction (common sentence starters).
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


# ── Helpers ────────────────────────────────────────────────────────────────

def _now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _run_cli(cmd_args, timeout=15):
    """Run a CLI command and return (returncode, stdout, stderr).
    Timeout is shorter for inject since it's called per-packet.
    """
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


def _estimate_tokens(text):
    """Rough token estimation: ~4 chars per token for English text."""
    return max(1, len(text) // 4)


def _estimate_item_tokens(item):
    """Estimate tokens for a single memory context item (id + summary + source_ref)."""
    text = f"{item.get('id', '')} {item.get('summary', '')} {item.get('source_ref', '')}"
    return _estimate_tokens(text)


def _deduplicate_by_source_ref(items):
    """Deduplicate a list of items by source_ref, keeping first occurrence."""
    seen = set()
    deduped = []
    for item in items:
        ref = item.get("source_ref") or item.get("source_path") or ""
        if ref and ref in seen:
            continue
        if ref:
            seen.add(ref)
        deduped.append(item)
    return deduped


def _extract_entities(text, cap=MAX_GRAPH_ENTITIES):
    """Extract candidate entities from objective text for graph fan-out.

    Returns an ordered list of distinct entity strings (cap-limited). Sources:
      - Backtick-quoted code: `like_this`
      - Double-quoted strings: "like this"
      - Absolute paths and ~paths
      - Proper-noun-ish tokens: CamelCase, dotted.identifier, kebab-case-tokens
    """
    if not text:
        return []
    found = []
    seen = set()

    def _add(token):
        token = token.strip().strip(".,;:!?")
        if not token or len(token) < 3 or token in _STOPWORDS:
            return
        if token in seen:
            return
        seen.add(token)
        found.append(token)
        return

    for m in re.finditer(r"`([^`]{2,80})`", text):
        _add(m.group(1))
    for m in re.finditer(r"\"([^\"]{2,80})\"", text):
        _add(m.group(1))
    for m in re.finditer(r"(?:^|\s)((?:/|~)[\w./\-]{2,200})", text):
        _add(m.group(1))
    for m in re.finditer(r"\b([A-Z][a-zA-Z0-9]{2,}(?:[._-][A-Za-z0-9]+)*)\b", text):
        _add(m.group(1))

    return found[:cap]


def _fit_to_budget(items, budget):
    """Return the subset of items (in order) that fits within token budget.
    Backend ranking is preserved; token fit is only a packing gate.
    """
    # Calculate token estimates
    with_tokens = []
    for item in items:
        item["_estimated_tokens"] = _estimate_item_tokens(item)
        with_tokens.append(item)

    # Greedy selection
    selected = []
    total = 0
    overhead = _estimate_tokens(json.dumps({
        "schema_version": SCHEMA_VERSION,
        "query": "",
        "token_budget": budget,
    }))

    for item in with_tokens:
        item_tokens = item["_estimated_tokens"]
        if total + item_tokens + overhead <= budget:
            selected.append(item)
            total += item_tokens

    # Remove internal tracking field
    for item in selected:
        del item["_estimated_tokens"]
    for item in with_tokens:
        if "_estimated_tokens" in item:
            del item["_estimated_tokens"]

    return selected, total


# ── Packet Loading ─────────────────────────────────────────────────────────

def load_packet(packet_path):
    """Load a packet from JSON or YAML file. Returns dict."""
    if not os.path.isfile(packet_path):
        print(json.dumps({"ok": False, "error": f"Packet file not found: {packet_path}"}),
              file=sys.stderr)
        sys.exit(1)

    with open(packet_path, "r") as f:
        content = f.read()

    # Try JSON first
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # Try YAML
    try:
        import yaml

        return yaml.safe_load(content)
    except ImportError:
        print(json.dumps({"ok": False, "error": "YAML package not available and file is not valid JSON."}),
              file=sys.stderr)
        sys.exit(1)
    except yaml.YAMLError as e:
        print(json.dumps({"ok": False, "error": f"Invalid YAML packet: {e}"}),
              file=sys.stderr)
        sys.exit(1)


# ── Query Functions ────────────────────────────────────────────────────────

def query_recall(text, workspace, limit=10, boundary_filter=None):
    """Query the canonical recall facade and return tier-separated results.

    Passes workspace scoping (ST + graph) and boundary_filter (semantic tier)
    through to the facade so injection-time scoping is not silently dropped.
    """
    cmd = [MEMORY_RECALL, "--text", text, "--limit", str(limit)]
    if workspace and workspace != "any":
        cmd.extend(["--workspace", workspace])
    if boundary_filter:
        cmd.extend(["--boundary-filter", boundary_filter])
    rc, stdout, stderr = _run_cli(cmd, timeout=30)
    if rc != 0:
        error_msg = stdout.strip() or stderr.strip() or f"Exit code {rc}"
        return None, [f"memory-recall unavailable: {error_msg}"]
    try:
        result = json.loads(stdout)
    except json.JSONDecodeError:
        return None, [f"memory-recall returned invalid JSON: {stdout[:200]}"]
    if not result.get("ok"):
        return None, [f"memory-recall error: {result.get('error', 'unknown')}"]
    notes = []
    for tier_name, tier in (result.get("tier_results") or {}).items():
        status = tier.get("status")
        if status not in ("available", None):
            notes.append(f"{tier_name} tier {status}: {tier.get('error', '')}".strip())
    return result, notes


# ── Main Injection Logic ──────────────────────────────────────────────────

def cmd_inject(packet_path, token_budget, out_path, dry_run=False, boundary_filter=None):
    """Run memory injection for a packet.

    Phase 2 Pipe 3: split budget 60/25/15 across vector/short-term/graph,
    fan-out graph queries over extracted entities, and emit a top-level
    ``graph`` key alongside ``long_term_refs`` (which becomes vector-only).
    """
    # 1. Load packet
    packet = load_packet(packet_path)

    # 2. Extract relevant fields
    workspace = packet.get("workspace", "home")
    # Normalize variant workspace names (scratch -> home)
    # so they match the canonical scopes used by long_term.py and inbox routing.
    WORKSPACE_ALIASES = {"scratch": "home"}
    workspace = WORKSPACE_ALIASES.get(workspace, workspace)
    intent = packet.get("intent", "OPS")
    objective = packet.get("objective", "")
    skills = packet.get("skills", [])
    memory_query = packet.get("memory_query", "")
    agent_id = str(packet.get("agent_id") or packet.get("agent") or "")
    run_id = str(packet.get("run_id") or packet.get("run") or "")

    # 3. Build query text
    query_parts = [objective]
    if memory_query:
        query_parts.append(memory_query)
    if skills:
        query_parts.append(" ".join(skills))
    query_text = " ".join(query_parts)
    if not query_text:
        query_text = workspace  # fallback

    # 4. Determine default budget if not provided or 0
    if not token_budget or token_budget <= 0:
        token_budget = DEFAULT_BUDGETS.get(intent, 900)

    # 5. Compute per-source budget slices (60/25/15).
    budgets = {
        "vector":     int(token_budget * BUDGET_SPLIT["vector"]),
        "short_term": int(token_budget * BUDGET_SPLIT["short_term"]),
        "graph":      int(token_budget * BUDGET_SPLIT["graph"]),
    }

    # 6. Query backends through the canonical facade
    entities = _extract_entities(objective or query_text)
    recall_result, recall_notes = query_recall(
        query_text, workspace, limit=10, boundary_filter=boundary_filter
    )
    if recall_result is None:
        st_results = []
        graph_items = []
        lt_vector_results = []
        graph_notes = list(recall_notes)
        vector_note = None
    else:
        tier_results = recall_result.get("tier_results") or {}
        st_results = tier_results.get("short_term", {}).get("results", [])
        graph_items = tier_results.get("graph", {}).get("results", [])
        lt_vector_results = tier_results.get("semantic", {}).get("results", [])
        graph_notes = list(recall_notes)
        vector_note = None

    # 6d. Memory Provenance v2 WP1.1 — wrap each retrieved row with a
    #     CitationRef so downstream consumers can audit the source.
    if _citation is not None:
        try:
            st_results = _citation.wrap_results(
                st_results, backend="sqlite", namespace="st_records",
                agent_id=agent_id, run_id=run_id,
            )
            graph_items = _citation.wrap_results(
                graph_items, backend="neo4j", namespace=workspace or "default",
                agent_id=agent_id, run_id=run_id,
            )
            lt_vector_results = _citation.wrap_results(
                lt_vector_results, backend="pinecone", namespace=workspace or "all",
                agent_id=agent_id, run_id=run_id,
            )
        except Exception:
            # Never let citation wrapping break injection.
            pass

    # 7. Deduplicate each source by source_ref independently
    st_deduped = _deduplicate_by_source_ref(st_results)
    graph_deduped = _deduplicate_by_source_ref(graph_items)
    vector_deduped = _deduplicate_by_source_ref(lt_vector_results)

    # 8. Fit each source to its slice of the budget
    st_fitted,    st_tokens    = _fit_to_budget(st_deduped,    budgets["short_term"])
    graph_fitted, graph_tokens = _fit_to_budget(graph_deduped, budgets["graph"])
    vec_fitted,   vec_tokens   = _fit_to_budget(vector_deduped, budgets["vector"])

    estimated_tokens = st_tokens + graph_tokens + vec_tokens

    # 9. Build output context (graph as its own top-level key per Pipe 3 spec).
    context = {
        "memory_context": {
            "schema_version": SCHEMA_VERSION,
            "generated_at": _now_iso(),
            "query": query_text,
            "entities": entities,
            "token_budget": token_budget,
            "budget_split": budgets,
            "estimated_tokens": estimated_tokens,
            "short_term_refs": st_fitted,
            "long_term_refs": vec_fitted,  # vector-only now
        }
    }

    # 9a. Only include "graph" key when Neo4j responded — Pipe 3 spec:
    # "Neo4j down → skip graph key, keep going."
    if not graph_notes:
        context["memory_context"]["graph"] = graph_fitted

    # Backend notes for failed backends
    backend_notes = list(graph_notes)
    if vector_note:
        backend_notes.append(vector_note)
    if backend_notes:
        context["memory_context"]["backend_notes"] = backend_notes

    summary = {
        "ok": True,
        "action": "inject",
        "dry_run": dry_run,
        "output": out_path if not dry_run else None,
        "schema_version": SCHEMA_VERSION,
        "estimated_tokens": estimated_tokens,
        "token_budget": token_budget,
        "budget_split": budgets,
        "entities": entities,
        "short_term_count": len(st_fitted),
        "graph_count": len(graph_fitted) if not graph_notes else 0,
        "vector_count": len(vec_fitted),
        "graph_skipped": bool(graph_notes),
        "backend_notes": backend_notes if backend_notes else None,
    }

    if dry_run:
        # Show what WOULD be written; nothing touches disk.
        print(json.dumps({"summary": summary, "memory_context": context["memory_context"]}, indent=2))
        return

    # 10. Write output JSON
    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(context, f, indent=2)
    print(json.dumps(summary))


# ── Argument Parser ───────────────────────────────────────────────────────

def build_parser():
    parser = argparse.ArgumentParser(
        description="Inject memory context into agent packets (P9 WP4)."
    )
    parser.add_argument("--packet", required=True,
                        help="Path to packet JSON or YAML file")
    parser.add_argument("--token-budget", type=int, default=0,
                        help="Maximum token budget for memory context")
    parser.add_argument("--out", required=False, default=None,
                        help="Output path for memory_context JSON "
                             "(omit with --dry-run)")
    parser.add_argument("--dry-run", action="store_true", default=False,
                        help="Print the would-be context to stdout; "
                             "do not write --out.")
    parser.add_argument("--boundary-filter", default=None,
                        help="Comma-separated boundary kinds passed to vector search "
                             "(brain,memory,legacy_no_provenance)")
    return parser


# ── Main Entry Point ──────────────────────────────────────────────────────

def main():
    parser = build_parser()
    args = parser.parse_args()
    if not args.dry_run and not args.out:
        print(json.dumps({"ok": False, "error": "--out is required unless --dry-run"}),
              file=sys.stderr)
        sys.exit(2)
    cmd_inject(args.packet, args.token_budget, args.out, dry_run=args.dry_run,
               boundary_filter=args.boundary_filter)


if __name__ == "__main__":
    main()
