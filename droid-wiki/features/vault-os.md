# Vault OS

## Purpose

Vault OS is a user-owned Markdown knowledge workspace that provides structure and conventions for organizing research, insights, sources, and operational workflows. It is designed for users who want to maintain a personal or team knowledge base that is independent of any specific agent runtime. The open-source scaffold provides the structure without prescribing a research domain or shipping private domain skills.

## How it works

A vault is created by running `init-vault.sh`, which scaffolds the directory structure from the skeleton at `examples/vault-os/` and writes the vault path to `~/.config/agent-os/config.env` as `VAULT_PATH`. The vault can be created fresh (`--create <path>`) or linked to an existing directory (`--link <path>`).

### Vault structure

| Directory | Purpose |
|-----------|---------|
| `capture/` | Unprocessed notes and source material awaiting classification |
| `sources/` | Normalized source records describing where information came from |
| `insights/` | Atomic, reusable claims or observations linked to their sources |
| `maps/` | Topic maps and indexes that connect related insights |
| `ops/` | Workflows, decisions, and maintenance records |
| `registry/` | Optional user-defined skills and workflows |

### Wiki-style linking

Vault OS supports Obsidian-compatible wikilink syntax (`[[wikilink]]`) for cross-referencing notes. This allows users to link between insights, sources, and maps using standard Markdown wiki notation. The vault is designed to be browsed with any Markdown editor that supports wikilinks.

### Glossary

| Term | Definition |
|------|------------|
| Capture | Unprocessed source material or a note awaiting classification |
| Source | A normalized record describing where information came from |
| Insight | An atomic, reusable claim or observation linked to its source |
| Map | An index or synthesis page that connects related insights |
| Provenance | The source identity and processing history that support a note |
| Workflow | A user-defined sequence for capturing, processing, validating, or reviewing vault content |

### Scaffold files

The `examples/vault-os/` directory contains:

- `README.md` — overview and quick start instructions
- `BOOT.md` — entry point for agents navigating the vault
- `AGENTS.md` — agent entrypoint instructions (in the parent superdocs scaffold)
- `GLOSSARY.md` — vault terminology reference
- `SKILLS_INDEX.md` — index of vault-specific skills
- `REFERENCE.md` — reference documentation
- `agent_manifest.yaml` — agent configuration manifest
- `registry/skills.yaml` — user-defined skill registrations
- `registry/workflows.yaml` — user-defined workflow registrations
- `workflows/knowledge-lifecycle.md` — knowledge lifecycle workflow definition

## Integration points

The vault path is registered in `~/.config/agent-os/config.env` so all agents can discover it. The `/recall` skill searches the vault's `findings/`, `insights/`, and `Topics/` directories as one of its standard tiers. The `/lesson` skill routes vault-scoped lessons to `<vault>/docs/vault-os/LESSONS.md`. Domain-specific skills (investment, research, venture, intelligence) are added separately and are not bundled in the open-source distribution.

## Key source files

| File | Purpose |
|------|---------|
| `examples/vault-os/` | Vault skeleton directory with scaffold files |
| `scripts/init-vault.sh` | Shell script to create or link a vault with full scaffold |
| `examples/vault-os/README.md` | Vault overview, suggested structure, and quick start |
