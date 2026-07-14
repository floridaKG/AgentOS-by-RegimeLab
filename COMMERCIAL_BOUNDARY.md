# Open-Core and Commercial Boundary

Agent OS is published under Apache 2.0: the full Local Core harness — local
memory, agent routing contracts, provider-neutral orchestration scripts,
governance scaffolding, and extension adapters — is free and open source.

## Open-Core (Apache 2.0) — ships here

- Local SQLite memory, recall, injection, and promotion contracts
- Optional self-hosted Pinecone and Neo4j adapter docs/interfaces
- ACP-compatible agent/provider routing scripts and CLIs
- MOE and multi-agent workflow scripts (require user-installed agent CLIs + ACPx)
- Generic Vault OS and SuperDocs scaffolds
- Public registries, health checks, and release gates

You may run, modify, and self-host all of the above without restriction under
Apache 2.0.

## Not in the OSS tree (by design)

These are **not** shipped and are not planned as drop-in OSS modules in v1:

- Private runtime bridges to maintainer-only services
- Personalized domain skill packs (trading, research, investment, etc.)
- Maintainer vault content, session history, and production configs
- Hosted multi-tenant control planes

## Reserved for managed / commercial products

These may be offered as hosted or commercial services. They are **product**
boundaries, not Apache 2.0 license restrictions on the public harness:

| Area | Examples |
|------|----------|
| Hosted memory | Managed Pinecone/Neo4j, backups, migrations, retention |
| Credential plane | Managed provider keys, billing, cost routing |
| Team / enterprise | SSO, admin RBAC, compliance export, audit retention |
| Hosted orchestration | Observability, run analytics, evaluation suites |
| Premium adapters | Proprietary ranking, domain packs, curated workflows |

## What will not be dual-licensed bait-and-switch

If a feature is already in this repository under Apache 2.0, it stays Apache
2.0. Commercial offerings extend the hosted plane and managed operations; they
do not re-license the public tree.

## Vault OS honesty

The public Vault OS example is **structural scaffolding** only. Personalized
and domain-specific vault skills from the maintainer environment are not part
of the open-source distribution and will not appear under a different license
later as “missing OSS pieces.”
