#!/usr/bin/python3
"""
promote.py — Promotion logic for agent OS dual memory system (P9 WP4)

Promotes short-term memory records into long-term graph memory (Neo4j)
and source files into Pinecone semantic memory (lessons namespace, agent-os-docs, vault).

CLI interface for $AGENT_OS_HOME/bin/memory-promote.

Two modes:
  --short-term-id <id> --target graph --reason <reason>
  --source-path <path> --target vector --namespace <ns> --scope <scope> --promoted-by <run_id>

Rejection rules (DUAL_MEMORY_SPEC.md):
  - Denied path or credential pattern in content/summary/source_ref/chunk_text
  - Missing source_ref
  - Unverified guess (hedging language detected)
  - Raw transcripts (chat-like patterns or excessive length)
  - Duplicate content (same fingerprint already promoted)
"""

import argparse
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import time

import ledger  # same-directory: $AGENT_OS_HOME/memory/ledger.py


# Subcommand routing: known subcommands that supersede the legacy flat CLI.
SUBCOMMANDS = {"propose", "approve", "reject", "apply", "rollback", "sweep-stale"}

# ── AGENT_OS_HOME resolution ──────────────────────────────────────────────
_AOH = os.environ.get("AGENT_OS_HOME") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── Constants ──────────────────────────────────────────────────────────────

MEMORY_ST = f"{_AOH}/bin/memory-st"
MEMORY_LT = f"{_AOH}/bin/memory-lt"

# Denied patterns (shared with long_term.py spec)
DENIED_PATTERNS = [
    r"\.ssh/",
    r"\.mssh/",
    r"\.env",
    r"_ed25519",
    r"_rsa",
    r"\.pem",
    r"credential.*\.json",
    r"credentials\.json",
]

# Hedging/uncertainty patterns for unverified guess detection
GUESS_PATTERNS = [
    r"\bmaybe\b",
    r"\bmight\b",
    r"\bcould be\b",
    r"\bpossibly\b",
    r"\bperhaps\b",
    r"\bguess\b",
    r"\bnot sure\b",
    r"\bunclear\b",
    r"\bspeculat",
    r"\bunverified\b",
    r"\bI think\b",
    r"\bI believe\b",
    r"\bprobably\b",
    r"\bsuspect\b",
]

# Raw transcript patterns
TRANSCRIPT_PATTERNS = [
    r"^\*\*.*?\*\*:",          # **role:**
    r"^> ",                     # blockquote lines
    r"^\d{2}:\d{2}:\d{2}",     # timestamps at line start
    r"^[A-Z/]+:",               # ALLCAPS role prefix at line start
]

LESSONS_NAMESPACE = os.environ.get("LESSONS_NAMESPACE", "agent-os-lessons")
ALLOWED_NAMESPACES = {LESSONS_NAMESPACE, "agent-os-docs", "vault"}
ALLOWED_SCOPES = {"home", "project-a", "project-b", "vault"}
GRAPH_PROMOTED_TAG = "promotion_target:graph"
VECTOR_PROMOTED_TAG = "promotion_target:vector"

# Vault folder allowlist (hard governance gate).
# Only files whose path is under the canonical Vault root AND whose relative
# subpath starts with one of these prefixes may be promoted to Pinecone.
# Non-Vault source paths (agent-os docs, workspace source paths,
# skills, etc.) are NOT subject to this allowlist — they are governed by
# their own indexers and the in-process validators below.
VAULT_ROOTS = (
    os.environ.get("VAULT", "~/vault") + "/",
)
VAULT_ALLOWED_PREFIXES = (
    "findings/",
    "insights/",
    "\U0001f4ca Processed/",   # "📊 Processed/"
    "\U0001f3f7️ Topics/",  # "🏷️ Topics/"
)


def _vault_relative_subpath(source_path):
    """If source_path is under a Vault root, return the relative subpath
    (using forward slashes). Otherwise return None.
    """
    # Normalize backslashes for Windows-style paths
    norm = source_path.replace("\\", "/")
    for root in VAULT_ROOTS:
        root_norm = root.replace("\\", "/")
        if norm.startswith(root_norm):
            return norm[len(root_norm):]
    return None


def _check_vault_allowlist(source_path):
    """Enforce the Vault folder allowlist.

    Returns None if the path is allowed (either not under the Vault, or
    under an allowed Vault subfolder). Returns an error string if rejected.
    """
    rel = _vault_relative_subpath(source_path)
    if rel is None:
        # Not a Vault path — allowlist does not apply.
        return None
    for prefix in VAULT_ALLOWED_PREFIXES:
        if rel.startswith(prefix):
            return None
    return (
        f"Vault source '{rel}' is outside the promotion allowlist. "
        f"Only Vault paths under one of these prefixes may be promoted: "
        f"{', '.join(VAULT_ALLOWED_PREFIXES)}."
    )


# ── Helpers ────────────────────────────────────────────────────────────────

