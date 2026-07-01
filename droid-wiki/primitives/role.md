# Role

## Overview

A role defines an agent's responsibility within the Agent OS dispatch system. Roles map tasks to the most appropriate agent and model, enabling the ACP (Agent Communication Protocol) to route work effectively. Roles are defined in `roles.toml` and agent capabilities are documented in `registry/agents.yaml`.

## Agent roles in ACP dispatch

The ACP dispatch system assigns tasks based on role. Each role specifies a model and provider, allowing different agents to be used for different types of work:

| Role | Default Provider | Typical Use |
|---|---|---|
| **Explorer** | opencode | Parallel exploration, fast review, cheap model hosting |
| **Architect** | claude | Complex reasoning, system design, architecture decisions |
| **Executor** | codex | Deep code analysis, complex refactoring, implementation |
| **Reviewer** | claude | Code review, correctness analysis, team coordination |
| **Code Reviewer** | codex | Diff analysis, bug detection, code quality checks |
| **Escalation** | claude | Tasks requiring stronger reasoning and orchestration |
| **Hard Escalation** | claude | The most demanding tasks requiring maximum capability |

### Escalation path

When a task exceeds the capabilities of the initial role, it escalates:

1. Initial dispatch to the most appropriate role based on task type
2. If the task fails or proves too complex, escalation to a stronger model
3. Hard escalation for tasks that require the maximum available reasoning capacity

## Role definition in roles.toml

Roles are defined in `.config/agent-workflows/roles.toml` using TOML sections:

```toml
[explorer]
model = "default"
provider = "opencode"
cost = "user-configured"

[architect]
model = "default"
provider = "claude"
cost = "user-configured"

[executor]
model = "default"
provider = "codex"
cost = "user-configured"

[reviewer]
model = "default"
provider = "claude"
cost = "user-configured"

[code_reviewer]
model = "default"
provider = "codex"
cost = "user-configured"

[escalation]
model = "default"
provider = "claude"
cost = "user-configured"

[hard_escalation]
model = "default"
provider = "claude"
cost = "user-configured"
```

Each role section contains:

| Field | Type | Description |
|---|---|---|
| `model` | string | Model identifier (default or specific model name) |
| `provider` | string | Agent/provider that handles this role |
| `cost` | string | Cost tier (user-configured) |

The `model = "default"` value means the provider's default model is used. Users can override this with specific model IDs.

## Agent registry

Agent capabilities are documented in `registry/agents.yaml`:

| Agent | Strengths | Use When |
|---|---|---|
| **claude** | reasoning, review, orchestration | Complex reasoning, code review, team coordination |
| **codex** | code archaeology, refactoring, analysis | Deep code analysis, complex refactoring |
| **opencode** | parallel exploration, fast review | Cheap/free model hosting, parallel exploration |

Each agent entry includes:

| Field | Type | Description |
|---|---|---|
| `id` | string | Agent identifier |
| `description` | string | One-line capability summary |
| `invocation_template` | string | CLI invocation template with `{{prompt}}` and `{{model}}` placeholders |
| `role_strengths` | list | Which roles this agent excels at |
| `use_when` | string | Guidance on when to dispatch to this agent |

## Workspace routing

Roles.toml also defines workspace routing:

```toml
[workspaces]
home = { path = "$AGENT_OS_HOME" }
project-a = { path = "$HOME/projects/project-a" }
project-b = { path = "$HOME/projects/project-b" }
vault = { path = "$VAULT_PATH" }
```

Each workspace maps to a filesystem path. When dispatching a task, ACP uses the workspace to set the working directory and load workspace-specific context.

## Model profiles

Model profiles are user-configured through `~/.config/agent-workflows/`:

- `roles.toml` — Role-to-agent mappings
- `panels.toml` — MOE panel definitions
- `model_aliases.toml` — User-defined model aliases

The default installation provides example configurations that users customize to match their installed providers. Agent OS does not store provider credentials — these remain in each provider's normal CLI configuration.

## Role strengths

Role strengths guide dispatch decisions:

- **reasoning** — Strong analytical and problem-solving capability
- **review** — Code and design review capability
- **orchestration** — Multi-step task coordination
- **code archaeology** — Deep codebase navigation and understanding
- **refactoring** — Safe code transformation
- **analysis** — Systematic analysis of code and architecture
- **parallel exploration** — Fast, broad investigation across multiple paths

## Key files

| File | Purpose |
|---|---|
| `.config/agent-workflows/roles.toml` | Role-to-agent and workspace definitions |
| `registry/agents.yaml` | Agent capability registry |
| `skills/shared/acp/SKILL.md` | ACP skill with dispatch instructions |
| `bin/acp-task` | ACP task dispatch CLI |
| `bin/team` | MOE and multi-agent panel dispatcher |
