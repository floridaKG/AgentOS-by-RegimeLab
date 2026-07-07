# Agent OS

An agent-agnostic harness -- the OS agents run on.

Agent OS is a CLI-first harness for orchestrating any AI coding agent
(Claude Code, Codex, Pi, Hermes, OpenCode, Droid\*, and future models)
as first-class citizens in a shared, memory-driven system.

> \* Droid is a proprietary agent runtime. It requires either a Factory
> subscription or bring-your-own-key (BYOK) configuration. All other listed
> agents are available to OSS users without additional subscription.

## Philosophy

- **Agent-agnostic.** Any agent participates equally. Easy to incorporate
  new models without rewiring the system.
- **Cross-agent memory.** Every agent contributes to shared memory.
  Stumbles are captured, reviewed, and promoted so all agents learn together.
- **Multi-agent, multi-provider.** Agents call each other through ACP and
  Agent Mail. Providers are swappable. No lock-in at any layer.
- **Enforced protocols.** The harness enforces the rules so agents don't
  have to rediscover them every session.
- **Agent voice.** Agents speak up about gaps and friction. The system
  listens and improves itself.
- **Multi-provider orchestration.** MOE panels can combine Claude, Codex,
  OpenCode, Pi, and compatible providers through user-editable configuration.

This is a **harness**, not a framework. Frameworks are libraries you import.
The harness is the OS agents run on top of. Agent OS owns the outcome,
learns from its mistakes, and gets better every cycle.

## Features

### Agent Communication

- **ACP (Agent Communication Protocol)** — Route work to configured agents and workspaces. Fire-and-forget or wait-for-result dispatch with role-based routing and workspace awareness. Ships with `acp-task`, `acp-daemon`, and `acp-health` CLI tools.
- **Agent Mail** — Async file-based messaging between agents. Send, inbox, and read messages without a running daemon. Lightweight and zero-dependency.
- **Agent Voice** — Agents surface gaps, friction, and improvement suggestions. The system listens and improves itself.

### Multi-Agent Reasoning

- **Sidecar** — Pair a higher-reasoning DRIVER agent with a persistent cheap execution partner. The driver thinks; the sidecar executes.
- **Sidecar Heavy** — The inverse: spawn a pure-reasoning heavy model (GPT-5.x, Claude Opus, etc.) that only thinks and advises. You and a cheap sidecar do the implementation. Consult on demand for plans, architecture decisions, and debugging hard problems.
- **Upward Handoff** — One-shot document pass to a higher-reasoning model for fresh-eyes review.
- **Adversarial Review** — Spawn a critic to find flaws in specs, decisions, or code.
- **MOE Panels** — Run configurable multi-provider Mixture-of-Experts panels combining Claude, Codex, OpenCode, Pi, and compatible providers.
- **Multi-Agent Workflows** — Swarm, council, and red-team patterns for parallel, adversarial, and iterative work.

## Quickstart

```bash
git clone https://github.com/floridaKG/AgentOS-by-RegimeLab.git
cd AgentOS-by-RegimeLab
./install.sh
```

Minimum requirements: Python 3.10+, Node.js 18+, Git, and one LLM provider
API key.

See `SETUP.md` for full instructions.

## Optional Components

- **Vault OS**: A user-owned knowledge vault for storing structured notes,
  research, and agent-readable content. Create or link with
  `scripts/init-vault.sh`. The public release provides structural scaffolding,
  not personalized domain skill packs.

- **SuperDocs**: A project documentation harness that agents can navigate.
  Scaffold with `scripts/init-superdocs.sh --project <name>`.

## Core vs Optional Providers

| Component | Status | Default |
|-----------|--------|---------|
| Memory (SQLite) | Core - always available | On |
| Agent Communication Protocol (ACP) | Core - always available | On |
| Agent Voice (agent feedback) | Core - always available | On |
| MOE / multi-agent panels | Core orchestration | On (providers configured by user) |
| ACPx (universal agent launcher) | External dependency (MIT) | Off (npm install acpx) |
| CodeGraph (code structure queries) | External dependency | Off (npm install @codegraph/cli) |
| Pinecone (semantic search) | Optional adapter | Off (needs API key) |
| Neo4j (graph memory) | Optional adapter | Off (needs credentials) |
| Hindsight (advanced memory) | Ships — requires Hermes + Hindsight API | `memory/hindsight_bridge.py` |

The default install works with zero external services. All adapters are optional.

## License

Apache 2.0. See `LICENSE`. Full commercial use, modification, and
redistribution are permitted under the terms of the license.

## Commercial Boundary

Agent OS is published under the Apache 2.0 license -- the full harness is
free and open source. The following capabilities are reserved for managed
or commercial product offerings (not OSS license restrictions):

- **Hosted memory plane**: Managed Pinecone and Neo4j infrastructure
- **Managed governance**: Team controls and observability
- **Premium adapters**: Advanced retrieval, ranking, and analytics
- **Enterprise features**: SSO, compliance, retention policies

See `COMMERCIAL_BOUNDARY.md` for the complete open-core boundary.
