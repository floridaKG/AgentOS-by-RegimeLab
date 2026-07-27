# Agent Report Conventions

> Standard format for task reports. Every agent ends every report
> with the sections below.

## Required Closing Sections

Every task report must end with these three sections, in this order:

### STUMBLES:

List anything that was blocked, worked around, or uncertain during
the task. Include the specific error, what you tried, and what
remains unresolved.

Format:
```
STUMBLES:
- describe what went wrong, what you tried, and what is unresolved
```

### CONFIRMED:

List every surface or component you touched that worked correctly
without stumbling. This gives the reviewer confidence that those
areas are sound.

Format:
```
CONFIRMED:
- surface / component A — verified working
- surface / component B — verified working
```

### ARTIFACTS:

List every file created or modified during the task. Include the
full path and a one-line summary of the change.

Format:
```
ARTIFACTS:
- path/to/file — summary of change (created/updated)
- path/to/other/file — summary of change (created/updated)
```

## Example

```
STUMBLES:
- Source path PINECONE_API_KEY uses pcsk_ prefix but env var
  wasn't exported; worked around by sourcing secrets.env manually

CONFIRMED:
- agent-os-boot.sh — config.env sourcing fix verified
- docs/BOOT_FACTS.yaml — created, no syntax errors

ARTIFACTS:
- scripts/agent-os-boot.sh — updated config.env source path
- docs/BOOT_FACTS.yaml — created boot facts for session routing
```

## When to Omit

Do not include these sections in informal or intermediate messages
(e.g., "I found the file, reading it now"). They are required in
every final deliverable report.
