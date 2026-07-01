# Session

## Overview

A session in Agent OS represents a single agent working session — the lifecycle from boot to completion. Sessions are the basic unit of agent activity and are tracked in the short-term memory system for recall, compression, and durable knowledge extraction.

## Session lifecycle

An agent session follows this lifecycle:

1. **Boot** — The agent starts via `agent-os-boot.sh`, which identifies the workspace surface, required reads, and current state.
2. **Work** — The agent executes tasks within the session context, producing a stream of messages (turns).
3. **Session compression** — On completion, `session_compress.py` distills the session into durable facts.
4. **Memory persistence** — Generated facts are appended to `memory.md` and optionally upserted to Pinecone.
5. **Recall** — Past sessions inform future sessions through the recall system.

## Session tracking in memory

Sessions are tracked in the short-term memory SQLite database via the `st_records` table. Each session produces records with:

| Field | Purpose |
|---|---|
| `run_id` | Identifies the session run |
| `agent_id` | Which agent executed the session |
| `workspace` | The workspace context |
| `intent` | The session's primary intent (e.g., LESSON, OBSERVATION) |
| `kind` | Record type (e.g., observation, state, stumble) |

The `st_packet_context` table stores per-run context for memory injection before agent launch, providing relevant past knowledge when a new session begins.

## Session compression

The session compressor (`memory/core/session_compress.py`) is the bridge between raw session transcripts and durable knowledge. It implements:

### Entry points

- **Plugin mode** — `compress_session(messages, session_id)` called live on `on_session_end`
- **CLI modes** — `backfill` scans session files for unseen sessions; `replay-queue` drains the pending retry queue

### Compression pipeline

1. **Threshold check** — Sessions under `MIN_TURNS` (default 50) are skipped
2. **Truncation** — Sessions exceeding context limits keep the first `HEAD_KEEP` (10) and last `TAIL_KEEP` (30) turns
3. **LLM compression** — An LLM call (via `opencode-go` with fallback models) distills the transcript into 3-5 durable facts
4. **Memory.md append** — Facts are written as a dated block to `memory.md`
5. **Pinecone upsert** — Each fact is upserted as a vector (category=insight, source=session-summary)
6. **Failure queue** — On any failure, the session is queued to `pending_summaries.jsonl` for retry

### Key constraints

| Constant | Value | Purpose |
|---|---|---|
| `MIN_TURNS` | 50 | Skip sessions too short to yield durable facts |
| `HEAD_KEEP` | 10 | Leading turns to preserve |
| `TAIL_KEEP` | 30 | Trailing turns to preserve |
| `MAX_FACTS` | 5 | Maximum facts per session |
| `MIN_FACTS` | 3 | Minimum facts (below this returns empty) |
| `MAX_CHARS_PER_MSG` | 1200 | Per-message truncation limit |

### Cursor management

The compressor tracks processed sessions via `session_compress_cursor.json` to avoid reprocessing. Sessions older than `max-age-days` are marked as seen without compression to prevent stale facts from poisoning memory.

## Session context for recall

When a new session begins, the `st_packet_context` table provides relevant past context:

- Past records matching the current workspace and intent are injected into the agent's context
- The `token_budget` field controls how much context is injected
- Packet context is written via `memory-inject` and queried via `memory-recall`

## Key files

| File | Purpose |
|---|---|
| `memory/core/session_compress.py` | Session compression pipeline |
| `memory/core/short_term.py` | Short-term memory backend with session record support |
| `memory/core/promote.py` | Promotion of session-derived facts to long-term storage |
| `memory/core/inject.py` | Context injection for new sessions |
| `memory/core/recall_hook.py` | Recall hook that surfaces past session context |
| `scripts/agent-os-boot.sh` | Session boot routing |
