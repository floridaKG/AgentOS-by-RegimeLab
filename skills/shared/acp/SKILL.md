---
id: acp
name: acp
trigger:
  - /acp
  - dispatch to executor
  - hand this off to opencode
  - send to codex
  - delegate to
  - ask work to
  - ask docs to
scope: cross-workspace
status: stable
agents: claude, opencode, codex (the providers registered in `registry/agents.yaml`)
description: Dispatch a task to another agent in the multi-agent OS via ACP (Agent Communication Protocol). Use when handing off work to opencode, codex, or another role/workspace.
last_reviewed: 2026-06-15
---

# ACP -- Cross-Agent Task Dispatch

This skill is agent-agnostic. Any agent with WSL shell access can use it.
The CLI `acp-task` is the interface. The daemon (tmux session `acp` running
`$AGENT_OS_HOME/bin/acp-daemon`) picks up envelopes, dispatches to the right agent via
`roles.toml`, and routes results back.

## HARD RULE — sandboxed agents never launch workers directly

If you are a **sandboxed agent** (codex `exec`, or any agent whose sandbox
disables outbound network), you MUST NOT run `acpx … exec`, `acpx … prompt`,
`sidecar`, or any network one-shot yourself. Those need outbound network; your
sandbox blocks it and your approval reviewer will (correctly) refuse it as a
third-party export — that is exactly the failure that wedged codex on
2026-06-14. **Always enqueue via `acp-task <role> <ws> "<obj>"` instead** — that
is a local filesystem write with no network, and the *unsandboxed* daemon
launches the real worker for you. The `acp-task` write lane is already allowed;
choosing to launch `acpx` directly is the bug, not a missing permission. When in
doubt, write the envelope and let the daemon do the network.

## Backend proof — never trust `run.json from`

To prove which backend actually executed a run, do NOT read `run.json`'s `from`
field — that is the **sender** identity (e.g. `opencode/big-pickle`) and misled
agents on 2026-06-14. The real proof is the adapter's stderr line
`ACP_ADAPTER: calling acpx <agent> exec`, captured in the run's
`adapter_completed.stderr` / `events.jsonl`, plus the output artifact path. Get
it in one shot:

    acp-status --proof <run-id>

That prints the true adapter/model line and artifact, and a reminder that `from`
is the sender. Cite this, not `from`, as backend proof.

## Capability Inventory

ACP (the protocol) provides durable run records, filesystem-based message routing,
and a state machine (queued->claimed->running->succeeded/failed). acpx (v0.10.0,
the agent driver) adds persistent named sessions, crash reconnect, cooperative
cancel, prompt queueing with TTL, and a multi-agent flow runner.

**The three dispatch modes and their persistence model:**

| Flag | Mode | acpx call | Session lifetime | State on disk |
|------|------|-----------|-----------------|---------------|
| *(none)* | One-shot | `acpx <agent> exec` | Created for one prompt, torn down after | None |
| `--session <name>` | Persistent named session | `acpx <agent> prompt -s <name>` | Lives across dispatches, survives crashes | `~/.acpx/sessions/` |
| *(flow runner)* | Multi-agent DAG | `acpx flow run` | Per-run, mixed profiles | `~/.acpx/flows/runs/` |

**Do NOT assume ACP is always one-shot.** The default dispatch is one-shot
(disposable session), but `--session` provides full persistence identical to
a native agent session. The common pitfall is conflating the default mode with
the system's total capability. Verify before claiming.

## When To Use

- The work is better suited to a different provider (opencode for cheap
  volume, codex for code analysis, or claude for high-context reasoning)
- The work needs a specifically configured ACP role label and you have already
  verified its live `roles.toml` mapping
- The work belongs in a different workspace (home, work, docs, vault)
- You want parallel work happening while you continue here
- A second pair of eyes on code or a spec (reviewer role)

Use `$AGENT_OS_HOME/skills/shared/agent-workflows/SKILL.md` instead when
the job needs a workflow pattern rather than a single dispatch: `swarm`,
`council`, `dialogue`, `redteam`, `orchestrate`, or `worktree-loop`.

Do NOT use ACP for trivial lookups or anything you can answer locally faster.

## Roles (from `$AGENT_OS_HOME/.config/agent-workflows/roles.toml`)

| Role | Provider | Use For |
|------|---------|---------|
| explorer | opencode | Codebase search, "where is X" |
| architect | claude | Design, spec drafts |
| executor | codex | Implementation, file writes |
| reviewer | claude | Light review pass |
| code_reviewer | codex | Deep code review |
| escalation | claude | Hard problems |
| hard_escalation | claude | Last resort |

