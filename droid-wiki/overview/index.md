# Agent OS overview

Agent OS is an agent-agnostic harness - the operating system that AI coding agents run on. It is not a framework (imported library) but a harness that owns outcomes, learns from mistakes, and improves every cycle.

## What it does

Agent OS provides shared memory, cross-agent dispatch, workspace routing, and enforced governance so AI coding agents (Claude Code, Codex, OpenCode, Pi, and others) don't start every session cold. Every agent participates as a first-class citizen with shared context, durable task tracking, and the expectation to speak up about gaps and friction.

## Who uses it

Developers and teams who run multiple AI coding agents and need:

- **Cross-agent memory** - lessons learned by one agent are available to all
- **Agent-agnostic dispatch** - route tasks to the right agent regardless of model provider
- **Enforced protocols** - governance rules that agents follow automatically
- **Agent voice** - a feedback channel for agents to report friction and improvement ideas

## Quick links

- [Architecture](architecture.md) - system design and components
- [Getting started](getting-started.md) - install, configure, run
- [Glossary](glossary.md) - project-specific terms
- [How to contribute](../how-to-contribute/index.md) - working with the codebase
- [Features](../features/index.md) - user-facing capabilities
- [Systems](../systems/index.md) - internal architectural components
- [Reference](../reference/index.md) - configuration, data models, dependencies

## License

Apache 2.0. See `LICENSE`. Full commercial use, modification, and redistribution are permitted.
