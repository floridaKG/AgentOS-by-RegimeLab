# Launch draft — X / social (staged, owner-publish only)

**Status:** STAGED — do not auto-post. Owner publishes after repo is public
and claim inventory + cold path pass.

**Repo:** https://github.com/floridaKG/AgentOS-by-RegimeLab  
**License:** Apache 2.0 · open-core by Regime Lab

---

## Short post (≤280 chars aim)

Agent OS — a shared operating layer for AI coding agents.

Local SQLite memory, skills, MOE tiers (including persistent multi-iteration
work), and dispatch scaffolding around the CLIs you already use.

Core needs no cloud keys. Optional backends when you want them.

https://github.com/floridaKG/AgentOS-by-RegimeLab

---

## Longer thread draft

1/ Agent OS is out (open-core, Apache 2.0).

It’s not a new model. It’s a harness under Claude Code, Codex, OpenCode, and
other agents that can connect with setup — shared local memory, workflows, and
optional multi-agent dispatch.

2/ Default path is boring on purpose: install → `memory-st write` → `recall`
finds it. SQLite on your machine. No hosted services required for the core.

3/ When one model isn’t enough: MOE tiers from cheap parallel panels up to
persistent multi-iteration collaborate/red-team style loops. Patterns you run
— not an automatic gate on every commit.

4/ Visual map (clone + open in browser):
`docs/assets/oss-architecture-diagram.html`

5/ What you supply: your agent CLIs and API keys when you want multi-agent or
MOE. ACPx for real dispatch. Pinecone/Neo4j/Hindsight optional.

Repo: https://github.com/floridaKG/AgentOS-by-RegimeLab

---

## Profile blurb (GitHub / org)

Agent-agnostic harness for AI coding agents — local SQLite memory, skills,
workflow patterns, and ACP dispatch scaffolding. Apache 2.0 by Regime Lab.
Local core; cloud backends opt-in.

---

## Claims checklist (before post)

- [ ] Repo unauthenticated HTTP 200 (public)
- [ ] No “every agent / automatic gate / private parity / works out of the box”
- [ ] Link matches intended repository
- [ ] Diagram/video paths exist in tree
- [ ] Cold path documented in README matches verified commands