Fallback chains were removed on 2026-06-03 because the adapter only read the
first configured model. If a role's model is unavailable, the task fails until
`roles.toml` is changed.

## Workspaces

Workspaces are user-configurable. The default set:

- `home` -- Agent OS infrastructure (`$AGENT_OS_HOME`)
- `work` -- Primary coding workspace (user-configured)
- `docs` -- Documentation / knowledge workspace (user-configured)
- `vault` -- Vault knowledge vault

## Modes

ACP supports three dispatch modes, chosen by flags on `acp-task`:

### Mode 1: One-shot (default) — `acp-task <role> <ws> "<objective>"`

Calls `acpx <agent> exec -f <prompt_file>`. Creates a temporary disposable
session, runs the prompt, returns output, tears down. No state persistence
between dispatches. Best for self-contained queries.

```bash
acp-task executor work "Find the API endpoint entry point" --wait
```

### Mode 2: Persistent named session — `acp-task <role> <workspace> "<objective>" --session <name>`

Calls `acpx <agent> prompt -s <session_name>`. Creates a named session whose
state (message history) persists at `~/.acpx/sessions/` across dispatches.
The agent remembers context from previous turns. Survives crashes
(auto-respawn via acpx daemon). Supports cooperative cancel.

```bash
# First call creates the session
acp-task executor scratch "Research topic X" --session my-research --wait

# Subsequent calls resume the same session with full history
acp-task executor scratch "Follow up on finding Y" --session my-research --wait
```

### Mode 3: Multi-agent DAG — `acpx flow run`

Multi-step orchestration across different agent profiles with data passing
between nodes. Supports switch/case decision edges and mixed agent types.

```javascript
// .flow.mjs — ESM module, run: acpx flow run <file>
import { defineFlow, acp, compute } from 'acpx/flows';
export default defineFlow({
  name: 'research-chain',
  startAt: 'explore',
  nodes: {
    explore: acp({ profile: 'opencode', prompt: () => "..." }),
    synthesize: compute({ run: (ctx) => process(ctx.outputs) }),
    review: acp({ profile: 'opencode', prompt: (ctx) => `Review: ${ctx.outputs.synthesize}` }),
  },
  edges: [ { from: 'explore', to: 'synthesize' }, { from: 'synthesize', to: 'review' } ],
});
```

Verified 2026-05-28: 4-node DAG executed, data passed between nodes, outputs
preserved across acp/compute/acp chain.

## How To Invoke

The CLI is `acp-task` in WSL at `$AGENT_OS_HOME/bin/acp-task`.

### From inside WSL (any agent in a WSL shell)

```bash
acp-task <role> <workspace> "<objective>" [--body "..."] [--wait]
```

### From Windows-side Claude Code (vault Claude)

```bash
wsl -e bash -lc "acp-task <role> <workspace> '<objective>' --wait"
```

### From opencode or codex

Same as WSL invocation. The CLI is on PATH.

## Examples

### Pipeline task to the executor role

```bash
acp-task executor home "Audit the codebase for security issues" --wait
```

This dispatches through the provider configured for `executor` in
`roles.toml`.

### Fire and forget

```bash
acp-task executor home "Summarize today's session"
```

Returns `RUN_ID=task-...` immediately. Check status later.

### Block and stream the answer

```bash
acp-task explorer work "Find the API endpoint entry point" --wait
```

Blocks up to 6 minutes, prints the agent's output when complete.

### Hard problem to codex

```bash
acp-task escalation home "Diagnose why neo4j auto-seed is not wired" --wait
```

### Code review with detail

```bash
acp-task code_reviewer docs "Review the latest API endpoint" \
  --body "Focus on auth flow and SQL injection vectors in the user controller"
```

## Check Run Status

```bash
# List recent runs
ls -lt $AGENT_OS_HOME/.local/state/agent-os/acp/runs/ | head -10

# Events for a specific run
cat $AGENT_OS_HOME/.local/state/agent-os/acp/runs/<RUN_ID>/events.jsonl

# Agent output
cat $AGENT_OS_HOME/.local/state/agent-os/acp/runs/<RUN_ID>/artifacts/output_*.md

# Daemon health
$AGENT_OS_HOME/bin/acp-health
```

## Health Check

Daemon health is separate from provider health. Check the daemon first if
`acp-task --wait` hangs, if runs stay in `message_sent`, or if inbox files pile
up without `dispatch_started` events.

```bash
$AGENT_OS_HOME/bin/acp-health
```

Healthy output has `daemon_alive: true`. `inbox_messages` can be non-zero even
when healthy; it is a backlog count, not by itself a failure. `dead_letters`
should normally be `0`.

