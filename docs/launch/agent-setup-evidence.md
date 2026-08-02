# Agent-driven setup evidence

**Date:** 2026-08-02
**Method:** fresh isolated HOME (`AGENT_OS_TEST=1`, no cloud API keys injected,
no access to the owner's private runtime or state), test-mode install from the
public tree, then the `docs/AGENT_SETUP.md` sequence executed step by step.
**Tree:** public OSS repo (`AgentOS-by-RegimeLab`), working tree 2026-08-02.

## What this proves

1. A fresh install boots with FIRST RUN guidance and a headless gap report
   (`agent-os setup --check`), so an agent knows setup is required and what is
   missing.
2. After the setup sequence (roles written, marker written), the same reporter
   flips to `setup_complete: true` and boot no longer shows FIRST RUN.
3. The core install, health check, and memory path all work with zero cloud
   credentials (same cold path as `cold-path-evidence.md`).

## Clean install (isolated HOME)

```bash
AGENT_OS_TEST=1 AGENT_OS_TEST_HOME=<fresh-home> AGENT_OS_HOME=<repo> HOME=<launcher> bash install.sh --no-path
# exit 0
```

## Gap report before setup

```bash
agent-os setup --check
```

```
  os:            ready
  node:          ready
  npm:           ready
  acpx:          ready
  codegraph:     ready
  rtk:           ready
  agent claude   ready
  agent codex    ready
  agent pi       ready
  agent omp      ready
  agent grok     ready
  agent droid    ready
  anthropic key: absent
  openrouter key:absent
  openai base:   default (https://openrouter.ai/api/v1)
  roles_toml:    missing Run docs/AGENT_SETUP.md step 5 to write roles.toml
  setup_complete: false
```

JSON: `"roles_toml": {"status": "missing"}`, `"setup_complete": false`.

Note: this run machine already had Node, npm, acpx, CodeGraph, rtk, and the
agent CLIs on PATH, so the reporter shows them ready. On a stranger's machine
each of those appears `missing` with an exact fix hint (for example
`"acpx": {"status": "missing", "hint": "npm install -g acpx"}`). The npm
installs and interactive logins are the documented user-side steps in
`docs/AGENT_SETUP.md`; they are not exercised in this offline evidence run.

## Boot FIRST RUN

```bash
bash scripts/agent-os-boot.sh
```

```
  ⚡ FIRST RUN: Agent OS is installed but not configured.
     Follow docs/AGENT_SETUP.md to complete setup (rtk, ACPx, agents, roles).
     Quick diagnostic: agent-os setup --check
```

## Core verify

```bash
bash scripts/agent-os-health.sh
```

```
  •  Neo4j: not configured (optional)

All checks passed ✓
```

## Roles and workspace routing

`~/.config/agent-workflows/roles.toml` written by the sequence with the user's
real paths (expensive roles -> claude, explorer -> cheap lane, workspaces ->
user paths).

## Close-out

Marker written to `$AGENT_OS_HOME/.local/state/agent-os/setup-complete`.

## Verification after setup

```bash
agent-os setup --check
```

```
  roles_toml:    configured
  setup_complete: true
```

JSON: `"roles_toml": {"status": "configured"}`, `"setup_complete": true`.

Boot no longer shows FIRST RUN (0 matches).

## Honest limits of this evidence

- npm installs (acpx, CodeGraph), provider signups, and interactive logins
  (`claude`, `codex`) were not executed here: they need network and the user's
  accounts, which this offline clean-room does not have. They are documented
  as user-side NEXT steps in the sequence and in the README Known Limitations.
- Dispatch pings (`acpx <agent> exec "ping"`) are the documented gate in
  `docs/AGENT_SETUP.md` step 3; they require configured ACPx profiles and are
  not exercised in this run.

## Verdict

PASS — mechanism verified: first-run detection, headless gap reporter (JSON
contract stable, roles placeholder vs configured distinction correct), marker
close-out, and the before/after state flip all behave as documented.
