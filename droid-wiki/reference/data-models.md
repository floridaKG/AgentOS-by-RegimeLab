# Data models

## Overview

This page documents the key data structures used across Agent OS, organized by subsystem. All schemas are based on the canonical source files in `memory/core/` and `registry/`.

## Memory record schema

Source: `memory/core/schema_short_term.sql`

### st_records

The primary table for all short-term memory records.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | TEXT | PRIMARY KEY | Auto-generated unique ID (`st_YYYYMMDD_XXXXXX`) |
| `run_id` | TEXT | NOT NULL | Session run identifier |
| `message_id` | TEXT | — | Optional message-level ID |
| `agent_id` | TEXT | NOT NULL | Creating agent |
| `workspace` | TEXT | NOT NULL | Workspace context |
| `intent` | TEXT | NOT NULL | Intent classification |
| `kind` | TEXT | NOT NULL | Record kind |
| `content` | TEXT | NOT NULL | Full content body |
| `summary` | TEXT | NOT NULL | Condensed summary |
| `source_ref` | TEXT | NOT NULL | Source reference |
| `status` | TEXT | NOT NULL | Lifecycle status |
| `promote_state` | TEXT | NOT NULL DEFAULT 'none' | Promotion stage |
| `fingerprint` | TEXT | — | SHA-256 dedup hash |
| `created_at` | TEXT | NOT NULL | ISO-8601 creation timestamp |
| `updated_at` | TEXT | NOT NULL | ISO-8601 update timestamp |
| `promoted_at` | TEXT | — | ISO-8601 promotion timestamp |
| `boundary_kind` | TEXT | — | Boundary tier (session/memory/brain) |

### st_records_fts

FTS5 virtual table for full-text search.

| Column | Type | Notes |
|---|---|---|
| `id` | TEXT (UNINDEXED) | References `st_records.id` |
| `content` | TEXT | Indexed full content |
| `summary` | TEXT | Indexed summary |

Tokenizer: `porter` (Porter stemming algorithm).

### st_tags

Many-to-many tag associations.

| Column | Type | Constraints |
|---|---|---|
| `record_id` | TEXT | NOT NULL, FK → st_records(id) ON DELETE CASCADE |
| `tag` | TEXT | NOT NULL |
| PRIMARY KEY | — | (record_id, tag) |

### st_help_requests

Dedicated table for unresolved HELP requests.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | TEXT | PRIMARY KEY | References `st_records.id` |
| `run_id` | TEXT | NOT NULL | Session run |
| `message_id` | TEXT | NOT NULL | Message ID |
| `parent_agent` | TEXT | NOT NULL | Parent agent |
| `requesting_agent` | TEXT | NOT NULL | Agent requesting help |
| `workspace` | TEXT | NOT NULL | Workspace context |
| `uncertainty_type` | TEXT | NOT NULL | Type of uncertainty |
| `question` | TEXT | NOT NULL | The help question |
| `recommended_default` | TEXT | NOT NULL | Suggested default action |
| `status` | TEXT | NOT NULL | active or resolved |
| `resolution_record_id` | TEXT | — | Link to resolution record |
| `created_at` | TEXT | NOT NULL | ISO-8601 timestamp |
| `updated_at` | TEXT | NOT NULL | ISO-8601 timestamp |

### st_packet_context

Per-run context for memory injection before agent launch.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `packet_run_id` | TEXT | PRIMARY KEY | Run identifier |
| `workspace` | TEXT | NOT NULL | Workspace context |
| `intent` | TEXT | NOT NULL | Intent classification |
| `query` | TEXT | NOT NULL | Search query |
| `context_json` | TEXT | NOT NULL | JSON context payload |
| `token_budget` | INTEGER | NOT NULL | Token limit for injection |
| `created_at` | TEXT | NOT NULL | ISO-8601 timestamp |

### st_decisions

Stumble triage decisions keyed by fingerprint.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `fingerprint` | TEXT | PRIMARY KEY | SHA-256 of content |
| `decision` | TEXT | NOT NULL | fix, guardrail, document, ignore |
| `note` | TEXT | — | Decision rationale |
| `decided_at` | TEXT | NOT NULL | ISO-8601 timestamp |
| `decided_by` | TEXT | — | Deciding agent |
| `spec_path` | TEXT | — | Related spec document |

## Memory tier schema

Source: `registry/memory_tiers.yaml`

| Field | Type | Description |
|---|---|---|
| `id` | string | Tier identifier |
| `layer` | string | Short-term, long-term-vector, long-term-graph |
| `backend` | string | Database or service name |
| `path` | string | Storage path or service URI |
| `scope` | string | What kind of data this tier stores |
| `write_via` | string | CLI command for writing |
| `read_via` | string | CLI command for reading |
| `status` | string | core or optional |
| `notes` | string | Additional details and requirements |

## Skill registry schema

Source: `registry/skills.yaml`

| Field | Type | Description |
|---|---|---|
| `name` | string | Skill identifier (matches SKILL.md id) |
| `tier` | string | Availability tier (os-shared, workspace-*, personal) |
| `status` | string | active, planned, deprecated, archived |
| `path` | string | Path to SKILL.md file |
| `trigger` | list | Trigger phrases for relevance matching |
| `description` | string | One-line description |
| `user_invocable` | bool | Direct user invocation allowed |

## Tool registry schema

Source: `registry/tools.yaml`

| Field | Type | Description |
|---|---|---|
| `id` | string | Tool identifier |
| `binary` | string | Path or name of the executable |
| `purpose` | string | What the tool does |
| `invocation` | string | Example invocation |

## Workflow schema

Source: `registry/workflows.yaml`

| Field | Type | Description |
|---|---|---|
| `name` | string | Workflow identifier |
| `description` | string | What the workflow does |
| `triggered_by` | string | How the workflow is triggered |
| `steps` | list | Ordered list of actions |
| `status` | string | active or draft |

## Agent schema

Source: `registry/agents.yaml`

| Field | Type | Description |
|---|---|---|
| `id` | string | Agent identifier |
| `description` | string | One-line capability summary |
| `invocation_template` | string | CLI template with `{{prompt}}`/`{{model}}` |
| `role_strengths` | list | Roles this agent excels at |
| `use_when` | string | When to dispatch to this agent |

## Hard rule schema

Source: `registry/hard_rules.yaml`

| Field | Type | Description |
|---|---|---|
| `id` | string | Stable unique slug |
| `rule` | string | Plain text directive or prohibition |
| `rationale` | string | Why the rule exists |
| `scope` | list | Affected workspaces (or "all") |
| `severity` | string | blocking, warning, suggestion |
| `status` | string | active, draft, deprecated |

## ACP task envelope

The ACP (Agent Communication Protocol) uses filesystem-based envelopes for task dispatch. The envelope structure is a JSON file with:

| Field | Type | Description |
|---|---|---|
| `id` | string | Unique task identifier |
| `role` | string | Target role (explorer, architect, etc.) |
| `workspace` | string | Target workspace |
| `prompt` | string | Task description |
| `status` | string | Queued, claimed, running, succeeded, failed |
| `created_at` | string | ISO-8601 timestamp |
| `claimed_at` | string | When a daemon claimed the task |
| `completed_at` | string | When the task completed |
| `result` | object | Task result payload |

## Key files

| File | Purpose |
|---|---|
| `memory/core/schema_short_term.sql` | SQLite schema (source of truth) |
| `memory/core/schema_neo4j.cypher` | Neo4j graph schema |
| `registry/*.yaml` | All registry schemas |
