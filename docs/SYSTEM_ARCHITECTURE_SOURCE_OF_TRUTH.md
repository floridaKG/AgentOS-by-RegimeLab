# System Architecture Source of Truth (SAST)

> Canonical reference for Agent OS architecture. All other docs
> must justify their existence against this document.

## Core Principle

Agent OS is an agent-agnostic harness — the operating system that AI
coding agents run on. It is not a framework (imported library) but a
harness that owns the outcome, learns from mistakes, and improves
every cycle.

## Components

| Component | Role | Why It Matters |
|---|---|---|
| **Workspace Router** | Detects active workspace, loads its rules | Prevents cross-domain contamination |
| **Memory Layer** | Short-term + optional semantic + graph | Gives agents relevant context without full history |
| **ACP (Agent Communication Protocol)** | Durable task ledger | Makes agent work resumable, inspectable, auditable |
| **Agent Harness** | Launches agent runtime with right tools/context | Different models do the work they're best suited for |

## Request Flow

```
Task arrives → Route → Recall → Dispatch → Capture
```

1. **Task arrives** — user asks, files a job, or resumes work
2. **Route** — workspace rules and task type detected
3. **Recall** — relevant memory queried and merged into context bundle
4. **Dispatch** — right role, model, and tools selected
5. **Capture** — useful outcomes recorded for later promotion

## Memory Tiers

| Tier | Backend | Default | Purpose |
|---|---|---|---|
| Short-Term | SQLite | Always on | Recent activity, lessons, stumbles, tool output |
| Semantic | Pinecone | Optional | Vector search for cross-session recall |
| Graph | Neo4j | Optional | Entity relationships, provenance, source tracking |

### Memory Profiles

- **Local/Core** — SQLite only. Works offline, zero external services.
- **Semantic** — SQLite + Pinecone. Cross-session semantic recall.
- **Graph** — SQLite + Neo4j. Relationship-based memory queries.
- **Full** — All three. Maximum capabilities.

### Promotion Pipeline

```
Capture → Filter → Promote → Prune
```

## ACP Dispatch Flow

ACP is the durable task ledger. Each task has a run directory with
objective, current state, timestamps, and append-only transition log.

```
queued → claimed → running → review/resume → succeeded | failed | cancelled
```

### Agent Roles

| Role | Purpose | Model Profile |
|---|---|---|
| Explorer | Research and codebase discovery | Fast, broad context |
| Architect | Design and specification writing | High reasoning, structured |
| Executor | Implementation and focused changes | Balanced speed/accuracy |
| Reviewer | Quality gates and skeptical review | Careful, detail-oriented |
| Escalation | Hard tasks cheaper models cannot finish | Higher capability, selective |

## Resilience

- Idempotent jobs — indexers and promotion rerun safely
- Source-first — indexed data rebuildable from source documents
- Partial failure tolerance — one tier down, others continue
- Retry queues — failed compression/promotion replay later
- Prunable memory — curated, not unbounded archive

## Source of Truth Boundaries

- Runtime: `$AGENT_OS_HOME/`
- Docs: `$AGENT_OS_HOME/docs/`
- Registry: `$AGENT_OS_HOME/registry/`