Codex sandbox caveat: sandboxed Codex may not be able to see host PIDs or tmux
sockets, so `$AGENT_OS_HOME/bin/acp-health` can report a false negative even while
the log is advancing. If the log mtime advances and host-level verification is
needed, rerun `$AGENT_OS_HOME/bin/acp-health` outside the sandbox or ask the owner
to run it from a direct terminal.

Verify all four ACP providers are working:

```bash
acp-provider-smoke [--timeout 150]
```

Dispatches a smoke prompt to opencode, codex, and claude, runs each through
the output validator, and reports pass/fail. JSON dump saved to
`~/.local/state/agent-os/acp/smoke/<date>.json`.

Do not hard-code a fixed “4/4 pass” claim into future docs. The saved smoke
JSONs are the truth surface, and different runs already show different results.
Inspect the latest artifact under `$AGENT_OS_HOME/.local/state/agent-os/acp/smoke/`
before claiming live provider health. Tool at `$AGENT_OS_HOME/bin/acp-provider-smoke`.

## Verification Recipes

Use prior ACP evidence before re-running a workflow or provider check.

```bash
sed -n '1,220p' $AGENT_OS_HOME/docs/checkpoints/<RUN_ID>-acp-task-report.md
sed -n '1,220p' $AGENT_OS_HOME/.local/state/agent-os/acp/runs/<RUN_ID>/events.jsonl
sed -n '1,220p' $AGENT_OS_HOME/.local/state/agent-os/acp/runs/<RUN_ID>/artifacts/output_*.md
```

Known ACP workflow proof points:

- `task-1780933092-fd5900f9`: `swarm.sh` synthesis rc hardening. Read the checkpoint report before re-testing `swarm`.
- `task-1780933094-38468b55`: original `agent-workflows` skill-body creation. This proves the skill content task, not registry/index integration.
- `task-1780933091-c612f342`: advisory `ACP_ALLOWED_ROOT` scoping for `acp-task` and `worktree-loop`. Do not overstate this as OS-enforced confinement.
- `task-1780933091-ec47e692`: `capability-check --live` added while default mode stayed advertisement-only.

When docs, current code, and saved evidence agree, cite the saved evidence and
avoid redundant live re-tests.

## Start Or Recover The Daemon

Symptoms: messages sit in `$AGENT_OS_HOME/.local/state/agent-os/acp/inboxes/workspaces/<ws>/`
forever, `acp-health` exits non-zero, or `acp-health` prints
`daemon_alive: false`.

Preferred recovery:

```bash
$AGENT_OS_HOME/bin/acp-health
tmux has-session -t acp 2>/dev/null || tmux new-session -d -s acp '$AGENT_OS_HOME/bin/acp-daemon'
$AGENT_OS_HOME/bin/acp-health
```

If `tmux has-session -t acp` succeeds but `acp-health` still reports
`daemon_alive: false`, inspect the stale session before replacing it:

```bash
tmux capture-pane -pt acp -S -80
tmux kill-session -t acp
tmux new-session -d -s acp '$AGENT_OS_HOME/bin/acp-daemon'
$AGENT_OS_HOME/bin/acp-health
```

Do not edit or blank the daemon pidfile by hand. `$AGENT_OS_HOME/bin/acp-daemon`
maintains `$AGENT_OS_HOME/.local/state/agent-os/acp/logs/daemon.pid` and uses a
lockfile to avoid duplicate active loops. After recovery, verify the log is
advancing:

```bash
tail -40 $AGENT_OS_HOME/.local/state/agent-os/acp/logs/daemon.log
```

Expected healthy loop lines include `ACP_SUPERVISE` and `ACP_DISPATCH`.

## Memory Injection

`acp-task` passes `--with-memory` by default. The dispatching agent receives
a `memory_context` populated by short-term SQLite + Neo4j Aura + Pinecone
queries scoped to the objective. If queries return no semantic match the
context is empty but the task still runs.

## Hard Rules

- Roles and workspaces are case-sensitive lowercase
- Objective is one line; use `--body` for detail
- Workspace must be one of: home, work, docs, vault (or user-configured names)
- Do not use this skill for trivial things — daemon cycles are not free

## Where Things Live

