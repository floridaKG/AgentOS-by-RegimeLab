# AGENT_SETUP.md — Agent-driven setup sequence

**Audience:** an AI coding agent (Claude Code, Codex, or any agent with shell
access) that the user has pointed at this repository.

**Purpose:** take a fresh Agent OS install from "installed" to "fully
configured" — rtk, ACPx, CodeGraph, agent profiles, provider wiring, roles,
and workspace routing — with a verification gate after every step.

**Read order:** `AGENTS.md` → this file → `docs/BOOT_FACTS.yaml`.

## Hard rules (do not violate)

1. Never ask for, read, or store the user's Anthropic API key. Claude Code's
   own login is the credential for the Claude lane.
2. Detect, don't collect: look for existing credentials in the environment
   and config files first; ask the user only when a credential is genuinely
   absent, in one plain sentence.
3. Never write secrets into the repository. User config lives in
   `~/.config/agent-os/config.env` (chmod 600).
4. Never fabricate output. If a step cannot be verified, report BLOCKED with
   the reason and stop.
5. Do not modify files outside the install home, the config paths below, and
   the workspace paths the user gives you.

---

## Step 0 — Preflight

- Confirm the OS: Linux or WSL2. If macOS, stop and report BLOCKED (v1 does
  not claim macOS support).
- Confirm `$AGENT_OS_HOME` resolves and points at the Agent OS install.
- Run `agent-os setup --check` and record the JSON output. That is your gap
  list for the rest of the sequence.

## Step 1 — Core install

- If `agent-os doctor` exits clean, skip to Step 2.
- Otherwise re-run the installer (idempotent, safe to re-run):
  `./install.sh --with-rtk`
- `source ~/.config/agent-os/config.env`
- **Gate:** `agent-os doctor` exits 0, and
  `bash scripts/agent-os-health.sh` reports the local tier GREEN.

## Step 2 — External tooling (rtk, ACPx, CodeGraph)

- rtk: confirm `rtk --version` works. If missing, re-run
  `./install.sh --with-rtk` (uses the bundled binary; no download needed on
  Linux x86-64).
- Node/npm: if `node --version` is below 18 or missing, tell the user to
  install Node.js 18+ and pause until they confirm.
- ACPx: `npm install -g acpx` if `acpx` is missing. Non-fatal: if npm fails,
  note it and continue; ACP dispatch stays unavailable until resolved.
- CodeGraph: `npm install -g @codegraph/cli` if `codegraph` is missing.
  Non-fatal.
- **Gate:** `agent-os setup --check` shows acpx/codegraph/rtk ready, or a
  documented reason they are not.

## Step 3 — Agents

- Detect which agent CLIs are installed: `claude`, `codex`, `pi`, `omp`,
  `grok`, `droid`.
- For each present agent, verify it can be dispatched through ACPx:
  `acpx <agent> exec "ping"`. If the profile is missing, create it using
  ACPx's own profile configuration (`acpx --help`; ACPx is an external tool
  with its own contract).
- If `claude` is absent and the user wants it: install it with the user's
  confirmation, then have the user complete `claude` login (interactive
  auth; the agent cannot do this for them).
- Optional agents (pi, omp, grok, droid) are not required. Install npm-
  installable ones only with the user's explicit confirmation; for others,
  print the setup instructions and continue.
- **Gate:** at least one of `claude` or `codex` responds to
  `acpx <agent> exec "ping"` before continuing.

## Step 4 — Providers (detect, don't collect)

- Read `~/.config/agent-os/config.env` and the environment for:
  - `ANTHROPIC_API_KEY` (usually absent; fine — Claude Code login covers it)
  - `OPENROUTER_API_KEY`
  - `OPENAI_BASE_URL` (defaults to `https://openrouter.ai/api/v1`)
- Wire whatever exists into `~/.config/agent-os/config.env` (chmod 600,
  preserve all other lines).
- If nothing exists for the open-source lane, ask the user exactly one
  question: "Which provider do you use for open-source models like DeepSeek?
  OpenRouter, an OpenAI-compatible endpoint, or none yet" and write what they
  provide. If none yet, record it under NEXT and continue.
- **Gate:** `agent-os setup --check` providers section reflects reality.

## Step 5 — Roles and workspace routing

- Ask the user for their real workspace paths. Never assume
  `$HOME/projects/*`.
- Write `~/.config/agent-workflows/roles.toml`:
  - `architect`, `reviewer`, `escalation`, `hard_escalation` → `claude`
    (expensive lane)
  - `explorer` → the user's chosen cheap agent (the one carrying open-source
    models)
  - `executor` → `codex` if present, else `claude`
  - `[workspaces]` → the user's real paths
- **Gate:** the file parses as TOML and contains the user's paths, not
  placeholders.

## Step 6 — Close-out

- Write the marker file:
  `$AGENT_OS_HOME/.local/state/agent-os/setup-complete`
  (one line: ISO date + agent id).
- Final verification:
  - `agent-os doctor`
  - `bash scripts/agent-os-health.sh`
  - `acpx <agent> exec "ping"` for every configured agent
  - `agent-os setup --check` now reports `"setup_complete": true`
- **Gate:** all of the above pass. If any fail, fix or report BLOCKED.

## Step 7 — Report

Use this exact format so the user (and future agents) know where things stand:

```
SETUP COMPLETE   (or: SETUP PARTIAL — <reasons>)

READY:
- local core (memory, CLI, health)
- rtk
- acpx / codegraph
- agents: <list with ping status>
- roles.toml with workspaces: <paths>

NEXT (manual):
- <interactive logins, provider signups, skipped agents>

SKIPPED:
- <anything not installed, and why>
```

---

## Interpretation for agents

- `"setup_complete": true` in `agent-os setup --check` means the boot sequence
  will not show FIRST RUN and the system is considered configured.
- If the user re-points you at this repo after setup, do NOT re-run the
  sequence. Verify with `agent-os setup --check` and proceed.
