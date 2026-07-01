# Agent OS - Architecture

> This document describes how Agent OS works. For installation, see `SETUP.md`.

Agent OS is an **agent-agnostic harness** - the OS that AI coding agents run on.
It provides shared memory, dispatch protocols, workspace routing, and enforced
governance so agents don't start every session cold.

## North Star

Agent OS exists to be the best agent-agnostic harness available.

- **Agent-agnostic.** Any agent (Claude Code, Codex, Pi, Hermes, OpenCode, Droid)
  participates as a first-class citizen. New models slot in without rewiring.
- **Cross-agent memory.** Every agent contributes to shared memory. Stumbles are
  captured, reviewed, and promoted so all agents learn together.
- **Multi-agent, multi-provider.** Agents call each other through ACP. Providers
  are swappable. No lock-in at any layer.
- **Enforced protocols.** The harness enforces document creation, maintenance,
  lifecycle, and memory promotion rules so agents don't rediscover them.
- **Agent voice.** Agents report gaps and friction. The system listens and improves.

This is a **harness**, not a framework. Frameworks are libraries you import.
The harness owns the outcome, learns from mistakes, and improves every cycle.

## Four Main Components

| Component | Role | Why It Matters |
|---|---|---|
| **Workspace Router** | Detects the active workspace and loads its rules | Prevents one domain's assumptions from contaminating another |
| **Memory Layer** | Combines short-term events, semantic search, and graph relationships | Gives agents relevant context without dumping full history |
| **ACP (Agent Communication Protocol)** | Durable task ledger from queue to completion | Makes agent work resumable, inspectable, and auditable |
| **Agent Harness** | Launches the selected agent runtime with the right tools and context | Different models and CLIs handle the work they're best suited for |

## Request Flow

1. **Task arrives** - user asks a question, files a job, or resumes work
2. **Route** - workspace rules and task type are detected
3. **Recall** - relevant memory is queried and merged into a context bundle
4. **Dispatch** - the right role, model, and tools are selected
5. **Capture** - useful outcomes are recorded for later promotion

## Workspace Routing

Each workspace has its own boot contract, tool policy, and memory scope. When an
agent starts, the router detects the current directory, reads the matching rules,
classifies the task, and builds a scoped context bundle.

This separation is the main safety feature. A lesson from one codebase must not
silently become guidance for another.

## Memory Layer

The memory layer captures candidate facts during work, keeps recent events close,
and promotes selected knowledge into longer-lived stores.

| Tier | Backend | Default | Purpose |
|---|---|---|---|
| Short-Term | SQLite (local) | **Always on** | Recent activity, lessons, stumbles, tool output |
| Semantic | Pinecone (optional) | Off | Vector search for cross-session recall |
| Graph | Neo4j (optional) | Off | Entity relationships, provenance, source tracking |
| Advanced | Hindsight | Ships — requires Hermes + Hindsight API | Local conversation extraction and fact proposal via `memory/hindsight_bridge.py` |

### Memory Profiles

| Profile | Components | Use Case |
|---|---|---|
| **Local/Core** | SQLite only | Default. Works offline, zero external services |
| **Semantic** | SQLite + Pinecone | Cross-session semantic recall |
| **Graph** | SQLite + Neo4j | Relationship-based memory queries |
| **Full** | All three | Maximum capabilities |

### Promotion Pipeline

During a session, the system records candidate observations. Promotion jobs
compress conversations into durable facts, deduplicate near-matches, attach
provenance, and write only useful pieces into longer-term memory.

1. **Capture** - facts, tool events, errors, outcomes recorded close to session
2. **Filter** - compress, deduplicate, classify
3. **Promote** - stable facts written to semantic/graph memory or source docs
4. **Prune** - long-term memory stays curated, not an unbounded dump

## ACP: Agent Communication Protocol

ACP is the durable task ledger. Each task gets a run directory with its objective,
current state, timestamps, and append-only transition log.

```
queued -> claimed -> running -> review/resume -> succeeded | failed | cancelled
```

This makes agent work resumable, inspectable, cancelable, and auditable.

### Agent Roles

| Role | Purpose | Model Profile |
|---|---|---|
| Explorer | Research and codebase discovery | Fast, broad context |
| Architect | Design and specification writing | High reasoning, structured output |
| Executor | Implementation and focused changes | Balanced speed and accuracy |
| Reviewer | Quality gates and skeptical review | Careful, detail-oriented |
| Escalation | Hard tasks cheaper models can't finish | Higher capability, selective use |

### ACPx (Universal Agent Launcher)

ACPx (`acpx`, MIT, `npm install -g acpx`) is the universal ACP agent driver.
It provides:

- Cooperative cancellation of running tasks
- Prompt queueing with named parallel sessions
- Crash reconnect with session recovery
- Structured JSON output for all supported agent types
- Cross-model DAG orchestration via flow definitions

### CodeGraph (Code Structure Queries)

CodeGraph (`@codegraph/cli`, MIT, `npm install -g @codegraph/cli`) is a
pre-indexed code knowledge graph (Tree-sitter to SQLite). It answers structural
questions in a single query instead of 5-15 grep/read chains:

- "Who calls function X?" -> `codegraph callers`
- "What does X call?" -> `codegraph callees`
- "What breaks if I change X?" -> `codegraph impact`
- "How does X reach Y?" -> `codegraph trace`

## Agent Runtime

The harness can launch different agent runtimes depending on the task. The key
design choice: task state, workspace rules, and memory context live outside any
single model provider. The runtime is replaceable.

## Resilience

- **Idempotent jobs:** indexers and promotion can rerun safely
- **Source-first:** indexed data can be rebuilt from source documents
- **Partial failure tolerance:** if one memory tier is down, others continue
- **Retry queues:** failed compression/promotion replays later
- **Prunable memory:** curated, not untouchable archive

## Commercial Boundary

Agent OS is published under Apache 2.0 (see `LICENSE`). The full harness
is free and open source. The following capabilities are reserved for managed
or commercial product offerings (not OSS license restrictions):

| Open-core (Apache 2.0) | Managed / Commercial Products |
|---|---|
| Personal use | Production deployments |
| Internal development | Paid redistribution |
| Evaluation | Hosted memory plane |
| | Managed governance, SSO, compliance |

## Putting It Together

1. Route the task to the right workspace
2. Recall only relevant context (not everything)
3. Dispatch the right agent for the job
4. Track work in the ACP ledger
5. Capture candidate lessons
6. Promote the useful ones
7. Keep the rest disposable

The result: agents start with better context each time without memory becoming
an unbounded transcript dump.
