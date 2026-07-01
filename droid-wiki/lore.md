# Lore

## Eras

### Foundation (pre-2026)

Agent OS was built as a private harness for orchestrating multiple AI coding agents across workspaces. The core design principles - agent-agnosticism, cross-agent memory, enforced protocols - were established during this period. The system was designed from the start as a harness, not a framework, with the insight that frameworks are libraries you import while a harness is the OS agents run on.

### Open-source publication (Jun 2026)

In late June 2026, Agent OS was published as open source under Apache 2.0. This involved:

- Extracting and curating a public subset of the codebase
- Building the EXPORT_MANIFEST.yaml allowlist system
- Implementing privacy gates (`tests/privacy/privacy_gate.sh`) to ensure no private data leaked
- Creating clean-room installation tests (`tests/clean-room/install_and_verify.sh`)
- Writing comprehensive documentation (SETUP.md, PRIVACY_BOUNDARY.md, COMMERCIAL_BOUNDARY.md)
- Adding the `RELEASE_READINESS.md` and release gate scripts

## Longest-standing features

The **memory system** is the oldest and most stable subsystem. Its architecture - SQLite core with optional Pinecone and Neo4j adapters - has survived multiple iterations. The facade pattern in `bin/` (lightweight shell wrappers delegating to Python implementations) is another enduring design choice.

## Deprecated features

- **NOW.md** - Archived on 2026-05-31. Was used as a runtime state document. Replaced by structured memory tiers and the `BOOT_FACTS.yaml` system.
- **Hindsight** — An advanced memory feature involving local conversation extraction and fact proposal. Shipped in `memory/hindsight_bridge.py` — requires a Hermes + Hindsight API backend.

## Major rewrites

The open-source publication (Jun 2026) was the largest restructuring of the repository. Before publication, the codebase existed as two private repositories (`agent-os` runtime and `agent-os-docs`). These were merged, curated, and staged through an allowlist-based export system (`EXPORT_MANIFEST.yaml`) into the public repository.

## Growth trajectory

The public repository represents a curated subset of the larger Agent OS ecosystem. The core components shipped in v1 include:
- SQLite-based local memory system
- 10 curated shared skills
- 19 CLI entry points
- 23 scripts
- 9 registry files
- Vault OS and SuperDocs example scaffolds
- Comprehensive test and gate infrastructure
