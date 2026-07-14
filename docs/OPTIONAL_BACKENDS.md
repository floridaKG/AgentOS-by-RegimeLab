# Optional Backends — Guided Setup

> How to go from SQLite-only (local core) to full-stack memory with semantic
> search, graph relationships, and cross-agent memory sharing. Follow the
> sections you want; skip the rest. Every backend degrades gracefully when
> unconfigured — there is no wrong order.

## Quick Decision Table

| Backend | What it gives you | Provisioning time | Cost |
|---------|-------------------|-------------------|------|
| Pinecone | Semantic search across sessions (vector similarity instead of keyword matching) | ~5 min | Free Starter tier (1 index) |
| Neo4j | Graph relationships between memory records (entity linking, provenance queries) | ~10 min | Free AuraDB tier (1 instance) |
| Hindsight | Cross-agent memory sharing via a shared bank digest bridge | ~15 min + running API | Self-hosted (your own API) |

All three are optional. Local SQLite memory works fully without any of them.

---

## Pinecone — Semantic Search

### What it gives you

Without Pinecone: `recall "how do I handle auth errors"` uses FTS5 keyword
matching. It finds records containing "auth" and "errors" but misses related
concepts like "authentication failure" or "login timeout."

With Pinecone: the same query finds semantically similar records across
sessions. Your agents can recall past lessons by meaning, not by keyword.

### Step 1 — Create a Pinecone account

1. Go to https://www.pinecone.io/
2. Click "Sign Up Free" (or "Get Started")
3. Create an account (email + password, or Google/GitHub SSO)
4. After login you land on the dashboard at https://app.pinecone.io/

### Step 2 — Create an index

1. From the Pinecone dashboard, click "Create Index" (or "Create your first index")
2. Fill in the form:
   - **Name**: `agent-vault` (or any name — update `PINECONE_INDEX` if different)
   - **Dimensions**: `1024` (Agent OS uses the `multilingual-e5-large` model, 1024-dimensional embeddings)
   - **Metric**: `cosine`
   - **Cloud provider**: AWS (default; any region works)
   - **Pod type**: Starter (free) — the `p1.x1` pod type is sufficient
3. Click "Create Index"
4. Wait ~30 seconds for the index to show status "Ready"

### Step 3 — Get your API key

1. In the Pinecone dashboard, click "API Keys" in the left sidebar
2. Copy the key (starts with `pcsk_` or `pcu_` — both work)
3. **Do not share this key.** It gives full access to your Pinecone account.

### Step 4 — Configure Agent OS

Add these two lines to `~/.config/agent-os/config.env` (uncomment the
existing placeholders):

```bash
export PINECONE_API_KEY="pcsk_your_key_here"
export PINECONE_INDEX="agent-vault"
```

### Step 5 — Verify

```bash
source ~/.config/agent-os/config.env
bash $AGENT_OS_HOME/scripts/agent-os-health.sh
```

Look for `✓ Pinecone: configured` in the Optional services section.

### Common pitfalls

- **"Index not found" at first recall**: The index needs a few records before
  vector search returns results. Run `memory-promote --target st-vector --dry-run`
  first to verify connectivity, then promote some records.
- **Starter index limit**: The free tier allows 1 index and ~100K vectors.
  Fine for personal use; upgrade if you exceed it.
- **Wrong dimension error**: If you get "dimension mismatch," delete the
  index and recreate it with dimension **1024**.

---

## Neo4j — Graph Memory

### What it gives you

Without Neo4j: memory records are flat rows in SQLite. You can search by text
but can't ask "what stumbles are related to this fix" or "which lessons
reference the same file."

With Neo4j: records become graph nodes with relationships. `memory-promote`
creates links between lessons, stumbles, files, and agents. The graph tier
answers "what else broke when we fixed X" and surfaces hidden connections.

### Step 1 — Create a Neo4j AuraDB instance

1. Go to https://neo4j.com/cloud/platform/aura-graph-database/
2. Click "Start Free" (or "Get Started Free")
3. Create an account (email + password, or Google SSO)
4. After login, click "Create Instance"
5. Choose "AuraDB Free"
6. Fill in:
   - **Instance name**: `agent-os` (or any name)
   - **Cloud provider**: Any (AWS us-east-1 is default)
7. Click "Create Instance"
8. Wait ~60 seconds for status "Running"

### Step 2 — Get your credentials

1. After creation, a dialog shows your credentials. **Save them immediately** —
   the password is shown only once.
2. Note three values:
   - **Connection URI**: looks like `neo4j+s://abc123.databases.neo4j.io`
   - **Username**: `neo4j` (default)
   - **Password**: auto-generated (e.g., `AbCdEfGh12345678`)

If you missed the dialog:
1. In the Aura console, click your instance
2. Click "..." → "Reset password" to generate a new one

### Step 3 — Configure Agent OS

Add these three lines to `~/.config/agent-os/config.env` (uncomment the
existing placeholders):

```bash
export NEO4J_URI="neo4j+s://abc123.databases.neo4j.io"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="your_generated_password_here"
```

### Step 4 — Initialize the schema

```bash
source ~/.config/agent-os/config.env
# The schema auto-applies on first promotion. Verify connectivity:
python3 -c "
import os
driver = __import__('neo4j').GraphDatabase.driver(
    os.environ['NEO4J_URI'],
    auth=(os.environ['NEO4J_USER'], os.environ['NEO4J_PASSWORD'])
)
driver.verify_connectivity()
print('Connected OK')
"
```

