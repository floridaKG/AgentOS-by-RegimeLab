# Registry vs Reality Audit

Methodology for verifying that `$AGENT_OS_HOME/registry/tools.yaml` and
`$AGENT_OS_HOME/registry/skills.yaml` match what's actually available
to each agent.

Use this when: adding a new agent to the fleet, after registry edits, or when
running truth-harvest rounds.

## tools.yaml Audit

`tools.yaml` lists 21 entries with `binary`, `purpose`, and `invocation`.
Each entry is a claim that the binary exists and works.

### Step 1: Bulk `command -v`

```bash
command -v rtk agent-workflow log-stumble stumble-review agent-enter \
  ws-run-win now digest recall opencode codex claude vault-reindex kadd \
  acp-task check-models memory-st memory-promote memory-inject \
  memory-lt acpx
```

This resolves every binary path in one shot. Check that all return paths (not
errors). `memory-lt` is NOT in tools.yaml but exists and is functional — flag
it as a missing entry. `acpx` is also not in tools.yaml but is a primary ACP
dispatch tool.

### Step 2: Smoke test each binary

For each resolved binary, run `--help` or a minimal invocation to prove it
actually works, not just that the path exists. Examples:

| tools.yaml ID | Smoke command |
|---|---|
| rtk | `rtk ls .` |
| digest | `digest --help` (expects window arg, not a standard `--help`) |
| recall | `recall --help` |
| memory-st | `memory-st query --text "smoke" --limit 1` |
| memory-lt | `memory-lt health` |
| ws-run-win | `ws-run-win --probe` |
| now | `now` (deprecated, redirects to agent-os-boot) |


Catch: `memory-st health` is NOT a valid subcommand (unlike `memory-lt health`).
Only `init/write/query/get/update-status/mark-candidate/set-promote-state` are valid.

### Step 3: Check for unregistered tools

Cross-check against running processes and PATH. In this audit, `memory-lt` and
`acpx` were found to be functional but missing from tools.yaml.

## skills.yaml Audit

`skills.yaml` assigns each active os-shared skill a `native_loaders` list.
That field is a claim about installed/configured first-class skill mechanisms,
not a guarantee that every listed agent has passed a direct native invocation
probe in the current session. The legacy `discoverable_by` field is cosmetic
and must not be treated as a capability map.

### Step 1: Grep loader claims

```bash
grep -n 'native_loaders' $AGENT_OS_HOME/registry/skills.yaml
```

Check every `native_loaders` line for the claimed agent set and read the inline
verification note. If an agent is listed but the note says direct invocation is
unproven, do not upgrade that to "verified" without a live command.

### Step 2: Check actual discovery

From your native toolset, call:

```
skills_list
```

This returns every skill you can actually discover. Compare against what the
registry claims you can discover.

### Step 3: Verify loadability

For each skill the registry claims you can discover (or that you found in
step 2), try loading it:

```
skill_view(name='<skill-name>')
```

If `skill_view` succeeds, it's genuinely reachable. If it fails (not found,
even though `skills_list` listed it), the skill may be an MCP tool reference
or a naming mismatch.

### Step 4: Build the mismatch table

| Skill | Registry `native_loaders` | Direct native load proven? | Shell fallback works? | Mismatch |
|---|---|---|---|

## Common Findings

- **Registry fields have different meanings.** `native_loaders` is the current
  installed/configured mechanism field. `discoverable_by` is legacy/cosmetic
  and appears to be a rendering directive, not a functional permission boundary.
- **Configured does not mean direct invocation proven.** Treat Pi and Droid as
  configured/installed for os-shared skills until a live native invocation probe
  proves the skill loads in that agent surface.
- **Name collisions.** `pinecone-search` and `pinecone-upsert` os-shared skills
  can collide with MCP Pinecone tool names (`pinecone-search-records`,
  `pinecone-upsert-records`), causing `skill_view` to fail on the MCP name.
- **Unregistered tools.** Always check for working binaries that aren't in
  tools.yaml (e.g., `memory-lt`, `acpx`).
- **Shell-ext suffix mismatch.** `check-models` in tools.yaml resolves to
  binary `check-models.sh`. When grepping for the binary name, use the
  `.sh` suffix.

## Pitfalls

- `digest --help` expects a window argument (`1d|7d|30d|90d|all`), not a
  standard `--help` flag. It will error "Unknown window: --help" but that
  doesn't mean the tool is broken.
- `check-models.sh` emits a Python `AttributeError` on first subprocess call
  but recovers and produces valid output. The traceback is noise, not failure.
- `skills_list` may include entries that aren't real Skill.md files (MCP tool
  references). Cross-check with `skill_view` to confirm loadability.
