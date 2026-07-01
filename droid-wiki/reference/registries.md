# Registries

## Overview

Agent OS uses YAML-based registries under `registry/` as the source of truth for all system capabilities. Registries make the system's capabilities inspectable and machine-readable without requiring code execution. Each registry is validated by `scripts/registry-check.py`.

## Registry files

| File | Contents | Schema |
|---|---|---|
| `skills.yaml` | 10 os-shared skill definitions | name, tier, status, path, trigger, description, user_invocable |
| `tools.yaml` | 21 CLI tool definitions | id, binary, purpose, invocation |
| `workflows.yaml` | 7 workflow definitions | name, description, triggered_by, steps, status |
| `agents.yaml` | 3 agent integrations | id, description, invocation_template, role_strengths, use_when |
| `hard_rules.yaml` | 7 enforced governance rules | id, rule, rationale, scope, severity, status |
| `memory_tiers.yaml` | 3 memory tier definitions | id, layer, backend, path, scope, write_via, read_via, status, notes |
| `mcp_servers.yaml` | MCP server configurations | Server name, description, tools, configuration (currently empty) |
| `workspaces.yaml` | Workspace templates | id, name, root, boot_doc, skills_prefix, lessons_path (currently template only) |
| `agent-manifest.yaml` | Public distribution summary | version, distribution, license, summary counts, source paths |

### Current counts (from agent-manifest.yaml)

| Registry | Count |
|---|---|
| Skills | 10 |
| Tools | 21 |
| Workflows | 7 |
| Agents | 3 |
| MCP Servers | 0 |
| Memory Tiers | 3 |

## Registry schemas

### skills.yaml

```yaml
skills:
  - name: <string>          # Skill identifier
    tier: <string>           # os-shared | workspace-* | personal
    status: <string>         # active | planned | deprecated | archived
    path: <string>           # Path to SKILL.md
    trigger: [<string>]      # Trigger phrases
    description: <string>    # One-line description
    user_invocable: <bool>   # Can users invoke directly
```

### tools.yaml

```yaml
tools:
  - id: <string>             # Tool identifier
    binary: <string>         # Path or name of executable
    purpose: <string>        # What the tool does
    invocation: <string>     # Example invocation
```

### workflows.yaml

```yaml
workflows:
  - name: <string>           # Workflow identifier
    description: <string>    # What the workflow does
    triggered_by: <string>   # Trigger mechanism
    steps: [<string>]        # Ordered action list
    status: <string>         # active | draft
```

### agents.yaml

```yaml
agents:
  - id: <string>             # Agent identifier
    description: <string>    # Capability summary
    invocation_template: <string>  # CLI template with {{prompt}}/{{model}}
    role_strengths: [<string>]     # Roles this agent excels at
    use_when: <string>       # When to dispatch
```

### hard_rules.yaml

```yaml
rules:
  - id: <string>             # Stable slug
    rule: <string>           # Directive or prohibition
    rationale: <string>      # Why it exists
    scope: [<string>]        # Affected workspaces (or "all")
    severity: <string>       # blocking | warning | suggestion
    status: <string>         # active | draft | deprecated
```

### memory_tiers.yaml

```yaml
tiers:
  - id: <string>             # Tier identifier
    layer: <string>          # short-term | long-term-vector | long-term-graph
    backend: <string>        # Database or service
    path: <string>           # Storage path
    scope: <string>          # Data scope
    write_via: <string>      # Write CLI command
    read_via: <string>       # Read CLI command
    status: <string>         # core | optional
    notes: <string>          # Additional details
```

## Registry validation

The `scripts/registry-check.py` validator performs these checks:

| Check | Scope | Description |
|---|---|---|
| YAML parse | All files | All registry files must parse as valid YAML |
| Unique IDs | All files | All entries with `id`/`name` must have unique values |
| Binary resolution | `tools.yaml` | Tool binaries must resolve (file exists or command available) |
| Skill path existence | `skills.yaml` | SKILL.md paths must exist (warnings for missing) |
| Workflow fields | `workflows.yaml` | Entries must include trigger and invocation info |
| Agent fields | `agents.yaml` | Entries must include all required fields |
| Hard rules schema | `hard_rules.yaml` | Validated by hard-rule-smoke.sh |
| Manifest counts | `agent-manifest.yaml` | Summary counts must match dry-run build |
| Discoverable_by | `skills.yaml` | Deprecated field warning for non-legacy active skills |

### Usage

```bash
# Standard check (exits non-zero on failures)
python3 $AGENT_OS_HOME/scripts/registry-check.py

# JSON output
python3 $AGENT_OS_HOME/scripts/registry-check.py --json

# Strict mode (exits non-zero on warnings too)
python3 $AGENT_OS_HOME/scripts/registry-check.py --strict
```

## How to add entries

### Adding a skill

1. Create the SKILL.md file at `skills/shared/<name>/SKILL.md`
2. Add a skill entry to `registry/skills.yaml` with all required fields
3. Add a tool entry to `registry/tools.yaml` if the skill has CLI tools
4. Add a workflow entry to `registry/workflows.yaml` if it defines a workflow
5. Run `scripts/registry-check.py` to validate

### Adding an agent

1. Add an entry to `registry/agents.yaml` with the agent's invocation template and role strengths
2. Update `.config/agent-workflows/roles.toml` to map roles to the new agent
3. Run `scripts/registry-check.py` to validate

### Adding a tool

1. Place the executable in `bin/` or `scripts/`
2. Add a tool entry to `registry/tools.yaml` with binary path and example invocation
3. Run `scripts/registry-check.py` to validate

### Adding a workflow

1. Add a workflow entry to `registry/workflows.yaml` with description, trigger, steps, and status
2. Run `scripts/registry-check.py` to validate

### Adding a hard rule

1. Add a rule entry to `registry/hard_rules.yaml` with id, rule, rationale, scope, severity, and status
2. Run `scripts/registry-check.py` to validate

### Updating the manifest

After adding or removing entries, rebuild the manifest:

```bash
python3 $AGENT_OS_HOME/scripts/build-manifest.py
```

## Key files

| File | Purpose |
|---|---|
| `registry/*.yaml` | All registry files |
| `scripts/registry-check.py` | Registry validation script |
|  `scripts/hard-rule-smoke.sh` | Hard rules schema validator |
| `scripts/build-manifest.py` | Manifest builder |