If `neo4j` Python package is missing: `pip install neo4j`

### Step 5 — Verify

```bash
bash $AGENT_OS_HOME/scripts/agent-os-health.sh
```

Look for `✓ Neo4j: configured` in the Optional services section.

### Common pitfalls

- **"Connection refused" or timeout**: AuraDB free instances sleep after ~3
  days of inactivity. Click the instance in the Aura console to wake it.
- **Password expired**: AuraDB passwords don't expire on the free tier. If you
  see an auth error, reset the password from the Aura console.
- **Schema not applied**: The Cypher schema (`memory/core/schema_neo4j.cypher`)
  is applied lazily. Run `memory-promote --target graph --dry-run` to trigger
  it explicitly.

---

## Hindsight — Cross-Agent Memory Sharing

### What it gives you

Without Hindsight: each agent's memory lives in its own SQLite database.
Lessons learned by Claude Code are invisible to Codex. Agents start cold.

With Hindsight: a shared memory bank collects digests from all your agents.
The bridge exports those digests into Agent OS SQLite, where every agent can
search them. Stumbles, lessons, and decisions accumulate across agents and
sessions.

### Step 1 — Install the Hindsight client

```bash
pip install 'hindsight-client>=0.4.22'
```

### Step 2 — Start the Hindsight API

```bash
# Install the server
pip install hindsight

# Start it (defaults to http://127.0.0.1:9177)
hindsight serve &
```

The API is now running locally. Verify:

```bash
curl -s http://127.0.0.1:9177/health | python3 -m json.tool
```

Look for `{"status": "ok"}`.

### Step 3 — Create a bank

A bank is a named container for your shared memories. Create one:

```bash
curl -s -X POST http://127.0.0.1:9177/banks \
  -H "Content-Type: application/json" \
  -d '{"id": "agent-os-shared", "profile": "default"}' | python3 -m json.tool
```

The bank ID (`agent-os-shared` in this example) is what you'll configure
below. Choose any name.

### Step 4 — Configure Agent OS

Add these lines to `~/.config/agent-os/config.env`:

```bash
export HINDSIGHT_API_URL="http://127.0.0.1:9177"
export HINDSIGHT_BANK="agent-os-shared"
export HINDSIGHT_PROFILE="default"
```

### Step 5 — Run the health check

```bash
source ~/.config/agent-os/config.env
python3 $AGENT_OS_HOME/scripts/hindsight-health-check.py
```

Expected output includes `client_ok: true` and `bank_ok: true`.

### Step 6 — Dry-run the bridge, then go live

```bash
# Dry-run: see what would be imported without writing anything
python3 $AGENT_OS_HOME/memory/hindsight_bridge.py --dry-run --limit 20

# Live import: export the 50 most recent digests into SQLite
python3 $AGENT_OS_HOME/memory/hindsight_bridge.py --limit 50
```

After the bridge runs, digests appear in Agent OS memory with tags
`origin:hindsight` and `hindsight`. They become searchable via `recall`
and `memory-st query`.

### Step 7 — Schedule the bridge (optional)

Add a cron entry to run the bridge hourly:

```bash
crontab -e
```

Add this line (adjust `$AGENT_OS_HOME` to your actual path):

```
0 * * * * /bin/bash -c 'source ~/.config/agent-os/config.env && python3 $AGENT_OS_HOME/memory/hindsight_bridge.py --limit 100'
```

### Step 8 — Lifecycle management (optional)

The GC tool helps manage bank size:

```bash
# Report on bank state
python3 $AGENT_OS_HOME/memory/hindsight_gc.py report

# Archive old digests (safe — no deletion)
python3 $AGENT_OS_HOME/memory/hindsight_gc.py export --older-than 30d
```

### Common pitfalls

- **"Connection refused" on the health check**: The Hindsight API isn't
  running. Start it with `hindsight serve &` and retry.
- **"Bank not found"**: The bank ID in `HINDSIGHT_BANK` doesn't match any
  bank on the API. List banks with
  `curl -s http://127.0.0.1:9177/banks | python3 -m json.tool`.
- **Bridge imports nothing**: An empty bank imports nothing — that's expected.
  Agents must write to the bank first. Use the `agent-voice` tool or your
  agent's native memory capture to populate it.
- **Hindsight vs Agent OS local memory**: Hindsight is a *shared* bank for
  cross-agent learning. Agent OS local SQLite is each agent's *private*
  short-term memory. The bridge copies from shared → local so every agent
  benefits from collective learning.

---

## All Three Together

The full-stack memory profile:

```bash
# ~/.config/agent-os/config.env
export AGENT_OS_HOME="$HOME/agent-os"
export LLM_PROVIDER="openai"
export LLM_API_KEY="your-api-key"

# Pinecone — semantic search
export PINECONE_API_KEY="pcsk_your_key"
export PINECONE_INDEX="agent-vault"

# Neo4j — graph relationships
export NEO4J_URI="neo4j+s://abc123.databases.neo4j.io"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="your_password"

# Hindsight — cross-agent memory sharing
export HINDSIGHT_API_URL="http://127.0.0.1:9177"
export HINDSIGHT_BANK="agent-os-shared"
export HINDSIGHT_PROFILE="default"
```

Verify everything at once:

```bash
source ~/.config/agent-os/config.env
bash $AGENT_OS_HOME/scripts/agent-os-health.sh
```

All three should show "configured" in the Optional services section. If any
show "not configured," check that the env var is exported (not just set) and
re-run `source ~/.config/agent-os/config.env` before the health check.
