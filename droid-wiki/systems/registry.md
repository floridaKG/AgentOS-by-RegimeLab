# Registry

## Purpose

Agent OS uses YAML-based registries to define all system capabilities in a machine-readable format. This page describes the registry architecture, file schemas, and how registries are validated.

## Registry files

All registries live in the `registry/` directory:

| File | Purpose | Entries |
|---|---|---|
| `registry/skills.yaml` | Skills registry | 10 skills |
| `registry/tools.yaml` | Tools registry | 21 tools |
| `registry/workflows.yaml` | Workflows registry | 7 workflows |
| `registry/agents.yaml` | Agents registry | 3 agents |
| `registry/memory_tiers.yaml` | Memory tiers registry | 3 tiers |
| `registry/hard_rules.yaml` | Hard rules registry | 7 rules |
| `registry/mcp_servers.yaml` | MCP servers registry | 0 (template) |
| `registry/workspaces.yaml` | Workspaces registry | 0 (template) |
| `registry/agent-manifest.yaml` | Auto-generated manifest | Summary |

## Schema overview

Each registry file follows a consistent YAML schema pattern:

### Skills schema (`registry/skills.yaml`)

```yaml
skills:
  - name: <string>          # Unique skill identifier
    tier: <string>          # os-shared, workspace-*, or personal
    status: <string>        # active, draft, deprecated
    path: <string>          # $AGENT_OS_HOME-relative path to SKILL.md
    trigger: [<string>]     # List of trigger phrases
    description: <string>   # One-line description
    user_invocable: <bool>  # Whether users can invoke directly
```

### Tools schema (`registry/tools.yaml`)

```yaml
tools:
  - id: <string>            # Unique tool identifier
    binary: <string>        # Path to executable
    purpose: <string>       # Description
    invocation: <string>    # Usage example
```

### Workflows schema (`registry/workflows.yaml`)

```yaml
workflows:
  - name: <string>          # Unique workflow name
    description: <string>   # Description
    triggered_by: <string>  # Trigger event or command
    steps: [<string>]       # Ordered list of steps
    status: <string>        # active, draft, deprecated
```

### Hard rules schema (`registry/hard_rules.yaml`)

```yaml
rules:
  - id: <string>            # Stable unique slug
    rule: <string>          # Plain text prohibition or directive
    rationale: <string>     # Why this rule exists
    scope: [<string>]       # Affected workspaces (or "all")
    severity: <string>      # blocking, warning, suggestion
    status: <string>        # active, draft, deprecated
```

## Registry validation

The `scripts/registry-check.py` script validates registry consistency:

| Check | What it verifies |
|---|---|
| YAML validity | All files parse without errors |
| Path resolution | All $AGENT_OS_HOME paths resolve to existing files |
| Schema compliance | Entries have required fields |
| Cross-references | Registry entries reference valid targets |
| Duplicate detection | No duplicate IDs or names |
| File presence | Referenced files exist on disk |

## Adding a new entry

To add a new skill, tool, workflow, or agent:

1. Create the implementation (SKILL.md, script, or binary)
2. Add an entry to the corresponding registry file
3. Run `python3 scripts/registry-check.py` to validate
4. Update `INDEX.md` if the entry should appear there

## Key source files

| File | Purpose |
|---|---|
| `registry/` | All registry files |
| `scripts/registry-check.py` | Registry validation script |
| `INDEX.md` | Master index derived from registries |
| `registry/agent-manifest.yaml` | Auto-generated summary manifest |
