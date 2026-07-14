# Optional ACP Agent Integrations

The public Agent OS distribution keeps its ACP contract provider-neutral. The
supported public roles and providers are defined by:

- `.config/agent-workflows/roles.toml`
- `registry/agents.yaml`
- `bin/acp-task`

To add another ACP-compatible agent, install and authenticate that agent
separately, then add a matching provider mapping and role configuration. Do not
assume that an internal or third-party agent is available in the public
distribution by default.

For the default public setup, use:

```bash
acp-task explorer work "Find the API entry point" --wait
acp-task reviewer docs "Review the documentation" --wait
```

ACPx remains an external dependency. Without `acpx` on `PATH`, the ACP daemon
records a safe dry-run instead of launching an agent.
