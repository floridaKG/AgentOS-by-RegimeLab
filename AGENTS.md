# AGENTS.md — Agent OS Entrypoint

## Why Agent OS Exists

Agent OS is an agent-agnostic harness — the OS agents run on, not a
framework you import. We strive to be the best harness possible. That
means we surface friction and fix it. We don't cut corners. We own the
outcome. Every agent participates as a first-class citizen: shared
memory, ACP dispatch, enforced protocols, and the expectation to speak
up when you see a gap (use `python3 $AGENT_OS_HOME/scripts/agent_voice.py emit`).

## HARD RULE: Read this file first. Then route below.

## Fast Exit (use first if it matches)

| Situation | Read this and stop here |
|---|---|
| You have a task assignment, or are resuming a session | Run `bash $AGENT_OS_HOME/scripts/agent-os-boot.sh` — it prints your surface, required reads, current state |
| You are working in a workspace | `<workspace_root>/AGENTS.md` |
| Vault knowledge base (on-demand only) | `$VAULT_PATH/AGENTS.md` |

## Otherwise: Boot Routing

1. Run: `bash $AGENT_OS_HOME/scripts/agent-os-boot.sh` (prints your surface, required reads, current state)
2. Read `$AGENT_OS_HOME/docs/BOOT_FACTS.yaml` — this is your ONLY required read
3. Follow the scan_path in BOOT_FACTS.yaml: read `every_agent` files first, then your role-specific files
4. If you need to find a skill/tool/file: `grep -i "<keyword>" $AGENT_OS_HOME/INDEX.md`
5. If writing a spec: use `$AGENT_OS_HOME/docs/SPEC_TEMPLATE.md`, save to `specs/active/`, pass `bin/spec-check`

## Coding Rules (every agent, every session)

1. **Think Before Coding** — No silent assumptions. State what you're assuming. Ask before guessing.
2. **Simplicity First** — Minimum code that solves the problem. No speculative features.
3. **Surgical Changes** — Touch only what you must. Don't improve adjacent code.
4. **Goal-Driven Execution** — Define success criteria. Loop until verified.
5. **Skill-Selection Convention** — Before loading any skill SKILL.md, run `skill-rank "<task>" --top 3 --json` to find the best match.
6. **Verify Before Trusting** — If you read a doc that makes a factual claim, check the live state before acting.

7. **No Credential Exposure** — Never write API keys, tokens, SSH keys, or
   passwords to files, logs, stdout, or any output that could be stored or
   transmitted. Use environment variables or `$AGENT_OS_HOME/config.env` /
   `secrets.env` for all sensitive values.
8. **No Temp Writes** — Never write files to `/tmp` or other world-readable
   directories. Use the workspace directory or
   `$AGENT_OS_HOME/.local/state/` for temporary storage.
9. **Use RTK for Token Efficiency** — When `rtk` is available (`command -v rtk`),
   prefer it over standard commands for file reads, directory listings, grep,
   and git status. Falls back to standard commands automatically.

## Memory System (every agent, every session)

The Agent OS memory system has multiple tiers. All agents should know these basics and contribute lessons.

### Tiers

| Tier | Backend | Purpose |
|---|---|---|
| Short-Term SQLite | Local SQLite | Recent activity, lessons, stumbles |
| Semantic (optional) | Pinecone | Vector search for cross-session recall |
| Graph (optional) | Neo4j | Relationship-based memory queries |

### How agents interact with memory

| Action | Command | Notes |
|---|---|---|
| Write a lesson/stumble | `memory-st write --intent LESSON --summary "..." --source-ref cli:...` | Use LESSON, STUMBLE, DECISION, CONFIRMED intents |
| Search memory | `recall "query"` or `memory-lt search-vector --text "..."` | Semantic + FTS5 + graph search |
| Check health | `bash $AGENT_OS_HOME/scripts/agent-os-health.sh` | All tiers should be GREEN |

### Promotion pipeline

Records with intent LESSON/STUMBLE/DECISION/CONFIRMED flow through:
1. **Auto-promote** to Pinecone (if configured)
2. **Graph-promote** to Neo4j (if configured)
3. **Recall hook** injects memories into agent sessions

### Memory docs

- Full user guide: `$AGENT_OS_HOME/docs/MEMORY_USER_GUIDE.md`

## Non-Negotiables (every agent, every session)

- No `git add`, `commit`, `push`, `checkout`, `reset`, `stash`, `branch` for ACP-dispatched workers and autonomous agents.
- No worktrees, no clones, no duplicate repos.
- Never read: `.ssh/`, `.mssh/`, `*_ed25519`, `*_rsa`, `*.pem`, `.env*`, credential JSON.
- Absolute paths only. Never `~`.
- End every report with `STUMBLES:` and `CONFIRMED:` sections.
- If blocked, stop and report `BLOCKED:` with the reason. Do not improvise.
- Never use `rm`, `rmdir`, `mv-to-delete`, or `shred`. Use write-to-tmp and rename.

## Source of Truth

- Runtime: `$AGENT_OS_HOME/` (your installation)
- Docs: `$AGENT_OS_HOME/docs/`
- Registry: `$AGENT_OS_HOME/registry/`
