# Upward handoff

## Purpose

The upward handoff feature prepares findings for review by a higher-reasoning model. When an agent has completed investigative work and needs validation of correctness, edge case analysis, or resolution of deferred decisions, it produces a structured handoff document.

## How it works

The handoff follows the standard defined in `docs/HANDOFF_AUTHORING_STANDARD.md`. Each handoff document has five sections:

1. **Context** — what the agent was asked to do, including the original prompt or summary
2. **Raw findings** — bulleted facts about what was observed, changed, and tried
3. **Tensions** — where constraints pull in opposite directions (speed vs. correctness, etc.)
4. **Open questions** — what could not be resolved, with options considered
5. **Boundary notes** — what was explicitly not investigated

Handoffs are triggered via `/handoff` or the `upward-handoff` skill. The output is saved to `handoffs/active/` for the reviewer to pick up.

## Integration points

- Uses `docs/HANDOFF_AUTHORING_STANDARD.md` for the document format
- Integrates with `changes-review` for tracing changes back to findings
- Complements `doc-audit` for documentation quality review

## Key source files

| File | Purpose |
|---|---|
| `skills/shared/upward-handoff/SKILL.md` | Skill definition and instructions |
| `docs/HANDOFF_AUTHORING_STANDARD.md` | Handoff document standard |
| `docs/AGENT_REPORT_CONVENTIONS.md` | Report conventions (STUMBLES, CONFIRMED, ARTIFACTS) |
