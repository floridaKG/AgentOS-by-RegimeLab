# Privacy Boundary

This document defines what ships in the public Agent OS distribution,
what is excluded, and how maintainers verify that private material
did not cross the boundary.

## Public Core Contents

The following directories and files are included in the public distribution:

| Component | Path | Description |
|---|---|---|
| AGENTS.md | `AGENTS.md` | Agent entrypoint and boot routing |
| BOOT.md | `BOOT.md` | Intent router for workspace matching |
| README.md | `README.md` | Project overview and quickstart |
| SETUP.md | `SETUP.md` | Installation and configuration guide |
| LICENSE | `LICENSE` | Apache 2.0 |
| install.sh | `install.sh` | Idempotent installer |
| config.env.template | `config.env.template` | Configuration template |
| .env.template | `.env.template` | Environment variables template |
| requirements.txt | `requirements.txt` | Python dependencies |
| Registry | `registry/` | Public-only capability registries |
| Skills | `skills/shared/` | Curated shared skill definitions |
| Memory core | `memory/core/` | SQLite-based local memory system |
| Memory adapters | `memory/adapters/` | Optional Pinecone and Neo4j adapter docs |
| Scripts | `scripts/` | Public CLI tools and utilities |
| Bin facades | `bin/` | CLI entry points for memory operations |
| Docs | `docs/` | Usage guides (ARCHITECTURE.md, rtk-usage-guide, codegraph-setup) |
| Tests | `tests/` | Smoke, privacy, and clean-room tests |
| Examples | `examples/` | Generic Vault OS and SuperDocs scaffolds |

## Optional Public Adapters

These are documented but require external services:

| Adapter | Config Required | Description |
|---|---|---|
| Pinecone | `PINECONE_API_KEY`, `PINECONE_INDEX` | Semantic vector search |
| Neo4j | `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` | Graph-based memory queries |

## Explicit Private Exclusions

The following are NEVER included in the public distribution:

- **Owner identifiers**: usernames, emails, home directory paths
- **Private repositories**: User-specific project repositories and vault contents
- **Credentials and secrets**: API keys, SSH keys, certificates, tokens
- **Runtime state**: SQLite databases, caches, agent state, cron schedules
- **Personal content**: notes, drafts, proposals, handoffs, memory history
- **Owner-specific services**: Hindsight, private MCP servers, deployment configs
- **Production data**: market data, trading strategies, financial information
- **Private skills**: workspace-specific skills not listed in registry
- **Owner history**: session logs, stumble records, lesson history

## External Dependencies (MIT, not bundled)

| Tool | Package | License | How users get it |
|---|---|---|---|
| ACPx | `acpx` (openclaw/acpx) | MIT | `npm install -g acpx` |
| CodeGraph | `@codegraph/cli` | MIT | `npm install -g @codegraph/cli` |

These are referenced in documentation and agent configs but are not shipped in the
Agent OS distribution. Users install them separately from npm. Both are MIT-licensed
and have no license conflict with the Apache 2.0 Agent OS core.

## Secret Handling

- No secrets are included in the distribution
- `config.env.template` and `.env.template` contain placeholder values only
- `secrets.env` is created by `install.sh` with placeholder comments
- Users must provide their own API keys in `~/.config/agent-os/config.env`
- Secrets files are created with `chmod 600` permissions

## Export Allowlist

Only files explicitly listed in `.ossbuild/EXPORT_MANIFEST.yaml` may enter
the staging tree. The allowlist is reviewed before each release.

## Export Denylist

The following patterns are always blocked:

- `.env*`, `*.sqlite`, `*.db`, `*.pem`, `*_ed25519`, `*_rsa`
- `credential*.json`, `service-account*.json`
- `node_modules/`, `.venv/`, `__pycache__/`
- `handoffs/`, `hermes-state/`, `state/`, `archive/`
- `drafts/`, `proposals/`, `notes/`, `legacy/`
- `droid-wiki/`
- `hooks/`, `acp/`, `config/`, `specs/`, `config.env`

## Release Scan Patterns

Before each release, the following scans are executed:

1. **Owner identifier scan**: No `$OWNER_USERNAME`, `/home/$OWNER_USERNAME`
2. **Private path scan**: No `/mnt/c/vault`, owner-specific absolute paths
3. **Service identifier scan**: No private repository and service identifiers
4. **Secret scan**: No API keys, tokens, or credentials in content
5. **File type scan**: No `.env`, `.sqlite`, `.db`, `.pem` files
6. **Registry consistency**: All registry entries resolve to shipped files
7. **YAML validity**: All YAML files parse without errors
8. **Path resolution**: All `$AGENT_OS_HOME/` paths resolve to existing files

**Scanner infrastructure note**: The gate scripts (`scripts/gate-privacy.sh`,
`scripts/gate-release.sh`) use `$OWNER_USERNAME` (configured per-user) as the grep/scanner
pattern. This is architecturally necessary — security scanners must contain the
patterns they scan for. These files are therefore excluded from owner-username scans,
just as test fixtures and this document are. Both gate scripts have been scrubbed of
literal owner file paths; only the scan pattern itself remains.

## How Maintainers Verify

Run the privacy gate:

```bash
bash tests/privacy/privacy_gate.sh .
```

This script:
- Scans all shipped content for prohibited patterns
- Checks file types against the denylist
- Validates registry consistency
- Emits per-gate artifacts with pass/fail status
- Exits non-zero if any gate fails

## Clean-Room Verification

The clean-room test (`tests/clean-room/install_and_verify.sh`) proves that
a new user can install Agent OS in an isolated temporary HOME without access
to the owner's machine, private repositories, services, or filesystem layout.
