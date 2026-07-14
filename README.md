# Agent OS

**The harness your AI coding agents run on — shared memory, multi-agent dispatch, and cross-agent learning that accumulates instead of resetting.**

---

## The problem

You run Claude Code, Codex, or OpenCode. Every session starts cold. Your agent
doesn't remember what it learned yesterday. It doesn't know what the other
agent discovered last week. It can't call a different model when it's stuck.
And the lessons you capture in one tool are invisible to the others.

Agent OS fixes this. It's a CLI harness that sits underneath your agents —
giving them shared memory, a dispatch protocol to call each other, and
workflows to combine multiple models on hard problems. It works with the tools
you already use.

## What it looks like in practice

**Without Agent OS:**
You ask Claude Code to fix a bug in your auth flow. It reads the file cold,
rediscovering the same edge case Codex documented three days ago. It fixes the
bug but doesn't record what it learned. Tomorrow, you open OpenCode to review
a different file and start from zero again.

**With Agent OS:**
You ask Claude Code to fix the bug. On startup, its memory is injected with
Codex's lesson from three days ago: "the token refresh path in auth.py:142
fails silently when the session expires during a database migration." Claude
Code reads the file already knowing the edge case, fixes it in one pass, and
writes a stumble for the pattern it found. Tomorrow, OpenCode picks up both
lessons. Over weeks, your agents accumulate a knowledge base that grows with
every session.

## Who this is for

You run multiple AI coding agents and want them to share context. You're tired
of repeating the same setup instructions. You want a second opinion from a
different model without copy-pasting between tools. You want your agents to
get smarter over time instead of starting from scratch every morning.

If you use one agent occasionally for simple tasks, you don't need Agent OS.
If you live in a terminal with multiple agents and want them to work together,
this is for you.

## Quickstart

```bash
git clone https://github.com/floridaKG/AgentOS-by-RegimeLab.git
cd AgentOS-by-RegimeLab
./install.sh
source ~/.config/agent-os/config.env
```

Four commands. You now have local memory, recall CLIs, workflow scripts, and
skill packs. Verify with:

```bash
bash scripts/agent-os-health.sh
```

**First time?** Read [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md) for a
10-minute walkthrough — every step produces visible output. Or run
`./install.sh --quickstart` to seed demo memory records so `recall` returns
results immediately.

**Minimum requirements:** Python 3.10+, Git, Bash. Linux and WSL2 are tested.
No Node.js, no hosted services, no API keys needed for the core.

