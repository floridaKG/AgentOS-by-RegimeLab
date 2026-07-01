# Record

## Overview

A record is the fundamental unit of memory in Agent OS. Records capture lessons, stumbles, decisions, observations, and other state that agents produce during their work. Records flow through a lifecycle from capture to optional long-term promotion.

## Memory record schema

Records are stored in the `st_records` table of the short-term memory SQLite database (`schema_short_term.sql`). The schema is defined as follows:

| Column | Type | Description |
|---|---|---|
| `id` | TEXT (PK) | Auto-generated unique ID (format: `st_YYYYMMDD_XXXXXX`) |
| `run_id` | TEXT | Identifies the session run that produced the record |
| `message_id` | TEXT | Optional message-level identifier |
| `agent_id` | TEXT | The agent that created the record |
| `workspace` | TEXT | Workspace context (home, project-a, project-b, vault) |
| `intent` | TEXT | The record's intent classification |
| `kind` | TEXT | The record's kind (observation, stumble, etc.) |
| `content` | TEXT | Full content body |
| `summary` | TEXT | Condensed summary (indexed by FTS5) |
| `source_ref` | TEXT | Reference to the source (e.g., cli:xxx, file://path) |
| `status` | TEXT | Lifecycle status (active, resolved, superseded, discarded) |
| `promote_state` | TEXT | Promotion stage (none, candidate, promoted, rejected, proposed, approved) |
| `fingerprint` | TEXT | Optional SHA-256 deduplication hash |
| `created_at` | TEXT | ISO-8601 UTC creation timestamp |
| `updated_at` | TEXT | ISO-8601 UTC last-updated timestamp |
| `promoted_at` | TEXT | ISO-8601 UTC promotion timestamp (set when promoted) |
| `boundary_kind` | TEXT | Boundary tier (session, memory, brain) for enforcement |

### Additional tables

| Table | Purpose |
|---|---|
| `st_records_fts` | FTS5 virtual table for full-text search on `content` and `summary` |
| `st_tags` | Many-to-many tag associations (`record_id`, `tag`) |
| `st_help_requests` | Dedicated schema for unresolved HELP requests |
| `st_packet_context` | Per-run context for memory injection before agent launch |
| `st_decisions` | Stumble triage decisions keyed by fingerprint |

## Supported intents

Records must carry one of the following intents:

| Intent | Purpose |
|---|---|
| `OBSERVATION` | A neutral observation about the system or work |
| `LESSON` | A reusable lesson learned |
| `DECISION` | A design or implementation decision |
| `STUMBLE` | A problem, pitfall, or error encountered |
| `CONFIRMED` | A fact or pattern that was verified |
| `OPS` | Operational state or run tracking |
| `HELP` | A request for assistance |
| `VERIFICATION` | A verification result |
| `STATE` | System or agent state snapshot |
| `LEARNING` | A learning about tooling, process, or techniques |
| `IMPLEMENT` | An implementation action |
| `BUG` | A bug report or finding |
| `SPEC` | A specification reference |
| `DOCS` | A documentation reference |
| `RESEARCH` | A research finding |

### Supported kinds

Records are further classified by kind:

`packet_summary`, `status`, `observation`, `stumble`, `confirmed`, `help_request`, `help_resolution`, `verification`, `state`

## Record lifecycle

A record progresses through these stages:

```
Capture → Filter → Promote → Prune
```

### 1. Capture

Records are created via the `memory-st write` CLI command. Required parameters include `--run-id`, `--agent-id`, `--workspace`, `--intent`, `--kind`, `--summary`, `--content-file`, and `--source-ref`.

### 2. Filter

Records are subject to validation:

- **Intent and kind** must be from the allowed sets
- **Boundary tier enforcement** — brain-tier writes require `--evidence-ref` or `--justify-no-evidence`
- **Content file** must exist and be readable

### 3. Promote

Records can be promoted to long-term storage:

| State | Meaning |
|---|---|
| `none` | Default state, not yet considered for promotion |
| `candidate` | Marked as promotion candidate via `memory-st mark-candidate` |
| `proposed` | Proposed for promotion (via `set-promote-state`) |
| `approved` | Promotion approved (via `set-promote-state`) |
| `promoted` | Successfully promoted to long-term storage |
| `rejected` | Promotion rejected; not suitable for long-term storage |

Promotion involves:

- **Denied pattern check** — Content is scanned for credential patterns (`.ssh/`, `.env`, `_ed25519`, etc.)
- **Unverified guess detection** — Hedging language (maybe, might, could be, I think) is flagged
- **Raw transcript detection** — Content that looks like a chat transcript is rejected
- **Duplicate detection** — Same fingerprint already promoted causes rejection
- **Vault folder allowlist** — Vault content must be under allowed prefixes

### 4. Prune

Records reach terminal statuses:

| Status | Meaning |
|---|---|
| `active` | Record is live and relevant |
| `resolved` | Issue resolved or lesson applied |
| `superseded` | Superseded by a newer record |
| `discarded` | Invalid or no longer relevant |

## Fingerprinting

The `promote.py` module computes fingerprints as deterministic SHA-256 hashes:

```python
raw = f"{content}|||{summary}|||{source_ref}"
fingerprint = hashlib.sha256(raw.encode("utf-8")).hexdigest()
```

Fingerprints enable:

- **Deduplication** — The same lesson captured by different agents produces the same hash
- **Triage decisions** — `st_decisions` table maps fingerprints to fix/guardrail/document/ignore outcomes
- **Lookup** — `memory-st get-by-fingerprint` retrieves records by fingerprint

## Tagging

Tags provide flexible metadata beyond the fixed schema fields. They are stored in the `st_tags` table as key-value pairs (`record_id`, `tag`). Tags are added via `memory-st add-tag --id <record-id> --tag <tag>` and are used for:

- Evidence references (`evidence_ref:path/to/file`)
- Justification markers (`justify_no_evidence:reason`)
- Promotion reasons (`promote_reason:reason`)
- Custom categorization

## Key files

| File | Purpose |
|---|---|
| `memory/core/short_term.py` | Short-term memory backend, record CRUD |
| `memory/core/promote.py` | Promotion logic, filtering, validation |
| `memory/core/schema_short_term.sql` | SQLite schema definition |
| `memory/core/ledger.py` | Ledger for promotion audit trail |
