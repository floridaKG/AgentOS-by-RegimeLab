# Documentation audit

## Purpose

The documentation audit feature (triggered via `/doc-audit`) scans documentation for quality issues: drift from the codebase, duplication across pages, undocumented frontmatter, stale content, and overall consistency problems.

## How it works

The skill runs an audit rubric against the canonical SAST (System Architecture Source of Truth). It checks:

- **Drift** — whether documentation matches the current codebase state
- **Duplication** — overlapping or redundant content across pages
- **Frontmatter quality** — whether pages have proper metadata (title, status, source of truth)
- **Staleness** — content that has not been updated despite codebase changes
- **Registry consistency** — whether registry entries match the files on disk

The audit produces a report with findings organized by severity. Each finding includes the file location and a description of the issue.

## Key source files

| File | Purpose |
|---|---|
| `skills/shared/doc-audit/SKILL.md` | Skill definition and instructions |
| `docs/SYSTEM_ARCHITECTURE_SOURCE_OF_TRUTH.md` | Canonical SAST reference |
| `INDEX.md` | Master index for cross-referencing |
