---
id: cline
name: cline
trigger:
  - dispatch to cline
  - use cline
  - cline agent
  - free model
  - cline pass
scope: cross-workspace
status: stable
agents: any
description: Dispatch Cline through ACP using its live provider catalog and a dynamically selected free default.
---

# Cline ACP Agent

## Quick Reference

**Dispatch:** `acp-task cline <workspace> "<objective>" --wait`
**Direct:** `acpx --model <model_id> cline exec "<prompt>"`
**Provider:** Configured Cline provider and its live catalog
**Transport:** acpx -> JSON-RPC relay -> Cline --acp mode (streaming, tool visibility)

## When to Use Cline

- **Cheap/free execution** -- free provider models for parallel or low-stakes tasks
- **Streaming output** -- real-time agent_message_chunk events
- **Tool-using tasks** -- visible tool_call/tool_call_update events
- **Model diversity** -- access to provider models not available through other agents
- **Code modification** -- Act mode for making codebase changes

## Model Contract

- The default role model is the internal sentinel `agent-os/cline-free`.
- The Cline ACP wrapper resolves it at session creation to the first `:free`
  model advertised by Cline's live catalog.
- If Cline advertises no free model, dispatch fails closed instead of silently
  using a metered model.
- Explicit models must come from the live catalog returned by the configured
  Cline provider.
- The live catalog is authoritative; do not maintain a hardcoded model list.

## Constraints

- Free models may be rate-limited
- Explicit non-free selections must be included in the owner's Cline Pass
- No skill auto-loading (Cline's skill mechanism differs from Agent OS skills)
- One session per dispatch (multi-turn experimental)

## Agent OS Contract

- Prefer `acp-task cline ...` over direct invocation. The dispatcher supplies
  the assignment packet, boot documents, path constraints, report destination,
  and context selected by the dispatching agent.
- Read every packet boot document before acting. `$AGENT_OS_HOME/AGENTS.md` is the
  controlling runtime contract for home-workspace tasks.
- Dispatched Cline does not run hidden automatic recall. Memory context comes
  from the packet's `context_prefill`/`memory_context`, chosen by the dispatcher.
- For direct interactive Cline use, invoke `recall` manually when prior context
  is needed.
- Use shared skills by reading their registered `SKILL.md`; Cline does not
  automatically load Agent OS skills.
- Specs use the packet-provided boot docs and the canonical spec lifecycle.
  Never infer permission to edit, stage, commit, or push beyond the packet.
- Write the requested report/handoff to `packet.report_path`. Follow the report
  and handoff conventions supplied in the boot docs, including `STUMBLES:` and
  `CONFIRMED:` sections.

## Registration

| Registry | Status |
|----------|--------|
| `registry/agents.yaml` | cline (id, invocation, models, constraints) |
| `roles.toml` | [cline] role (provider=cline, cost=free) |
| `lib/acpx-dispatch.sh` | catalog-probe group (validates model availability) |

## Verification

Provider-free checks must prove role resolution, provider whitelist coverage,
wrapper syntax, free-sentinel resolution, and packet-context rendering. A live
prompt is optional and must never be used merely to discover the catalog.