For multi-agent dispatch, install [ACPx](https://www.npmjs.com/package/acpx)
(`npm install -g acpx`) and configure your agent CLI credentials. See
[SETUP.md](SETUP.md) for the full walkthrough.

## What you get

### Memory that accumulates

A local SQLite store that agents write to and search. Lessons, stumbles, and
decisions persist across sessions. Agents query shared memory with `recall`
before starting work — no more discovering the same edge case twice.

```bash
recall "how do we handle token refresh errors"
memory-st write --intent LESSON --summary "auth.py:142 fails silently during DB migrations"
```

Optional auto-injection: the recall hook can inject relevant context before
every prompt. Requires a one-time agent hook configuration. See
[docs/MEMORY_USER_GUIDE.md](docs/MEMORY_USER_GUIDE.md) for setup.

### Multi-agent dispatch

Agents call each other through ACP (Agent Communication Protocol). Claude Code
dispatches a code review to Codex. Codex hands off a hard problem to a
higher-capability model. Every task is tracked with a run record you can
inspect and audit.

```bash
acp-task code_reviewer work "Review the auth flow for SQL injection" --wait
acp-task executor work "Apply the security fix" --session auth-hardening --wait
```

One-shot for quick handoffs, persistent sessions for multi-turn work.

### Multi-model reasoning (MOE)

When one model isn't enough, fire a panel. Three models answer in parallel, a
judge synthesizes the disagreements. Or run a red-team: proposer defends,
attacker finds holes, adjudicator decides. Or a swarm: parallel explorers
investigate from different angles.

```bash
team fire --tier 2 --members "claude opus, codex gpt-5.5" --task "Review this spec for security issues"
./agent-workflow redteam ./spec.md 4 --proposer architect --attacker escalation
```

Five MOE tiers from cheap parallel LLM panels to persistent iterative rounds.
See [docs/OPTIONAL_BACKENDS.md](docs/OPTIONAL_BACKENDS.md) for panel
configuration.

### Doc protocols and conventions

Agent OS ships document templates and conventions so your agents stop
reinventing formats. Spec templates, handoff standards, report conventions
with required STUMBLES/CONFIRMED/ARTIFACTS sections. Hard rules enforced
by machine-readable policy. Your agents follow the same playbook every time.

### Optional: semantic, graph, and cross-agent memory

Add Pinecone for semantic search across sessions. Neo4j for graph
relationships between records. Hindsight for cross-agent memory sharing
via a shared bank bridge. Each backend is uncomment-two-lines simple, and
the system degrades gracefully when they're not configured.

See [docs/OPTIONAL_BACKENDS.md](docs/OPTIONAL_BACKENDS.md) for the guided
setup walkthrough, or run `./install.sh --setup-memory` for an interactive
provisioning walkthrough.

## How it fits together

```
Your agents (Claude Code, Codex, OpenCode)
        │
        ├── Memory layer ── SQLite (always on) + optional Pinecone/Neo4j/Hindsight
        │   ├── recall      Search across memory tiers
        │   ├── inject      Auto-inject relevant context on session start
        │   └── promote     Move stable lessons to long-term storage
        │
        ├── ACP dispatch ── Agents call each other through a protocol daemon
        │   ├── acp-task    Fire-and-forget or block-and-wait dispatch
        │   ├── acp-daemon  Polls inboxes, dispatches to target agents
        │   └── Run ledger  Every task tracked with state, events, and artifacts
        │
        ├── Workflows ── Multi-agent patterns for hard problems
        │   ├── team        MOE panels (1/2/2r/3/P tiers)
        │   ├── swarm       Parallel explorers + synthesis
        │   ├── council     Independent opinions + moderator
        │   ├── redteam     Adversarial proposer/attacker/adjudicator
        │   └── orchestrate Explore → architect → execute → review loop
        │
        └── Skills ── 15 shared skill packs agents load on demand
            ├── acp, recall, lesson, digest, doc-audit
            ├── moe, agent-workflows, adversarial-review
            └── upward-handoff, changes-review, umbrella-refactor
```

Everything runs locally. Nothing phones home. Your API keys stay in your
`config.env`.

## Getting deeper

| Document | When to read it |
|----------|----------------|
| [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md) | First 10 minutes — concrete walkthrough |
| [SETUP.md](SETUP.md) | Full installation walkthrough with every option |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | How the components connect and the request flow |
| [docs/OPTIONAL_BACKENDS.md](docs/OPTIONAL_BACKENDS.md) | Set up Pinecone, Neo4j, or Hindsight |
| [docs/MEMORY_USER_GUIDE.md](docs/MEMORY_USER_GUIDE.md) | Memory commands: write, recall, promote |
| [AGENTS.md](AGENTS.md) | Entrypoint your agents read on boot |
| [BOOT.md](BOOT.md) | Intent router: which skill for which task |

## License

Apache 2.0. See [LICENSE](LICENSE). Full commercial use, modification, and
redistribution are permitted.

Agent OS is open-core: the full harness is free and open source. Hosted
memory, managed governance, and enterprise controls are reserved for
commercial offerings — not license restrictions. See
[COMMERCIAL_BOUNDARY.md](COMMERCIAL_BOUNDARY.md).

## Security

See [SECURITY.md](SECURITY.md) for how to report vulnerabilities.
