# Agent OS

**A shared operating layer for AI coding agents** — local tools, conventions,
skills, and optional routing that sit around the agent CLIs you already use.

<p align="center">
  <img src="https://app.regime-lab.com/assets/regimelab-logo-transparent-C9fEkeux.png" alt="Regime Lab" width="72" height="72" />
</p>

<p align="center"><sub>by Regime Lab · Apache 2.0 · open-core</sub></p>
<p align="center"><sub>Logo displayed from Regime Lab product site — brand mark not licensed with this repo (see <a href="docs/assets/BRAND.md">docs/assets/BRAND.md</a>).</sub></p>

---

## What this is / is not

| This **is** | This **is not** |
|---|---|
| A CLI **harness** under your agents (memory, skills, workflows, dispatch scaffolding) | A new LLM, chat app, or “autonomous OS” that replaces your agents |
| **Local-first**: default memory is SQLite on your machine | A hosted multi-tenant control plane (that’s commercial plane) |
| Compatible with agents that **can connect with setup** (Claude Code, Codex, OpenCode, Pi, Grok, Droid, and others) | A claim that every agent works with zero configuration |
| Opt-in cloud backends (Pinecone, Neo4j, Hindsight) | Cloud or API keys required for the core |
| Runnable multi-agent **patterns** (MOE panels, red-team, swarm) | An automatic gate that always reviews every change |

Cross-agent sharing needs a **shared store** and conventions — not magic sync
across unrelated machines. ACP dispatch needs **ACPx** plus your agent CLIs
and credentials.

---

## The problem

You run multiple AI coding agents. Sessions start cold. Lessons from last week
live in one tool and stay invisible to the others. Getting a second opinion
means copy-paste between windows.

Agent OS gives you a local place to write and recall lessons, scripts to run
multi-model workflows when you want them, and scaffolding to dispatch work
between agents once you configure it.

---

## Quickstart (local core — no cloud keys)

```bash
git clone https://github.com/floridaKG/AgentOS-by-RegimeLab.git
cd AgentOS-by-RegimeLab
./install.sh
source ~/.config/agent-os/config.env
```

For a one-line install into `~/.local/share/agent-os`:

```bash
curl -fsSL https://raw.githubusercontent.com/floridaKG/AgentOS-by-RegimeLab/main/bootstrap.sh | bash
```

The bootstrapper clones the repository, runs the idempotent installer, and
prints a setup report. Review the script or pin a release tag when supply-chain
control matters.

**Minimum requirements:** Python 3.10+, Git, Bash. Linux and WSL2 are tested.
ACP and ACPx are cross-platform in principle, but this Agent OS distribution's
full daemon and shell workflow integration is currently verified only on Linux
and WSL2. macOS is not verified for v1 claims. No Node.js, hosted services, or
API keys are required for the local core.

### Primary CLI path

```bash
agent-os init
agent-os doctor
agent-os memory add "Agent OS local core write/recall smoke test"
agent-os memory search "local core write/recall smoke test"
```

The unified CLI is the recommended shell interface. Existing `memory-*`
commands remain available for compatibility.

### MCP Server (optional)

Agent OS includes a local MCP server for memory and diagnostics:

```bash
# Start the MCP server
agent-os mcp serve

# Install MCP config for Claude
agent-os mcp install --client claude

# Install MCP config for Codex
agent-os mcp install --client codex

# Install MCP config for OpenCode
agent-os mcp install --client opencode
```

See [docs/MCP.md](docs/MCP.md) for full documentation.

### Prove memory works (write → recall)

```bash
SMOKE_FILE="$AGENT_OS_HOME/.local/state/agent-os/aos-smoke.txt"
mkdir -p "$(dirname "$SMOKE_FILE")"
echo "Agent OS local core write/recall smoke test — unique $(date +%s)" > "$SMOKE_FILE"

memory-st write \
  --run-id "quickstart-$(date +%s)" \
  --agent-id "you" \
  --workspace "demo" \
  --intent LESSON \
  --kind observation \
  --summary "Agent OS local core write/recall smoke test" \
  --content-file "$SMOKE_FILE" \
  --source-ref "readme:quickstart"

memory-recall --text "local core write/recall smoke test" --tier short_term
```

You should see the lesson you just wrote (JSON including your summary). That is
the cold path: install → write → recall, entirely local.

If the database is brand new, run `memory-st init` once after install (also
safe to re-run).

**First time?** [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md) is a ~10-minute
walkthrough. Or run `./install.sh --quickstart` to seed demo records.

Verify tooling with:

```bash
bash scripts/agent-os-health.sh
```

