# Agent OS

An agent-agnostic harness — the OS agents run on.

Agent OS is a CLI-first harness for orchestrating supported AI coding agents
(Claude Code, Codex, OpenCode, and compatible providers) with shared local
memory, dispatch protocols, and cross-agent learning.

## What you get out of the box (Local Core)

After `./install.sh` you have:

- **Local memory** — SQLite short-term store, write/recall CLIs, stumble pipeline
- **CLI harness** — `bin/` tools for memory, health, skills, mail, voice
- **Workflow config** — role templates and multi-agent scripts under
  `~/.config/agent-workflows/`
- **Curated skills** — shared skill packs agents can load on demand
- **Gates** — privacy, history, clean-room, and release verification scripts

No Node.js, no hosted services, and no third-party vector/graph DBs required
for Local Core.

## Multi-agent dispatch (optional)

ACP task dispatch and multi-agent workflows (swarm, council, MOE panels) need
extra pieces **you** install:

| Need | Why |
|------|-----|
| At least one agent CLI | Claude Code, Codex, and/or OpenCode |
| [ACPx](https://www.npmjs.com/package/acpx) (`npm install -g acpx`) | Launches agents for real ACP dispatch |
| Node.js 18+ | Only if you install ACPx or CodeGraph |
| LLM API keys | Required by the agent CLIs you use |

Without ACPx, `acp-daemon` runs in **dry-run** mode (records what would run).
That is intentional — Local Core stays usable offline.

**RTK (optional token savings):** Install via `./install.sh --with-rtk` to
reduce LLM token consumption. RTK is an external Apache 2.0 tool that
filters command outputs before they reach your AI agent.

## Philosophy

- **Agent-agnostic.** Supported agents participate equally.
- **Cross-agent memory.** Agents write lessons and stumbles into shared local memory.
- **Multi-agent, multi-provider.** Optional ACP + ACPx; providers are swappable.
- **Enforced protocols.** Gates and boot docs keep sessions consistent.
- **Agent voice.** Agents can surface friction for maintainers to review.

This is a **harness**, not a framework. Frameworks are libraries you import.
The harness is the OS agents run on top of.

## Quickstart

```bash
git clone https://github.com/floridaKG/AgentOS-by-RegimeLab.git
cd AgentOS-by-RegimeLab
./install.sh
source ~/.config/agent-os/config.env
bash scripts/agent-os-health.sh
```

**Minimum requirements (Local Core):** Python 3.10+, Git, Bash, and one LLM
provider API key for the agent CLI you use.

**Platforms:** Linux and WSL2 are tested. macOS is **not yet verified** — may
work, but is not a supported v1 target.

See `SETUP.md` for full instructions, optional adapters, and multi-agent setup.

## Optional components

| Component | Status | Default |
|-----------|--------|---------|
| Memory (SQLite) | Core | On |
| Agent Communication Protocol (ACP CLIs) | Core (dry-run without ACPx) | On |
| Agent Voice | Core | On |
| ACPx (agent launcher) | External (MIT) | Off — `npm install -g acpx` |
| CodeGraph | External | Off — `npm install -g @codegraph/cli` |
| RTK (token filter CLI) | External (Apache 2.0) | Off — `./install.sh --with-rtk` |
| Pinecone (semantic search) | Optional adapter | Off |
| Neo4j (graph memory) | Optional adapter | Off |
| Hindsight (memory bank bridge) | Optional adapter | Off — see `memory/adapters/hindsight/` |
| Vault OS / SuperDocs scaffolds | Optional examples | Off — init scripts |

## License

Apache 2.0. See `LICENSE`. Full commercial use, modification, and
redistribution are permitted under the terms of the license.

## Commercial boundary

Agent OS is open-core under Apache 2.0. Hosted memory, managed governance,
and enterprise controls are reserved for commercial offerings — not license
restrictions on the OSS harness. See `COMMERCIAL_BOUNDARY.md`.

## Security

See `SECURITY.md` for how to report vulnerabilities.
