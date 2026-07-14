# Security Policy

## Supported versions

Security fixes are applied to the default branch (`main`) of this repository.
There is no long-term support branch for v1.

## Reporting a vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Please report security issues privately:

1. Use GitHub **Security Advisories** for this repository (preferred), or
2. Contact the repository owner via their GitHub profile on the org that
   publishes this project.

Include:

- A description of the issue and its impact
- Steps to reproduce (PoC if possible)
- Affected commit hash or release tag
- Whether you plan to disclose publicly and on what timeline

We aim to acknowledge reports within 7 days and to provide a remediation plan
or status update within 30 days for confirmed issues in the public tree.

## Scope

In scope:

- Secrets or credentials accidentally present in the public tree or git history
- Installer or gate scripts that execute untrusted remote content unsafely
- Path traversal or command injection in shipped CLIs when used as documented
- Privacy-boundary failures (private paths, owner identifiers, production keys)

Out of scope:

- Issues that require a user to deliberately paste secrets into configs
- Vulnerabilities solely in external tools (agent CLIs, ACPx, RTK, Pinecone, Neo4j)
- Social engineering against individual API keys stored outside this repo

## Optional RTK install note

`./install.sh --with-rtk` downloads and runs a third-party install script over
HTTPS. That is an explicit advanced opt-in. Prefer reviewing the upstream
script and pinning a release if your environment requires supply-chain control.

## Privacy gates

Before release, maintainers run:

```bash
bash tests/privacy/privacy_gate.sh .
OWNER_USERNAME=<maintainer-username> bash tests/privacy/history_gate.sh .
bash scripts/gate-release.sh
```

See `PRIVACY_BOUNDARY.md` for what must never ship.