| What | Path |
|------|------|
| Helper | `$AGENT_OS_HOME/bin/acp-task` |
| Daemon | `$AGENT_OS_HOME/bin/acp-daemon` (manual start usually uses tmux session `acp`; watchdog/manual starts may leave it parented to PID 1) |
| Send script | `$AGENT_OS_HOME/.config/agent-workflows/acp/acp_send.py` |
| Roles config | `$AGENT_OS_HOME/.config/agent-workflows/roles.toml` |
| Run state | `$AGENT_OS_HOME/.local/state/agent-os/acp/runs/<RUN_ID>/` |
| acpx config | `~/.acpx/config.json` (defaultAgent=opencode, format=json, approve-all) |
| acpx sessions | `~/.acpx/sessions/` (named session state per `--session <name>`) |
| acpx flow runs | `~/.acpx/flows/runs/` |
| Full plan | Project-specific; document it in your own Agent OS docs repository |
| What works | `archive/2026-05/VERIFIED_WORKING.md` (archived) |

## Pitfalls

- **Model selection differs by provider.** `codex`, `claude`, and `opencode`
  are configured in `roles.toml`; their model values must match the live
  catalogs exposed by the installed CLIs.

- **events.jsonl uses event field, not state.** When polling ACP runs programmatically, look for event: dispatch_completed

- **Do NOT assume ACP is always one-shot.** This is the most common mistake.
  The default dispatch (`acp-task` without `--session`) is one-shot, but adding
  `--session <name>` gives full named-session persistence identical to a native
  agent terminal session. Answering "ACP has no session persistence" is wrong —
  verify before claiming. The Capability Inventory section above lists all three
  modes and their persistence models.
- **Do NOT conflate `acp-task` default mode with total ACP capability.** ACP is
  a protocol and run-record system; acpx is the agent driver that provides
  persistence, flow orchestration, and crash recovery. The default dispatch path
  uses one for convenience, but the system supports all three modes.
- **--session is for multi-turn work; default is for one-shots.** If a task needs
  follow-up context (research chains, iterative debugging, code review with
  memory), use `--session <name>`. If it's a self-contained query, the default
  one-shot is correct.
- **There are no fallback chains anymore.** If the configured model is
  unavailable, the task fails until `roles.toml` is changed.
- **opencode is slow through ACP.** Expect ~130s response time on the free
  tier for opencode dispatches. Claude is ~20-30s, codex ~15s. Set
  `--timeout` accordingly on `acp-provider-smoke`.

- **Worker timeout is 600s (10 min); escalation is 1800s.** Worker roles
  (executor, explorer, reviewer) get 600s in `acp_to_run_agent.sh`.
  Escalation roles get 1800s. If a task fails with `worker_timeout`, the task
  was too broad, so break it into focused pieces.

- **Task decomposition for free-tier workers.** Free-tier models are slower than paid. A task that takes Claude 20s might take a free model 120s. When dispatching complex work (spec execution, multi-file review + action), break it into 2-3 focused dispatches rather than one monolith. Example: (1) "read X and answer Q1-Q7", (2) "verify F1-F12 and fix what's broken", (3) "write summary". Each completes within the timeout.

## Completion Envelope (--json)

When `--wait --json` is used, `acp-task` returns a structured JSON completion
envelope instead of human-readable text. Every terminal state (success, failure,
timeout, cancellation) produces the envelope — including partial output on timeout.

```bash
acp-task reviewer home "review X" --wait --json
```

Returns:

```json
{
  "schema": "agent_os.acp.completion.v1",
  "run_id": "task-...",
  "state": "succeeded|failed|timeout|cancelled|blocked",
  "classification": "success|timeout|parse_error|auth_error|rate_limited",
  "elapsed_seconds": 140.1,
  "output_path": "/path/to/output.md",
  "has_partial_output": false,
  "summary": "...first 500 chars of output...",
  "budget": { "token_cap": 200000, "spent_usd": 0.0 }
}
```

**Key behaviors:**
- `has_partial_output: true` means the task timed out but produced useful results
- `classification` resolves `parse_error` → `timeout` when adapter stderr contains `worker_timeout`
- `summary` is the first 500 chars of the output artifact (may include boilerplate)
- Budget `spent_usd` is currently always 0.0 (not yet enforced)

**When to use `--json`:**
- After any ACP dispatch where you need to programmatically inspect the result
- When you need to know if partial output exists on timeout
- When building tooling that consumes ACP results (sidecar route facade, watchdogs)

**Standalone completion check:**
```bash
python3 $AGENT_OS_HOME/.config/agent-workflows/acp/acp_completion.py <run_id>          # human
python3 $AGENT_OS_HOME/.config/agent-workflows/acp/acp_completion.py <run_id> --json   # JSON
```

## After You Dispatch

Tell the user:
- The RUN_ID
- Which role + workspace + provider/model it went to
- Whether it used --session (persistent) or default (one-shot) mode
- Expected latency (based on the current mapped provider: ~130s for opencode free tier, ~20-30s for claude, ~15s for codex)
- How to check status if not using `--wait`
