# Getting Started

You just installed Agent OS. Here's what to do in your first 10 minutes.

Every step produces visible output. Skip anything you don't need yet.

---

## Step 1: Verify it works (30 seconds)

```bash
source ~/.config/agent-os/config.env
bash $AGENT_OS_HOME/scripts/agent-os-health.sh
```

You should see "All checks passed." Optional services (Pinecone, Neo4j) will
show "not configured" — that's expected. You haven't set them up yet.

**If it fails:** Run `./install.sh` again. The installer is idempotent — it
won't overwrite your config.

---

## Step 2: Your first memory (2 minutes)

Agent OS memory is empty when you first install it. Let's seed a demo record
so you can see how `recall` works.

### Write a record

```bash
echo "The login endpoint at /api/auth/login rate-limits after 5 failed attempts per IP address. The cooldown is 15 minutes. This was confirmed by reading the rate limiter middleware in src/middleware/rate_limiter.py." > /tmp/demo_lesson.txt

memory-st write \
  --run-id "getting-started-001" \
  --agent-id "demo" \
  --workspace "demo" \
  --intent LESSON \
  --kind observation \
  --summary "Login endpoint rate-limits at 5 attempts per IP, 15min cooldown" \
  --content-file /tmp/demo_lesson.txt \
  --source-ref "getting-started:demo"
```

Expected output: `{"ok": true, "id": "st_...", ...}`

### Recall it

```bash
recall "how many failed login attempts trigger rate limiting"
```

Expected output: the record you just wrote, with its summary and content.

This is the core loop: agents write lessons, agents recall them later. Memory
accumulates with every session.

### Seed more demo data (optional)

Run the quickstart seeder for a richer demo experience:

```bash
./install.sh --quickstart
```

This writes 5 realistic demo records (API behavior, deployment gotchas, known
bugs) so `recall` returns interesting results immediately.

**Skip if:** You plan to start using Agent OS with your real agents. The demo
records are for exploration only.

---

## Step 3: Configure your agent provider (5 minutes)

Agent OS needs to know which agent CLIs you have installed and what models
they use. Edit your roles configuration:

```bash
nano ~/.config/agent-workflows/roles.toml
```

The shipped file has placeholder values. Replace them with your actual setup:

```toml
[explorer]
model = "claude-sonnet-4-20250514"    # your actual model ID
provider = "claude"                    # claude, codex, or opencode
cost = "user-configured"

[executor]
model = "gpt-5.1"                      # your actual model ID
provider = "codex"
cost = "user-configured"
```

**What provider means:**
- `claude` — you have the Claude Code CLI installed (`claude` command)
- `codex` — you have the Codex CLI installed (`codex` command)
- `opencode` — you have OpenCode installed (`opencode` command)

**What model means:** The model ID your CLI recognizes. Run your CLI's model
listing command to see available models (e.g., `claude models list`).

At minimum, configure the `explorer` and `executor` roles. Leave the rest as
placeholders until you need them.

**Skip if:** You don't plan to use ACP dispatch or multi-agent workflows yet.
The memory system works without any agent CLI.

---

## Step 4: Set up agent dispatch (10 minutes)

ACP (Agent Communication Protocol) lets your agents call each other. Claude
Code can dispatch a task to Codex. A reviewer agent can inspect work from an
executor.

### Install ACPx

ACPx is the universal agent launcher that drives dispatch:

```bash
npm install -g acpx
```

**Requires Node.js 18+.** If you don't have it: https://nodejs.org/

### Configure ACPx

```bash
acpx config set defaultAgent opencode
acpx config set format json
acpx config set approveAll true
```

### Start the daemon

The daemon polls for task envelopes and dispatches them to agents:

```bash
# In one terminal (or a tmux session):
tmux new-session -d -s acp "$AGENT_OS_HOME/bin/acp-daemon"

# Verify it's running:
$AGENT_OS_HOME/bin/acp-health
```

Expected: `daemon_alive: true`.

### Fire a task

```bash
acp-task explorer work "List the files in the current directory" --wait
```

If everything is configured correctly, the explorer agent reads your workspace
and returns results. If it stays in `queued` state, check:
- `acp-health` — is the daemon alive?
- `roles.toml` — are your model IDs correct?
- Is your agent CLI authenticated? Run `claude --version` or `codex --version`
  to confirm.

### One-shot vs persistent sessions

```bash
# One-shot: runs once, no history
acp-task executor work "Fix the auth bug" --wait

# Persistent: keeps context across dispatches
acp-task executor work "Fix the auth bug" --session auth-fix --wait
acp-task executor work "Update the tests too" --session auth-fix --wait
```

**Skip if:** You only use one agent and don't need dispatch. The memory system
and manual `recall` work without ACP.

---

## Step 5: Multi-agent workflows (5 minutes)

Once ACP dispatch works, try a multi-agent workflow:

```bash
# Swarm: 3 parallel explorers + synthesis reviewer
echo "What error handling patterns exist in this codebase?" > /tmp/task.txt
agent-workflow swarm /tmp/task.txt 3

# Council: 3 independent opinions + moderator
echo "Should we use async or sync for the data pipeline?" > /tmp/problem.txt
agent-workflow council /tmp/problem.txt
```

Workflows use the roles you configured in Step 3. If a role's provider isn't
configured, the workflow falls back to canned local output (clearly marked).

**Skip if:** You don't need multi-agent patterns yet.

---

## Step 6: Optional backends

Memory works fully with SQLite alone. Optional backends add capabilities:

| Backend | What it adds | Setup time |
|---------|-------------|------------|
| Pinecone | Semantic search across sessions | ~5 min |
| Neo4j | Graph relationships between records | ~10 min |
| Hindsight | Cross-agent memory sharing | ~15 min |

See [docs/OPTIONAL_BACKENDS.md](OPTIONAL_BACKENDS.md) for step-by-step setup,
or run `./install.sh --setup-memory` for an interactive walkthrough.

**Skip if:** SQLite-only memory is sufficient. Most users start here and add
backends later.

---

## What next?

| You want to | Read this |
|-------------|-----------|
| Understand the architecture | [docs/ARCHITECTURE.md](ARCHITECTURE.md) |
| Learn every memory command | [docs/MEMORY_USER_GUIDE.md](MEMORY_USER_GUIDE.md) |
| Set up Pinecone, Neo4j, or Hindsight | [docs/OPTIONAL_BACKENDS.md](OPTIONAL_BACKENDS.md) |
| Configure MOE panels | Edit `~/.config/agent-workflows/panels.toml` |
| See all available skills | `cat $AGENT_OS_HOME/registry/skills.yaml` |
| Run the full setup guide | [SETUP.md](SETUP.md) |

## Troubleshooting

**Health check shows "Python: FAIL" or "pyyaml not installed":**
```bash
pip install -r $AGENT_OS_HOME/requirements.txt
```

**ACP dispatch stays in "queued" state:**
1. `$AGENT_OS_HOME/bin/acp-health` — is the daemon alive?
2. `tmux has-session -t acp` — is the tmux session running?
3. Check daemon logs: `tail -40 ~/.local/state/agent-os/acp/logs/daemon.log`

**`recall` returns nothing:**
Memory starts empty. Write a lesson first (see Step 2), then try again.

**MOE panels fail with "unknown model":**
Your `panels.toml` or `model_aliases.toml` has placeholder values. Edit them
with your actual provider and model IDs.

**"acpx: command not found":**
ACPx isn't installed. Run `npm install -g acpx` (requires Node.js 18+).
