# Background

## Purpose

This page documents the design decisions, architectural rationale, and pitfalls of the Agent OS codebase.

## Design decisions

### Harness, not framework

Agent OS is designed as a harness rather than a framework. Frameworks are libraries you import and call into. A harness is what agents run on top of — it owns the outcome, learns from mistakes, and improves every cycle. This distinction drives every architectural choice: the system enforces protocols rather than providing optional utilities.

### Core-plus-adapters memory architecture

The memory system uses a core-plus-adapters pattern. SQLite provides always-on local storage, while Pinecone and Neo4j are optional adapters. This ensures zero-configuration operation by default while allowing users to add capabilities as needed. The adapter interfaces define clear integration points that commercial products can supersede without breaking the open-source core.

### Agent-agnosticism

Agent OS is deliberately agnostic about which AI agent runs on it. The ACP protocol and harness interfaces are model-agnostic. Claude Code, Codex, OpenCode, Pi, and future agents all participate as first-class citizens. This avoids lock-in and allows teams to use the best tool for each task.

### YAML-based registries

All tools, skills, workflows, agents, and memory tiers are defined in YAML registries under `registry/`. This makes the system's capabilities inspectable and machine-readable without requiring code execution. The registries are validated by `scripts/registry-check.py`.

### Gate-based validation

Instead of ad-hoc testing, Agent OS uses structured gates (privacy, release, clean-room) that must pass before changes are accepted. Each gate produces a pass/fail status with detailed output. This makes the release process auditable and repeatable.

## Pitfalls and danger zones

### ACP task queue on filesystem

The ACP task queue uses the filesystem for envelopes. This is simple and inspectable but means tasks are not durable across filesystem corruption. For production use, consider a proper message queue.

### SQLite WAL mode

The memory system uses SQLite WAL mode for performance. WAL files (`.sqlite-wal`, `.sqlite-shm`) can accumulate in crash scenarios. The health check does not currently monitor WAL file growth.

### Optional adapter detection

The system auto-detects Pinecone and Neo4j credentials at boot time. If credentials are present but the service is unreachable, the system falls back silently. This can mask configuration errors — the health check reports DEGRADED for optional tiers.

### Large skills

Some SKILL.md files (e.g., `acp/SKILL.md` at ~446 lines, `moe/SKILL.md` at ~306 lines) are large enough to consume significant token budget. The `skill-pack` tool can extract bounded context packs, but the default skill loading does not cap size.

## Key source files

| File | Purpose |
|---|---|
| `COMMERCIAL_BOUNDARY.md` | Open-core vs commercial boundary |
| `PRIVACY_BOUNDARY.md` | Privacy boundary and exclusion policy |
| `RELEASE_READINESS.md` | Release readiness documentation |
| `docs/SYSTEM_ARCHITECTURE_SOURCE_OF_TRUTH.md` | Canonical architecture reference |
| `EXPORT_MANIFEST.yaml` | Allowlist-based export manifest |
