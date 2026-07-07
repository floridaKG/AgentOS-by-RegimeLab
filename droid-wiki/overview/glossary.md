# Glossary

## A

**ACP (Agent Communication Protocol)** — A durable task ledger that tracks agent work from queue to completion. Each task has a run directory with objective, state, timestamps, and append-only transition log.

**ACP daemon** — Background process (`bin/acp-daemon`) that watches for new task envelopes and dispatches them to the configured agent runtime.

**ACPx** — Universal agent launcher (MIT, `npm install -g acpx`) that provides cooperative cancellation, named parallel sessions, crash reconnect, and cross-model DAG orchestration.

**Agent harness** — The component that launches the selected agent runtime with the right tools and context.

**Agent OS** — An agent-agnostic harness that provides shared memory, dispatch protocols, workspace routing, and enforced governance for AI coding agents.

**Agent Voice** — An append-only insight buffer (`bin/agent-voice`) for agents to self-report friction, improvement ideas, and risks.

## B

**BOOT_FACTS.yaml** — A YAML file read by every agent on session start containing session state, required reads, and role assignments.

## C

**CodeGraph** — A pre-indexed code knowledge graph (MIT, `npm install -g @codegraph/cli`) that answers structural code questions using Tree-sitter and SQLite.

**Citation** — Source attribution tracking for memory records, implemented in `memory/core/citation.py`.

## D

**Droid** — A proprietary agent runtime supported by the ACP protocol. Droid
requires either a Factory subscription or bring-your-own-key (BYOK)
configuration. See the README for supported agent options.

## E

**Envelope** — A task request packet in the ACP system, written to the filesystem by `acp-task` and picked up by the daemon.

## F

**FTS5** — SQLite full-text search engine, used by the short-term memory system for keyword-based recall.

## G

**Gate** — A validation script in the release pipeline. Agent OS has privacy gates, release gates, and clean-room gates that verify correctness before publication.

**Graph memory** — Optional Neo4j-based memory tier for relationship-based queries and provenance tracking.

## H

**Hard rules** — Machine-readable enforced rules (`registry/hard_rules.yaml`) that agents must follow, including prohibitions on committing secrets, using `rm`, and using relative paths.

**Harness** — The operating system that agents run on, as opposed to a framework (imported library). Agent OS is a harness.

## I

**Injection** — The process of building task-specific memory context from stored records, implemented in `memory/core/inject.py`.

## L

**Lesson** — A reusable insight captured to durable memory. Lessons have intents like LESSON, STUMBLE, DECISION, and CONFIRMED.

**Ledger** — The append-only task transition log in the ACP system, implemented in `memory/core/ledger.py`.

## M

**Memory profiles** — Predefined combinations of memory tiers: Local/Core (SQLite only), Semantic (+ Pinecone), Graph (+ Neo4j), and Full (all three).

**Memory tier** — A storage backend in the memory system. Agent OS has short-term (SQLite), semantic (Pinecone), and graph (Neo4j) tiers.

**MOE (Mixture of Experts)** — Multi-provider parallel panel system (`bin/team`) that dispatches tasks to multiple LLM providers and synthesizes results.

## P

**Promotion** — The process of validating and moving short-term memory records to long-term storage (Pinecone and/or Neo4j).

## R

**Recall** — The process of querying memory tiers for relevant context, merging results into a unified response.

**Registry** — YAML files in `registry/` that define available tools, skills, workflows, agents, memory tiers, and MCP servers.

**Run** — A single task execution tracked by the ACP ledger, with its own directory containing objective, state, and transitions.

## S

**Semantic memory** — Optional Pinecone-based vector search tier for cross-session similarity recall.

**Session** — An agent working session, tracked by the memory system for context and continuity.

**Short-term memory** — The always-on SQLite memory tier that records recent activity, lessons, stumbles, decisions, and tool output.

**Skill** — A reusable capability definition in `skills/shared/`, written as a SKILL.md file with triggers, description, and instructions.

**SuperDocs** — An optional documentation harness for any project, providing a structured `docs/` tree that agents can navigate and maintain.

## V

**Vault OS** — A user-owned Markdown knowledge workspace for storing structured notes, research, and agent-readable content.

## W

**Workspace** — A user-created directory with its own AGENTS.md entrypoint, tool policy, and memory scope. Each workspace isolates its lessons and rules from others.

**Workspace router** — The component that detects the active workspace, reads its rules, classifies the task, and builds a scoped context bundle.
