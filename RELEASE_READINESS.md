# Release Readiness

This public candidate is a curated duplicate. It does not modify or package the
maintainer's private Agent OS runtime, private workspaces, personal Vault,
production SuperDocs, credentials, memories, or service state.

## What users install

- Agent OS **Local Core**: SQLite memory plus CLI entry points under `bin/`
  (memory, ACP, voice, mail, stumble pipeline, unified `agent-os` CLI).
- Curated shared skills under `skills/shared/` (see `registry/skills.yaml`).
- Public-only registries, scripts, setup documentation, and health checks.
- Optional Pinecone, Neo4j, and Hindsight adapter contracts (off until configured;
  Hindsight bridge/GC/health ship and work when `hindsight-client` + API + bank are set).
- CodeGraph and ACPx reference docs (external MIT dependencies, not bundled).

Counts drift as the tree evolves — treat `registry/*.yaml` and `bin/` as truth,
not this paragraph.

## Optional components

- **Vault OS** is a generic, user-owned knowledge workspace. Users create it at
  a path they choose or link an existing vault with `scripts/init-vault.sh`.
  It is not required by Agent OS core and contains no maintainer notes.
- **SuperDocs** is a generic project-documentation scaffold. Users initialize it
  in any project with `scripts/init-superdocs.sh --project <name> --path <path>`.
  It contains governance, guardrails, skills, workflows, and registry templates.

## License

Apache 2.0. See `LICENSE`. Full commercial use, modification, and
redistribution are permitted.

## Setup

Follow `SETUP.md`. The minimum installation uses local SQLite only and requires
no Vault, SuperDocs, Pinecone, Neo4j, ACPx, or private runtime services.

## Verification

Run:

```bash
pip install -r requirements.txt   # PyYAML required by gates
bash scripts/gate-release.sh
```

CI runs the same gates on every push to `main`. Do not flip the repository
public while CI is red.

The authoritative gate validates privacy, binary content, syntax, registries,
negative leak fixtures, clean-room installation, first memory write/query,
idempotency, Vault OS, SuperDocs, manifest coverage, permissions, and absence
of nested Git metadata in export trees.

Top-level `.ossbuild/` contains private build evidence and is explicitly
non-shipping (gitignored).

## Platform support (v1)

| Platform | Status |
|----------|--------|
| Linux | Tested |
| WSL2 | Tested |
| macOS | Not verified — unsupported for v1 claims |
