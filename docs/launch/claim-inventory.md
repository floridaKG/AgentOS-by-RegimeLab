# Public claim inventory — Agent OS OSS

**Date:** 2026-07-27
**Tree:** public OSS staging repo (`AgentOS-by-RegimeLab`) @ post-diagram commits  

**Spec:** `2026-07-02-agent-os-oss-marketing-and-github-launch`  
**Scope:** user-facing docs, launch drafts, repo metadata, CI config

## Files checked

| Path | Role |
|---|---|
| `README.md` | Primary stranger surface |
| `SETUP.md` | Install walkthrough |
| `docs/GETTING_STARTED.md` | First 10 minutes |
| `docs/ARCHITECTURE.md` | Component story |
| `docs/assets/oss-architecture-diagram.html` | Visual overview |
| `docs/assets/BRAND.md` | Brand rules |
| `docs/MEMORY_USER_GUIDE.md` | Memory commands |
| `docs/OPTIONAL_BACKENDS.md` | Opt-in backends |
| `memory/README.md` | Memory architecture |
| `COMMERCIAL_BOUNDARY.md` | Open-core boundary |
| `PRIVACY_BOUNDARY.md` / `SECURITY.md` | Trust surfaces |
| `AGENTS.md` / `BOOT.md` | Agent entrypoints |
| `LICENSE` | Apache 2.0 |
| `.github/workflows/ci.yml` | CI claims |
| `docs/launch/*` | Launch drafts |
| Repo metadata (description, visibility) | GitHub surface |

Skills, examples, registry YAML, and tests are implementation detail; claims
there are not treated as marketing unless linked from README.

## Disposition legend

| Code | Meaning |
|---|---|
| **OK** | Claim proven by public path or reproducible command |
| **QUALIFY** | True only with config / user-supplied agents / opt-in backend |
| **FIX** | Overclaim or privacy risk — edit required |
| **N/A** | Not advertised |

## Inventory

| Claim / pattern | Where | Disposition | Evidence / action |
|---|---|---|---|
| Local SQLite memory always on after install | README, memory README | OK | `memory/core`, install init |
| Core needs no hosted services / no API keys | README, SETUP | OK | Local core path |
| `memory-st write` + `recall` | GETTING_STARTED | OK | Cold-path package 3 |
| Optional Pinecone / Neo4j / Hindsight | README, OPTIONAL_BACKENDS | OK if “optional” | Keep opt-in wording |
| ACP multi-agent dispatch works | README | QUALIFY | Needs ACPx + agent CLIs + config |
| MOE / team / redteam work | README | QUALIFY | Needs configured agent CLIs + keys |
| “shared memory” / cross-agent learning default | README hero | QUALIFY | Shared only if agents share store + conventions |
| “On startup, its memory is injected” | README narrative | QUALIFY | Injection is opt-in hook setup |
| “Hard rules enforced by machine-readable policy” | README | QUALIFY | Tools/conventions exist; not an automatic gate on every action |
| “Any agent… first-class” | ARCHITECTURE | QUALIFY | “can connect with setup” |
| “works out of the box” | memory/README | FIX | Soften to local core after install |
| Video adversarial demo | — | N/A | Ship wiki overview only if present |
| Wiki overview video (~5 min) | README (target) | OK after asset add | `docs/assets/video/overview.mp4` |
| Architecture diagram | README | OK | `docs/assets/oss-architecture-diagram.html` |
| CI present | `.github/workflows/ci.yml` | OK | Privacy/history/security/ACP mock jobs — not full product suite |
| Private absolute paths in public docs | BRAND.md (pre-fix) | FIX | Remove maintainer home paths |
| Production-ready / uniqueness / private parity | scanned | OK if absent | Re-scan after edits |
| Automatic adversarial gate | — | N/A | Pattern is runnable, not automatic |

## Privacy / security baseline

| Check | Result |
|---|---|
| Credential patterns in README/SETUP/docs | Scan on each edit pass |
| Maintainer absolute paths in user-facing docs | BRAND.md fixed to in-repo paths only |
| License present | `LICENSE` Apache 2.0 |
| Repo visibility | Private until owner live gate (package 5) |

## CI honesty

CI runs privacy gate, history gate, runtime security tests, and ACP mock tests.
It is **not** a guarantee of full functional coverage or multi-agent end-to-end
success. README should not imply “production CI green = production-ready.”

## Historical package checklist

The package checklist above records the original launch work. Current release
validation is maintained by the repository's release, privacy, security, and
clean-room gates.

## Sign-off

| Role | Status |
|---|---|
| Executor inventory | Complete |
| Static/privacy validation | Maintained by CI and release gates |
| Adversarial review | Complete for current release candidate |