For multi-agent dispatch, install [ACPx](https://www.npmjs.com/package/acpx)
and configure agent CLI credentials. See [SETUP.md](SETUP.md).

---

## What you get

### Memory that accumulates (local SQLite)

A local SQLite store that agents (and you) can write to and search. Lessons,
stumbles, and decisions persist across sessions when you use the CLIs.

```bash
memory-recall --text "how do we handle token refresh errors" --tier short_term
# write requires --content-file; see docs/GETTING_STARTED.md for a full example
```

Optional auto-injection into agent sessions is **opt-in** and requires a
one-time hook setup. See [docs/MEMORY_USER_GUIDE.md](docs/MEMORY_USER_GUIDE.md).

### Multi-agent dispatch (with setup)

Agents **can** call each other through ACP when ACPx and agent CLIs are
installed and configured. Tasks can be tracked with a run record.

```bash
acp-task code_reviewer work "Review the auth flow for SQL injection" --wait
```

### Multi-model reasoning — MOE tiers (with setup)

When one model isn’t enough, fire a panel or iterative workflow. Tiers range
from cheap parallel panels to **persistent multi-iteration** collaborate /
red-team style loops for deeper work. These need configured providers.

```bash
team fire --tier 2 --members "claude opus, codex gpt-5.5" --task "Review this spec for security issues"
./agent-workflow redteam ./spec.md 4 --proposer architect --attacker escalation
```

See [docs/OPTIONAL_BACKENDS.md](docs/OPTIONAL_BACKENDS.md) for panel configuration.

### Doc protocols and conventions

Spec templates, handoff standards, and report conventions ship in-tree so
agents can follow the same playbook. Enforcement depends on using the shipped
tools and conventions — not an invisible automatic gate on every edit.

### Optional backends

Add Pinecone, Neo4j, or Hindsight when you want semantic, graph, or bank-bridge
memory. Each is opt-in; the core degrades gracefully without them.

See [docs/OPTIONAL_BACKENDS.md](docs/OPTIONAL_BACKENDS.md) or
`./install.sh --setup-memory`.

---

## How it fits together

**Visual overview:** [open the rendered architecture overview](https://floridaKG.github.io/AgentOS-by-RegimeLab/) · [view the HTML source](docs/assets/oss-architecture-diagram.html)

Covers agents that can connect, MOE tiers (including persistent multi-iteration
work), Sidecar modes, skill-rank → pack → inject, memory promote/inject, rtk,
governed knowledge surfaces, and the local cold path. Core is local SQLite;
cloud backends are opt-in.

```
Your agents (Claude Code, Codex, OpenCode, Pi, Grok, Droid, + more with setup)
        │
        ├── Memory layer ── SQLite (always on) + optional Pinecone/Neo4j/Hindsight
        │   ├── recall      Search across memory tiers
        │   ├── inject      Opt-in context injection (hook setup)
        │   └── promote     Move stable lessons when configured
        │
        ├── ACP dispatch ── with ACPx + agent CLIs + config
        │   ├── acp-task    Dispatch helpers
        │   └── Run ledger  Task tracking when dispatch is used
        │
        ├── Workflows ── MOE / swarm / council / redteam / orchestrate (patterns)
        │
        └── Skills ── shared skill packs agents load on demand
```

The local core does not phone home. Provider API keys you add stay in your
`config.env` / secrets files.

**Video overview (~5 minutes):**  
[docs/assets/video/overview.mp4](docs/assets/video/overview.mp4) — wiki-style
tour of the system. Not a product demo of unreleased or maintainer-only
features.

---

## Getting deeper

| Document | When to read it |
|----------|----------------|
| [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md) | First ~10 minutes |
| [SETUP.md](SETUP.md) | Full installation options |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Components and request flow |
| [Rendered architecture overview](https://floridaKG.github.io/AgentOS-by-RegimeLab/) · [source](docs/assets/oss-architecture-diagram.html) | Interactive architecture poster |
| [docs/OPTIONAL_BACKENDS.md](docs/OPTIONAL_BACKENDS.md) | Pinecone, Neo4j, Hindsight |
| [docs/MEMORY_USER_GUIDE.md](docs/MEMORY_USER_GUIDE.md) | write, recall, promote |
| [AGENTS.md](AGENTS.md) | Entrypoint agents read on boot |
| [BOOT.md](BOOT.md) | Intent router: which skill for which task |
| [docs/launch/claim-inventory.md](docs/launch/claim-inventory.md) | Public claim inventory |

## Known limitations

- Linux / WSL2 tested for the full harness; ACP/ACPx are not inherently Linux-only
- macOS ACPx use may work, but the Agent OS daemon and shell workflows are not verified for v1 claims
- Multi-agent dispatch and MOE need your agent CLIs, models, and often ACPx  
- Memory injection and optional backends are configuration-dependent  
- CI covers privacy/history gates and selected tests — not a full product SLA  
- Open-core: hosted memory, managed governance, and enterprise controls are commercial plane (see commercial boundary)

## License

Apache 2.0. See [LICENSE](LICENSE).

Agent OS is open-core: the public harness is free and open source. Hosted
memory, managed governance, and enterprise controls are reserved for
commercial offerings — not license restrictions on this tree. See
[COMMERCIAL_BOUNDARY.md](COMMERCIAL_BOUNDARY.md).

## Security

See [SECURITY.md](SECURITY.md) for how to report vulnerabilities.

## CI

GitHub Actions runs privacy/history gates and selected security/ACP tests on
`main` and pull requests. Green CI is not a promise that every workflow works
on every machine without configuration.
