# Changes review

## Purpose

The changes review feature produces a traceable audit document that maps every change to its source finding. After applying fixes from stumble reports or closure findings, this skill creates an audit trail that makes it clear what was changed and why.

## How it works

When triggered via `/changes-review`, the skill:

1. Reads the source findings (stumble reports, review comments, etc.)
2. Identifies all changes made in response to those findings
3. Maps each change to its originating finding
4. Surfaces deferred decisions with full context
5. Produces a traceable audit document

The output is placed in the handoffs directory, ready for upward review by a higher-reasoning model.

## Integration points

- Complements `upward-handoff` for upward review of changes
- Integrates with `lesson` for capturing lessons learned during the review
- Works with `doc-audit` for documentation quality review

## Key source files

| File | Purpose |
|---|---|
| `skills/shared/changes-review/SKILL.md` | Skill definition and instructions |
| `docs/HANDOFF_AUTHORING_STANDARD.md` | Handoff document standard |
| `docs/AGENT_REPORT_CONVENTIONS.md` | Report conventions |
