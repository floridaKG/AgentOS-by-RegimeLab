# Release Readiness

This public candidate is a curated duplicate. It does not modify or package the
maintainer's private Agent OS runtime, private workspaces, personal Vault,
production SuperDocs, credentials, memories, or service state.

## What users install

- Agent OS core with local SQLite memory and five CLI entry points.
- Eight curated shared skills.
- Public-only registries, scripts, setup documentation, and health checks.
- Optional Pinecone and Neo4j adapter contracts.
- CodeGraph and ACPx reference docs (external MIT dependencies, not bundled).

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
no Vault, SuperDocs, Pinecone, Neo4j, advanced private memory provider, or
private runtime service.

## Verification

Run:

```bash
bash scripts/gate-release.sh
```

The authoritative gate validates privacy, binary content, syntax, registries,
negative leak fixtures, clean-room installation, first memory write/query,
idempotency, Vault OS, SuperDocs, manifest coverage, permissions, and absence
of Git metadata.

Top-level `.ossbuild/` contains private build evidence and is explicitly
non-shipping. Publishing must use `.ossbuild/EXPORT_MANIFEST.yaml`.
