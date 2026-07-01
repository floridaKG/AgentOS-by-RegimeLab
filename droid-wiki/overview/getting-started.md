# Getting started

Active contributors: kevin

## Prerequisites

- **Python 3.10+** — check with `python3 --version`
- **Git** (optional) — needed for skill updates
- **Node.js 18+** (optional) — needed for some external plugins (ACPx, CodeGraph)
- **One LLM provider API key** — OpenAI, Anthropic, or OpenRouter-compatible

### Supported platforms

- Linux (Debian/Ubuntu, Fedora, Arch)
- macOS (Homebrew or system Python)
- WSL2 (Windows Subsystem for Linux — required for Windows users)

## Quick install

```bash
git clone https://github.com/floridaKG/AgentOS-by-RegimeLab.git
cd AgentOS-by-RegimeLab
./install.sh
```

The installer is idempotent — running it again is safe and will not overwrite existing configuration.

## What the installer does

1. Checks prerequisites (Python, Git, Node.js)
2. Verifies repo structure
3. Creates `~/.config/agent-os/config.env` and `secrets.env`
4. Installs Python dependencies from `requirements.txt`
5. Verifies CLI facades in `bin/`
6. Initializes the memory directory
7. Installs user-editable MOE configuration under `~/.config/agent-workflows`

## Minimum configuration

After installation, edit `~/.config/agent-os/config.env`:

```bash
export AGENT_OS_HOME="$HOME/AgentOS-by-RegimeLab"
export LLM_PROVIDER="openai"    # or "anthropic", "openrouter"
export LLM_API_KEY="your-api-key-here"
```

Source this file in your shell profile:

```bash
source ~/.config/agent-os/config.env
export PATH="$AGENT_OS_HOME/bin:$PATH"
```

## Verify installation

```bash
bash $AGENT_OS_HOME/scripts/agent-os-health.sh
```

Expected output: all checks pass, memory health shows GREEN for local tier.

```bash
bash $AGENT_OS_HOME/scripts/agent-os-verify.sh
```

## First memory operation

```bash
# Initialize the memory database (first run only)
python3 $AGENT_OS_HOME/memory/core/short_term.py init

# Write a lesson
memory-st write --run-id test-run --agent-id test-agent --workspace home \
  --intent LESSON --kind observation \
  --summary "Test lesson" --content-file /dev/stdin \
  --source-ref cli:test <<< "This is a test lesson"

# Search for it
memory-recall --text "test lesson"

# Check memory health
bash $AGENT_OS_HOME/scripts/agent-os-health.sh
```

## Getting started checklist

1. Read `AGENTS.md` — the entry point for every agent session
2. Read `BOOT.md` — the intent router for matching tasks to capabilities
3. Explore `skills/shared/` — available shared skills
4. Read `memory/README.md` — memory system architecture
5. Try a recall: `memory-recall --text "test query"`

## Optional integrations

| Integration | Install | Configuration |
|---|---|---|
| Pinecone (semantic memory) | API key only | `PINECONE_API_KEY`, `PINECONE_INDEX` |
| Neo4j (graph memory) | API credentials | `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` |
| ACPx (universal agent launcher) | `npm install -g acpx` | Registry entry |
| CodeGraph (code structure queries) | `npm install -g @codegraph/cli` | `codegraph index` |

## Key source files

| File | Purpose |
|---|---|
| `install.sh` | Idempotent installer |
| `SETUP.md` | Full installation and configuration guide |
| `config.env.template` | Configuration template |
| `AGENTS.md` | Agent entrypoint and boot routing |
| `scripts/agent-os-health.sh` | Health check script |
| `scripts/agent-os-verify.sh` | Installation verification |