def _now_iso():
    """Return current UTC timestamp in ISO format."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _run_cli(cmd_args):
    """Run a CLI command and return (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(
            cmd_args,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.returncode, result.stdout, result.stderr
    except FileNotFoundError:
        return 127, "", f"Command not found: {cmd_args[0]}"
    except subprocess.TimeoutExpired:
        return 124, "", "Command timed out after 30s"


def _check_denied_patterns(text):
    """Check if text contains denied secret/credential patterns.
    Returns the first matched pattern, or None.
    """
    for pattern in DENIED_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return pattern
    return None


def _check_unverified_guess(text):
    """Check if text contains hedging language suggesting unverified guess.
    Returns the first matched pattern, or None.
    """
    for pattern in GUESS_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return pattern
    return None


def _check_raw_transcript(text):
    """Check if text looks like a raw transcript.
    Returns error message string or None.
    """
    if len(text) > 5000:
        return "Content exceeds 5000 characters (possible raw transcript)"
    # Check for transcript patterns in the first 500 chars
    sample = text[:500]
    lines = sample.split("\n")
    match_count = 0
    for line in lines:
        line = line.strip()
        if not line:
            continue
        for pattern in TRANSCRIPT_PATTERNS:
            if re.search(pattern, line):
                match_count += 1
                break
    if match_count >= 3:
        return f"Content matches transcript patterns ({match_count} lines)"
    return None


def _compute_fingerprint(content, summary, source_ref):
    """Compute a deterministic SHA-256 fingerprint for dedup."""
    raw = f"{content}|||{summary}|||{source_ref}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _read_st_record(record_id):
    """Read a short-term record via memory-st get.
    Returns (record_dict, error_string).
    """
    rc, stdout, stderr = _run_cli([MEMORY_ST, "get", "--id", record_id])
    if rc != 0:
        return None, stdout.strip() or stderr.strip() or f"Exit code {rc}"
    try:
        result = json.loads(stdout)
    except json.JSONDecodeError as e:
        return None, f"Invalid JSON from memory-st get: {e}"
    if not result.get("ok"):
        return None, result.get("error", "Unknown error from memory-st get")
    record = result.get("record")
    if not record:
        return None, "No record field in memory-st get output"
    return record, None


def _update_st_promote_state(record_id, promote_state, reason=None):
    """Update promote_state via memory-st set-promote-state (supported interface).

    Agents must not write directly to SQLite — DUAL_MEMORY_SPEC says
    $AGENT_OS_HOME/bin/memory-st is the supported interface.

    Returns (success_bool, error_string_or_None).
    """
    cmd_args = [
        MEMORY_ST, "set-promote-state",
        "--id", record_id,
        "--state", promote_state,
    ]
    if reason:
        cmd_args.extend(["--reason", reason])
    rc, stdout, stderr = _run_cli(cmd_args)
    if rc != 0:
        return False, stdout.strip() or stderr.strip() or f"Exit code {rc}"
    try:
        result = json.loads(stdout)
    except json.JSONDecodeError as e:
        return False, f"Invalid JSON from memory-st: {e}"
    if result.get("ok"):
        return True, None
    return False, result.get("error", "Unknown error")


def _add_st_tag(record_id, tag):
    """Attach a tag to a short-term record via the supported CLI."""
    rc, stdout, stderr = _run_cli([
        MEMORY_ST, "add-tag", "--id", record_id, "--tag", tag,
    ])
    if rc != 0:
        return False, stdout.strip() or stderr.strip() or f"Exit code {rc}"
    try:
        result = json.loads(stdout)
    except json.JSONDecodeError as e:
        return False, f"Invalid JSON from memory-st add-tag: {e}"
    if result.get("ok"):
        return True, None
    return False, result.get("error", "Unknown error")


def _split_tags(tags_value):
    if isinstance(tags_value, list):
        return [t for t in tags_value if t]
    if isinstance(tags_value, str):
        return [t for t in tags_value.split(",") if t]
    return []


def _check_duplicate_fingerprint(fingerprint):
    """Check if a record with the same fingerprint has already been promoted.
    Uses memory-st get-by-fingerprint (supported interface).
    Returns (is_duplicate, duplicate_record_id_or_None).
    """
    rc, stdout, stderr = _run_cli([
        MEMORY_ST, "get-by-fingerprint", "--fingerprint", fingerprint,
    ])
    if rc != 0:
        return False, None
    try:
        result = json.loads(stdout)
        if result.get("ok") and result.get("found"):
            record = result["record"]
            if record.get("promote_state") == "promoted":
                return True, record["id"]
        return False, None
    except (json.JSONDecodeError, KeyError):
        return False, None


def _fail_json(message, exit_code=1):
    """Print JSON error and exit."""
    print(json.dumps({"ok": False, "error": message}))
    sys.exit(exit_code)


# ── Graph Mode ────────────────────────────────────────────────────────────

def _promote_graph_record(short_term_id, reason, mark_state=False):
    """Promote one short-term record into Neo4j graph memory."""
    record, err = _read_st_record(short_term_id)
    if err:
        return {"ok": False, "error": f"Cannot read short-term record '{short_term_id}': {err}"}

    boundary_kind = (record.get("boundary_kind") or "").strip() or None
    if boundary_kind == "session":
        try:
            _run_cli([
                MEMORY_ST, "set-promote-state",
                "--id", short_term_id,
                "--state", "rejected",
                "--reason", "session_boundary",
            ])
        except Exception:
            pass
        return {
            "ok": True,
            "action": "promote-graph",
            "short_term_id": short_term_id,
            "rejection": "session_boundary",
        }

    rec_status = record.get("status")
    if rec_status != "resolved":
        return {
            "ok": False,
            "error": (
                f"Cannot promote record '{short_term_id}': "
                f"status is '{rec_status}', must be 'resolved'."
            ),
        }

    source_ref = (record.get("source_ref") or "").strip()
    if not source_ref:
        return {
            "ok": False,
            "error": f"Cannot promote record '{short_term_id}': missing source_ref.",
        }

    content = record.get("content") or ""
    summary = record.get("summary") or ""
    tags = _split_tags(record.get("tags"))
    if GRAPH_PROMOTED_TAG in tags:
        return {
            "ok": True,
            "action": "promote-graph",
            "short_term_id": short_term_id,
            "skipped": "already_graph_promoted",
        }

    for field_name, field_value in [
        ("content", content),
        ("summary", summary),
        ("source_ref", source_ref),
    ]:
        matched = _check_denied_patterns(field_value)
        if matched:
            return {
                "ok": False,
                "error": (
                    f"Cannot promote record '{short_term_id}': "
                    f"field '{field_name}' contains denied pattern '{matched}'."
                ),
            }

    guess_matched = _check_unverified_guess(content)
    if guess_matched:
        return {
            "ok": False,
            "error": (
                f"Cannot promote record '{short_term_id}': "
                f"content appears to be an unverified guess "
                f"(matched pattern: '{guess_matched}')."
            ),
        }

    transcript_error = _check_raw_transcript(content)
    if transcript_error:
        return {
            "ok": False,
            "error": f"Cannot promote record '{short_term_id}': {transcript_error}",
        }

    fingerprint = _compute_fingerprint(content, summary, source_ref)
    is_dup, dup_id = _check_duplicate_fingerprint(fingerprint)
    if is_dup:
        return {
            "ok": False,
            "error": (
                f"Cannot promote record '{short_term_id}': "
                f"duplicate content already promoted as record '{dup_id}'."
            ),
        }

    graph_id = f"promoted_{short_term_id}"
    kind = record.get("kind", "observation")
    intent = record.get("intent", "")
    intent_type_map = {
        "LESSON": "lesson",
        "DECISION": "memory",
        "STUMBLE": "stumble",
        "CONFIRMED": "verification",
        "HELP": "help_resolution",
        "VERIFICATION": "verification",
    }
    kind_type_map = {
        "stumble": "stumble",
        "help_resolution": "help_resolution",
        "confirmed": "memory",
        "observation": "memory",
        "state": "memory",
        "verification": "verification",
        "packet_summary": "memory",
        "status": "memory",
        "help_request": "help_resolution",
    }
    graph_type = intent_type_map.get(intent) or kind_type_map.get(kind, "memory")

    # Collect existing tags and add promotion metadata
    existing_tags = tags

    graph_payload = {
        "id": graph_id,
        "run_id": record.get("run_id") or "unknown",
        "workspace": record.get("workspace") or "home",
        "type": graph_type,
        "st_record_id": short_term_id,
        "intent": intent,
        "kind": kind,
        "boundary_kind": boundary_kind or "legacy_no_provenance",
        "promoted_from": short_term_id,
        "summary": summary,
        "content": content,
        "source_ref": source_ref,
        "tags": existing_tags + [f"promoted_by:promote.py", f"reason:{reason}"],
        "created_at": _now_iso(),
        "valid_from": _now_iso(),
    }

    tmp_path = f"/tmp/promote_graph_{short_term_id}.json"
    with open(tmp_path, "w") as f:
        json.dump(graph_payload, f)

    rc, stdout, stderr = _run_cli([
        MEMORY_LT, "put-graph",
        "--type", graph_type,
        "--json-file", tmp_path,
    ])

    if rc != 0:
        error_msg = stdout.strip() or stderr.strip() or f"Exit code {rc}"
        return {
            "ok": False,
            "action": "promote-graph",
            "short_term_id": short_term_id,
            "graph_type": graph_type,
            "rejection": "graph_backend_unavailable",
            "error": f"Graph write failed: {error_msg}",
            "note": "Short-term record was NOT promoted (graph backend unavailable).",
        }

    tag_ok, tag_err = _add_st_tag(short_term_id, GRAPH_PROMOTED_TAG)

    # ── Ledger: log CLAIM_ADDED ────────────────────────────────────────
    ledger.append(
        "CLAIM_ADDED",
        graph_id,
        actor="promote.py",
        delta={"valid_from": _now_iso(), "valid_until": None},
        prior=None,
        provenance=f"promoted_from_st:{short_term_id} type:{graph_type}",
    )

    result = {
        "ok": True,
        "action": "promote-graph",
        "short_term_id": short_term_id,
        "graph_id": graph_id,
        "graph_type": graph_type,
        "graph_tag_ok": tag_ok,
        "graph_tag_err": tag_err,
    }
    if mark_state:
        success, update_err = _update_st_promote_state(
            short_term_id, "promoted", reason=reason
        )
        if not success:
            result["warning"] = f"Promotion recorded in graph but ST update failed: {update_err}"
        else:
            result["promote_state"] = "promoted"
    return result


def cmd_promote_graph(short_term_id, reason):
    """Promote a short-term record into Neo4j graph memory."""
    result = _promote_graph_record(short_term_id, reason, mark_state=False)
    if not result.get("ok") and not result.get("rejection"):
        _fail_json(result.get("error", "graph promotion failed"))
    print(json.dumps(result))


# ── Vector Mode ────────────────────────────────────────────────────────────

def cmd_promote_vector(source_path, namespace, scope, promoted_by):
    """Promote a source file into Pinecone vector memory."""
    # 1. Read the source file
    if not os.path.isfile(source_path):
        _fail_json(f"Source path not found or not a file: {source_path}")

    # 1a. Enforce Vault folder allowlist (hard governance gate).
    # Non-Vault sources (agent-os-docs, workspace source paths, skills) are unaffected.
    vault_err = _check_vault_allowlist(source_path)
    if vault_err:
        _fail_json(vault_err)

    try:
        with open(source_path, "r") as f:
            chunk_text = f.read()
    except Exception as e:
        _fail_json(f"Error reading source file '{source_path}': {e}")

    if not chunk_text.strip():
        _fail_json(f"Source file is empty: {source_path}")

    # 2. Check for denied patterns in chunk_text and source_path
    for field_name, field_value in [
        ("chunk_text", chunk_text),
        ("source_path", source_path),
    ]:
        matched = _check_denied_patterns(field_value)
        if matched:
            _fail_json(
                f"Field '{field_name}' contains denied pattern '{matched}'. "
                f"Secrets and credentials are not allowed in vector records."
            )

    # 3. Build Pinecone record following PINECONE_SCHEMA.md
    # Generate a unique record ID: <namespace>::<slug>
    basename = os.path.splitext(os.path.basename(source_path))[0]
    slug = re.sub(r"[^a-zA-Z0-9-]", "-", basename)
    slug = re.sub(r"-+", "-", slug).strip("-").lower()
    if not slug:
        slug = "promoted-file"
    record_id = f"{namespace}::{slug}"

    # Determine category from namespace
    category_map = {
        LESSONS_NAMESPACE: "lesson",
        "agent-os-docs": "reference",
        "vault": "insight",
    }
    category = category_map.get(namespace, "reference")

    # Truncate chunk_text to ~8000 chars (safety for embedding model)
    if len(chunk_text) > 8000:
        chunk_text = chunk_text[:8000] + "\n\n[truncated...]"

    record = {
        "_id": record_id,
        "chunk_text": chunk_text,
        "category": category,
        "source_path": source_path,
        "promoted_by": promoted_by,
        "scope": scope,
        "tags": [namespace, scope, "promoted"],
        "created_at": _now_iso(),
    }

    # 4. Write Pinecone record to deterministic temp path and call memory-lt upsert-vector
    # Use deterministic path under /tmp — cleanup is the orchestrator's job.
    tmp_path = f"/tmp/promote_vector_{record_id}.json"
    with open(tmp_path, "w") as f:
        json.dump(record, f)

    rc, stdout, stderr = _run_cli([
        MEMORY_LT, "upsert-vector",
        "--namespace", namespace,
        "--json-file", tmp_path,
    ])

    if rc != 0:
        error_msg = stdout.strip() or stderr.strip() or f"Exit code {rc}"
        print(json.dumps({
            "ok": False,
            "action": "promote-vector",
            "source_path": source_path,
            "namespace": namespace,
            "scope": scope,
            "rejection": "vector_backend_unavailable",
            "error": f"Vector upsert failed: {error_msg}",
        }))
        sys.exit(1)

    # Success
    try:
        upsert_response = json.loads(stdout)
    except json.JSONDecodeError:
        upsert_response = {"raw_output": stdout}

    print(json.dumps({
        "ok": True,
        "action": "promote-vector",
        "source_path": source_path,
        "namespace": namespace,
        "record_id": record_id,
        "scope": scope,
        "promoted_by": promoted_by,
        "upsert_response": upsert_response,
    }))


# ── ST → Vector Auto-Promote (Pipe 2) ─────────────────────────────────────

# Path of the short-term SQLite (same as short_term.py DB_PATH).
SHORT_TERM_DB = os.path.expanduser(
    os.environ.get(
        "AGENT_OS_ST_DB",
        f"{os.environ.get('HOME', os.path.expanduser('~'))}/.local/state/agent-os/memory/short_term.sqlite",
    )
)

# Intents eligible for auto-promotion to vector memory (Phase 2 §8.2).
PROMOTABLE_INTENTS = ("LESSON", "DECISION", "STUMBLE", "CONFIRMED")

# Routing: per locked policy (Q7 + routing decision), all promotable intents
# land in LESSONS_NAMESPACE. Keep as a dict to make future re-routing trivial.
INTENT_NAMESPACE = {
    "LESSON":    LESSONS_NAMESPACE,
    "DECISION":  LESSONS_NAMESPACE,
    "STUMBLE":   LESSONS_NAMESPACE,
    "CONFIRMED": LESSONS_NAMESPACE,
}

# Map ST intent → Pinecone schema `category` (allowlist enforced upstream:
# insight | methodology | pattern | reference | skill).
INTENT_CATEGORY = {
    "LESSON":    "insight",
    "DECISION":  "methodology",
    "STUMBLE":   "pattern",
    "CONFIRMED": "reference",
}

# Map ST workspace → vector record `scope` field.
WORKSPACE_SCOPE = {
    "home": "home", "project-a": "project-a", "project-b": "project-b", "vault": "vault",
}

AUTO_PROMOTE_LOG = f"{_AOH}/{os.environ.get('AGENT_STATE_DIR', '.agent-os')}/logs/memory/auto-promote.log"


def _heartbeat(msg):
    """Append a one-line heartbeat. Never raises."""
    try:
        os.makedirs(os.path.dirname(AUTO_PROMOTE_LOG), exist_ok=True)
        with open(AUTO_PROMOTE_LOG, "a") as fh:
            fh.write(f"{_now_iso()} {msg}\n")
    except Exception:
        pass


def _candidate_rows(intents, limit):
    """Read promotable ST rows directly (read-only). Writes go via memory-st."""
    conn = sqlite3.connect(f"file:{SHORT_TERM_DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        # Detect whether the boundary_kind column exists (post-migration).
        cols = [r[1] for r in conn.execute("PRAGMA table_info(st_records)").fetchall()]
        has_boundary_kind = "boundary_kind" in cols
        bk_select = ", r.boundary_kind" if has_boundary_kind else ", NULL AS boundary_kind"
        bk_filter = (
            "AND (r.boundary_kind IS NULL OR r.boundary_kind NOT IN ('session', 'memory'))"
            if has_boundary_kind else ""
        )
        placeholders = ",".join("?" * len(intents))
        rows = conn.execute(
            f"""SELECT r.id, r.run_id, r.agent_id, r.workspace, r.intent, r.kind,
                       r.content, r.summary, r.source_ref, r.status, r.promote_state,
                       r.fingerprint, r.created_at, r.promoted_at{bk_select},
                       GROUP_CONCAT(t.tag, ',') AS tags_str
                FROM st_records r
                LEFT JOIN st_tags t ON t.record_id = r.id
                WHERE r.intent IN ({placeholders})
                  AND r.status = 'active'
                  AND r.promoted_at IS NULL
                  AND COALESCE(r.promote_state, 'none') NOT IN ('promoted', 'rejected')
                  {bk_filter}
                GROUP BY r.id
                ORDER BY r.created_at ASC
                LIMIT ?""",
            (*intents, limit),
        ).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            item["tags"] = _split_tags(item.pop("tags_str", None))
            out.append(item)
        return out
    finally:
        conn.close()


def _graph_candidate_rows(intents, limit, replay=False):
    """Read graph-promotable ST rows directly (read-only)."""
    conn = sqlite3.connect(f"file:{SHORT_TERM_DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(st_records)").fetchall()]
        has_boundary_kind = "boundary_kind" in cols
        bk_select = ", r.boundary_kind" if has_boundary_kind else ", NULL AS boundary_kind"
        bk_filter = (
            "AND (r.boundary_kind IS NULL OR r.boundary_kind != 'session')"
            if has_boundary_kind else ""
        )
        placeholders = ",".join("?" * len(intents))
        rows = conn.execute(
            f"""SELECT r.id, r.run_id, r.agent_id, r.workspace, r.intent, r.kind,
                       r.content, r.summary, r.source_ref, r.status, r.promote_state,
                       r.fingerprint, r.created_at, r.promoted_at{bk_select},
                       GROUP_CONCAT(t.tag, ',') AS tags_str
                FROM st_records r
                LEFT JOIN st_tags t ON t.record_id = r.id
                WHERE r.intent IN ({placeholders})
                  AND r.status = 'resolved'
                  AND COALESCE(r.promote_state, 'none') NOT IN ('rejected')
                  {bk_filter}
                GROUP BY r.id
                ORDER BY r.created_at ASC
                LIMIT ?""",
            (*intents, limit),
        ).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            item["tags"] = _split_tags(item.pop("tags_str", None))
            if not replay and GRAPH_PROMOTED_TAG in item["tags"]:
                continue
            out.append(item)
        return out
    finally:
        conn.close()


def _promotion_health():
    """Return promotion backlog/report metrics from short-term memory."""
    conn = sqlite3.connect(f"file:{SHORT_TERM_DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        summary = conn.execute(
            """
            SELECT
              COUNT(*) AS total_rows,
              SUM(CASE WHEN status='active' THEN 1 ELSE 0 END) AS active_rows,
              SUM(CASE WHEN status='resolved' THEN 1 ELSE 0 END) AS resolved_rows,
              SUM(CASE WHEN promote_state='rejected' THEN 1 ELSE 0 END) AS rejected_rows,
              SUM(CASE WHEN promoted_at IS NOT NULL THEN 1 ELSE 0 END) AS vector_promoted_legacy,
              MAX(promoted_at) AS last_vector_promotion_at
            FROM st_records
            """
        ).fetchone()
        tag_counts = {
            row["tag"]: row["count"]
            for row in conn.execute(
                """
                SELECT tag, COUNT(*) AS count
                FROM st_tags
                WHERE tag IN (?, ?)
                GROUP BY tag
                """,
                (VECTOR_PROMOTED_TAG, GRAPH_PROMOTED_TAG),
            ).fetchall()
        }
        promotable_vector = len(_candidate_rows(PROMOTABLE_INTENTS, 100000))
        graph_intents = PROMOTABLE_INTENTS + ("HELP", "VERIFICATION")
        promotable_graph = len(_graph_candidate_rows(graph_intents, 100000))
        return {
            "ok": True,
            "action": "promotion-report",
            "total_rows": int(summary["total_rows"] or 0),
            "active_rows": int(summary["active_rows"] or 0),
            "resolved_rows": int(summary["resolved_rows"] or 0),
            "rejected_rows": int(summary["rejected_rows"] or 0),
            "promotable_vector": promotable_vector,
            "promotable_graph": promotable_graph,
            "vector_promoted": int(summary["vector_promoted_legacy"] or 0),
            "vector_promoted_tagged": int(tag_counts.get(VECTOR_PROMOTED_TAG, 0) or 0),
            "graph_promoted": int(tag_counts.get(GRAPH_PROMOTED_TAG, 0) or 0),
            "last_vector_promotion_at": summary["last_vector_promotion_at"],
        }
    finally:
        conn.close()


def _build_vector_record(row, namespace):
    """Build a Pinecone record from an ST row. Stable id = <ns>::st_<id_lower>."""
    record_id = f"{namespace}::{row['id'].lower()}"
    chunk_text = row["content"] or row["summary"] or ""
    if len(chunk_text) > 8000:
        chunk_text = chunk_text[:8000] + "\n\n[truncated...]"
    return {
        "_id": record_id,
        "chunk_text": chunk_text,
        "category": INTENT_CATEGORY.get(row["intent"], "reference"),
        "source_path": row["source_ref"] or f"st://record/{row['id']}",
        "promoted_by": row["agent_id"] or "auto-promote",
        "scope": WORKSPACE_SCOPE.get(row["workspace"], "home"),
        "tags": [
            namespace, row["intent"], row["kind"],
            f"st_id:{row['id']}", "promoted",
        ],
        "created_at": row["created_at"],
        # Phase 2 schema discipline (§ "Cross-cutting requirements")
        "source": "short_term",
        "tier": "vector",
        "promoted_from": row["id"],
        "promoted_at": _now_iso(),
        "boundary_kind": row.get("boundary_kind") or "legacy_no_provenance",
    }


def _upsert_one(record, namespace):
    """Write record JSON and call memory-lt upsert-vector. Returns (ok, payload)."""
    tmp_path = f"/tmp/promote_stvec_{record['_id'].replace('::', '__')}.json"
    with open(tmp_path, "w") as f:
        json.dump(record, f)
    rc, stdout, stderr = _run_cli([
        MEMORY_LT, "upsert-vector",
        "--namespace", namespace,
        "--json-file", tmp_path,
    ])
    try:
        archive_dir = "/tmp/agent-os-promote/archive"
        os.makedirs(archive_dir, exist_ok=True)
        archived = os.path.join(
            archive_dir,
            f"{os.path.basename(tmp_path)}.{_now_iso().replace(':', '').replace('-', '')}",
        )
        os.replace(tmp_path, archived)
    except OSError:
        pass
    if rc != 0:
        return False, {"error": stdout.strip() or stderr.strip() or f"rc={rc}"}
    try:
        return True, json.loads(stdout)
    except json.JSONDecodeError:
        return True, {"raw": stdout.strip()}


def cmd_auto_promote_st_vector(args):
    """Phase 2 Pipe 2 — auto-promote ST records → Pinecone vector."""
    intents = tuple(args.intent) if args.intent else PROMOTABLE_INTENTS
    rows = _candidate_rows(intents, args.limit)
    _heartbeat(
        f"start dry_run={args.dry_run} intents={list(intents)} "
        f"candidates={len(rows)} limit={args.limit}"
    )

    results = []
    upserted = skipped = errors = 0
    for row in rows:
        namespace = INTENT_NAMESPACE.get(row["intent"])
        if not namespace:
            skipped += 1
            _heartbeat(f"SKIP id={row['id']} reason=unrouted_intent intent={row['intent']}")
            continue

        # Guard: denied secret patterns in content/summary/source_ref.
        text_blob = " ".join([
            row.get("content") or "", row.get("summary") or "",
            row.get("source_ref") or "",
        ])
        denied = _check_denied_patterns(text_blob)
        if denied:
            skipped += 1
            _heartbeat(f"SKIP id={row['id']} reason=denied_pattern pattern={denied}")
            mark_ok = None
            mark_err = None
            if not args.dry_run:
                mark_ok, mark_err = _update_st_promote_state(
                    row["id"], "rejected", reason=f"denied_pattern:{denied}"
                )
            results.append({
                "id": row["id"],
                "action": "skip",
                "reason": f"denied:{denied}",
                "mark_ok": mark_ok,
                "mark_err": mark_err,
            })
            continue

        # Boundary tier routing.
        bk = (row.get("boundary_kind") or "").strip() or None
        if bk == "session":
            skipped += 1
            _heartbeat(f"SKIP id={row['id']} reason=session_boundary")
            results.append({
                "id": row["id"], "action": "skip", "reason": "session_boundary"
            })
            continue
        if bk == "memory":
            # 'memory' tier is graph-only — skip Pinecone path.
            skipped += 1
            _heartbeat(f"SKIP id={row['id']} reason=memory_tier_skip_pinecone")
            results.append({
                "id": row["id"], "action": "skip", "reason": "memory_tier_skip_pinecone"
            })
            continue
        # bk ∈ {brain, None} → normal vector path.

        record = _build_vector_record(row, namespace)

        if args.dry_run:
            results.append({
                "id": row["id"],
                "action": "dry_run",
                "namespace": namespace,
                "intent": row["intent"],
                "_id": record["_id"],
                "summary": (row["summary"] or "")[:80],
            })
            _heartbeat(f"DRY id={row['id']} ns={namespace} intent={row['intent']}")
            continue

        ok, payload = _upsert_one(record, namespace)
        if not ok:
            errors += 1
            _heartbeat(
                f"ERR id={row['id']} ns={namespace} err={payload.get('error', '?')}"
            )
            results.append({
                "id": row["id"], "action": "error",
                "namespace": namespace, "error": payload.get("error"),
            })
            # Don't crash — continue with next row (brief: "log and continue").
            time.sleep(args.sleep)
            continue

        # Mark short-term row promoted (stamps promoted_at automatically).
        mark_ok, mark_err = _update_st_promote_state(
            row["id"], "promoted", reason=f"auto_st_vector:{namespace}"
        )
        tag_ok, tag_err = _add_st_tag(row["id"], VECTOR_PROMOTED_TAG)
        upserted += 1
        _heartbeat(
            f"OK id={row['id']} ns={namespace} _id={record['_id']} "
            f"mark_ok={mark_ok} mark_err={mark_err or '-'} "
            f"tag_ok={tag_ok} tag_err={tag_err or '-'}"
        )
        results.append({
            "id": row["id"],
            "action": "promoted",
            "namespace": namespace,
            "_id": record["_id"],
            "mark_ok": mark_ok,
            "mark_err": mark_err,
            "tag_ok": tag_ok,
            "tag_err": tag_err,
        })
        time.sleep(args.sleep)  # rate limit

    summary = _promotion_health()
    summary.update({
        "action": "auto-promote-st-vector",
        "dry_run": args.dry_run,
        "candidates": len(rows),
        "upserted": upserted,
        "skipped": skipped,
        "errors": errors,
        "results": results,
    })
    _heartbeat(
        f"end upserted={upserted} skipped={skipped} errors={errors} "
        f"dry_run={args.dry_run}"
    )
    print(json.dumps(summary, indent=2))


def cmd_auto_promote_st_graph(args):
    """Batch-promote resolved ST rows into Neo4j."""
    intents = tuple(args.intent) if args.intent else PROMOTABLE_INTENTS + ("HELP", "VERIFICATION")
    rows = _graph_candidate_rows(intents, args.limit, replay=args.replay)
    _heartbeat(
        f"graph-start dry_run={args.dry_run} replay={args.replay} "
        f"intents={list(intents)} candidates={len(rows)} limit={args.limit}"
    )
    results = []
    promoted = skipped = errors = 0
    for row in rows:
        if args.dry_run:
            results.append({
                "id": row["id"],
                "action": "dry_run",
                "intent": row["intent"],
                "summary": (row["summary"] or "")[:80],
            })
            continue

        result = _promote_graph_record(row["id"], "auto_st_graph", mark_state=False)
        if result.get("ok") and not result.get("skipped") and not result.get("rejection"):
            promoted += 1
        elif result.get("ok"):
            skipped += 1
        else:
            errors += 1
        results.append(result)
        time.sleep(args.sleep)

    summary = _promotion_health()
    summary.update({
        "action": "auto-promote-st-graph",
        "dry_run": args.dry_run,
        "replay": args.replay,
        "candidates": len(rows),
        "promoted": promoted,
        "skipped": skipped,
        "errors": errors,
        "results": results,
    })
    _heartbeat(
        f"graph-end promoted={promoted} skipped={skipped} errors={errors} "
        f"dry_run={args.dry_run} replay={args.replay}"
    )
    print(json.dumps(summary, indent=2))


# ── Argument Parser ───────────────────────────────────────────────────────

def build_parser():
    parser = argparse.ArgumentParser(
        description="Promote short-term records or source files into long-term memory."
    )

    # Mode selection
    parser.add_argument(
        "--target", required=True,
        choices=["graph", "vector", "st-vector", "st-graph", "report"],
        help="Promotion target: 'graph' (Neo4j single record), "
             "'vector' (Pinecone file-based), or 'st-vector' "
             "(Phase 2 Pipe 2: batch auto-promote ST rows to Pinecone), "
             "'st-graph' (batch auto-promote ST rows to Neo4j), or "
             "'report' (promotion backlog and health report)"
    )

    # Graph mode args
    parser.add_argument("--short-term-id", default=None,
                        help="Short-term record ID (required for --target graph)")
    parser.add_argument("--reason", default=None,
                        help="Promotion reason (required for --target graph)")

    # Vector mode args
    parser.add_argument("--source-path", default=None,
                        help="Source file path (required for --target vector)")
    parser.add_argument("--namespace", default=None,
                        choices=sorted(ALLOWED_NAMESPACES),
                        help="Pinecone namespace (required for --target vector)")
    parser.add_argument("--scope", default=None,
                        choices=sorted(ALLOWED_SCOPES),
                        help="Workspace scope (required for --target vector)")
    parser.add_argument("--promoted-by", default=None,
                        help="Agent run_id (required for --target vector)")

    # st-vector (Pipe 2) args
    parser.add_argument("--dry-run", action="store_true", default=False,
                        help="Preview promotions without writing (st-vector)")
    parser.add_argument("--intent", action="append", default=None,
                        choices=list(PROMOTABLE_INTENTS),
                        help="Restrict to these intents (repeatable). "
                             "Default: all promotable intents.")
    parser.add_argument("--limit", type=int, default=100,
                        help="Max ST rows to process per run (st-vector)")
    parser.add_argument("--sleep", type=float, default=0.1,
                        help="Seconds to sleep between Pinecone upserts (rate limit)")
    parser.add_argument("--replay", action="store_true", default=False,
                        help="Include already graph-promoted ST rows (st-graph only)")

    return parser


# ── Main Entry Point ──────────────────────────────────────────────────────

def _is_legacy_call():
    """Detect whether argv is a legacy flat CLI call or a new subcommand call.

    Legacy: --target or --short-term-id appear as top-level args
            (before any positional argument that is a known subcommand).
    """
    # Scan argv for indicators
    for i, a in enumerate(sys.argv[1:], 1):
        if a.startswith("--"):
            if a == "--target":
                return True
            if a == "--short-term-id":
                return True
            continue
        # First positional: check if it's a known subcommand
        if a in SUBCOMMANDS:
            return False
        # Unknown positional with --target present somewhere → legacy
        if "--target" in sys.argv:
            return True
        # Default: subcommand mode (argparse will show help if no subcommand)
        return False
    return False


def _subcommand_main():
    """Route to proposals.py subcommand CLI.

    Delegates by re-executing the proposals.py module with the same argv
    (stripping the script name and inserting 'proposals.py' as the module).
    This avoids import overhead and keeps the two modules loosely coupled.
    """
    from proposals import cli as proposals_cli
    # Intercept sys.argv for the proposals CLI parser
    proposals_cli()


def main():
    if len(sys.argv) == 1 or any(arg in ("-h", "--help") for arg in sys.argv[1:]):
        build_parser().parse_args(sys.argv[1:])
        return
    # Public OSS distribution uses the flat CLI. Private proposal subcommands
    # are intentionally not shipped.
    if _is_legacy_call():
        _legacy_main()
    else:
        _legacy_main()


def _legacy_main():
    """Original flat CLI entry point (--target graph|vector|st-vector)."""
    parser = build_parser()
    args = parser.parse_args()

    if args.target == "graph":
        # Validate required graph args
        if not args.short_term_id:
            _fail_json("--short-term-id is required for --target graph")
        if not args.reason:
            _fail_json("--reason is required for --target graph")
        cmd_promote_graph(args.short_term_id, args.reason)

    elif args.target == "st-vector":
        cmd_auto_promote_st_vector(args)

    elif args.target == "st-graph":
        cmd_auto_promote_st_graph(args)

    elif args.target == "report":
        print(json.dumps(_promotion_health(), indent=2))

    elif args.target == "vector":
        # Validate required vector args
        if not args.source_path:
            _fail_json("--source-path is required for --target vector")
        if not args.namespace:
            _fail_json("--namespace is required for --target vector")
        if not args.scope:
            _fail_json("--scope is required for --target vector")
        if not args.promoted_by:
            _fail_json("--promoted-by is required for --target vector")
        cmd_promote_vector(args.source_path, args.namespace,
                           args.scope, args.promoted_by)

    else:
        _fail_json(
            f"Invalid target: {args.target}. "
            "Use 'graph', 'vector', 'st-vector', 'st-graph', or 'report'."
        )


if __name__ == "__main__":
    main()
