---
id: recall
name: recall
trigger:
  - /recall
  - /recall <query>
  - what do we know about X
  - find lessons on X
scope: cockpit
status: stable
description: Search across all memory tiers (cockpit, workspace, vault, Pinecone) for past lessons, decisions, and findings. Use when you need to know what was learned about a topic before. Triggers on "/recall", "/recall <query>", "what do we know about X", "find lessons on X".
version: "1.0"
user-invocable: true
allowed-tools: Read, Bash, Grep, Glob
last_reviewed: 2026-06-15
---

## Purpose

Single search interface across all memory tiers. The shared contract is the
CLI floor: any agent with shell access can run `$AGENT_OS_HOME/scripts/recall.sh`
to ask "what do we already know about X" before doing new work.

The memory tiers (see `memory/README.md` for full architecture):
1. User memory — `$AGENT_OS_HOME/state/memory/` (user-state path, documented in SETUP.md)
2. Cockpit — `$AGENT_OS_HOME/memory.md` + `lessons.md`
3. Workspace — `<workspace>/docs/MEMORY.md` + `LESSONS.md`, `<vault>/self/memory.md`
4. Vault — `findings/`, `insights/`, `Topics/`
5. Vector — Pinecone (semantic search via `memory-lt`)
6. Graph — Neo4j (entity relationships)
7. Short-term — SQLite via `memory-st`
8. Sessions — CASS cross-agent session search (raw session history from Claude Code, Codex, OpenCode, etc.)

---

## Execute

### `/recall <query>`

Default: grep all tiers, return top hits with file path + line number.

```bash
$AGENT_OS_HOME/scripts/recall.sh "<query>"
```

### `/recall --tier=<name> <query>`

Restrict to one tier: `cockpit`, `user`, `workspace-<name>`, `vault`, `sessions`.

```bash
$AGENT_OS_HOME/scripts/recall.sh --tier=<name> "<query>"
```

Use `--tier=sessions` to search only raw session history via CASS. Other tier values search only file-based memory.

### `/recall --semantic <query>`

Use Pinecone vector search (requires `PINECONE_API_KEY` configured).

```bash
$AGENT_OS_HOME/scripts/recall.sh --semantic "<query>"
```

Falls back to grep with a warning if Pinecone is not configured or semantic search fails at runtime.

### `/recall --explain <query>`

Like default, but each result includes metadata: tier, method, score, freshness, and reliability.

```bash
$AGENT_OS_HOME/scripts/recall.sh --explain "<query>"
```

Output format:
```
[TIER:cockpit] [METHOD:fts5] [SCORE:1.0] [FRESHNESS:2026-06-05] [RELIABILITY:high] line 42: <text>
```

Use `--explain` when building context for a handoff or when you need to assess result quality.

### Context Pack (for handoffs)

For bounded context bundles suitable for reasoning model handoffs, use the `context-pack` command (see `skill-optimizer` skill):

```bash
$AGENT_OS_HOME/scripts/context-pack.sh "<query>" --budget=8000
```

---

## Output Format

```
[cockpit/lessons] line 42: <matching line>
[project-a/LESSONS]  line 17: <matching line>
[vault/insights]  insights/2026-04-22-vrp-insight.md:12: <matching line>
```

Top 20 hits by default. Pipe through `head -N` for fewer.

---

## When to Use

- **Before starting a new task** that touches a topic — check what was learned
  before.
- **When user asks "do we have anything on X?"** — direct retrieval.
- **When debugging an unexpected behavior** — grep lessons for prior incidents.
- **When deciding on an approach** — check if there's a memory entry recording
  a prior decision and its rationale.

---

## Locating Distributed Work Products

When the user asks "find everything about X" or "where did we leave Y", run a parallel multi-source search. Memory tiers alone are not enough -- work products (specs, inventory docs, umbrella docs) live on the filesystem and in session logs, not just in memory.

**Parallel search pattern (fire all at once):**

| Source | Tool | What it finds |
|---|---|---|
| Shared memory/content | `$AGENT_OS_HOME/scripts/recall.sh --explain "X"` | Cockpit/workspace/vault hits with freshness and reliability metadata |
| Filesystem names | `find` or `rg --files` under the relevant root | Files with matching names |
| Semantic content | `$AGENT_OS_HOME/scripts/recall.sh --semantic "X"` | Pinecone-backed semantic matches when configured and reachable |
| Known locations | Direct shell reads under known roots | Specs in `$AGENT_OS_HOME/docs/specs/active/`, vault docs, cockpit files |

**Search surface ownership:** `$AGENT_OS_HOME/scripts/recall.sh` is the shared Agent OS interface. CASS is an active recall backend that searches raw session history (Claude Code, Codex, OpenCode, etc.) and is included in all-tiers searches by default. Use `--tier=sessions` to query CASS only. CASS is fail-open: if unavailable or returning no results, recall continues with other tiers uninterrupted.

**Why parallel:** These sources are independent. Filesystem search finds real artifacts. `recall.sh` finds remembered content across cockpit/workspace/vault tiers. Pinecone can add content-level matches that filename search misses when it is available. Known locations catch files that don't match the search term but are structurally relevant (for example, `AGENT_OS.md` for an Agent OS query).

**Pitfall:** Pinecone namespace results can reference paths that no longer exist on disk (archived/moved/renamed). Always verify with a filesystem check before reporting a file as "found." If Pinecone hits a stale path, note it as a reference but don't treat it as an active artifact.

**Pitfall: Fuzzy recall of past evaluations.** Users often remember a tech evaluation happened but misremember the name, language, or domain. ("Wasn't there a rust thing?" when they mean TurboQuant, which is a quantization algorithm with llama.cpp forks in C/C++.) When the user's query yields no direct hits:
1. **Broaden the search surface immediately** — try session_search with multiple angles: the topic domain (e.g., "reranking", "quantization"), related concepts (e.g., "rust", "llama.cpp"), and partial terms from the user's memory.
2. **Search session history first** for tech evaluations — they live in session transcripts, not always in SHELF.md or research artifacts. Use `session_search(query="<topic> tech evaluation")` and `session_search(query="<tool name>")` in parallel.
3. **Check SHELF.md and research/ directory** for shelved evaluations — these are the canonical storage for past tech evals.
4. **Confirm with the user before shelving** — once you find the right session, summarize what was evaluated and the verdict, then ask if they want to shelve it. Don't assume.

**Output:** Group results by source, note which are stale/missing, and give the user a clear map of what exists and where.

---

## References

- CASS is an active backend: `--tier=sessions` queries raw session history, default all-tiers includes sessions automatically

## When NOT to Use

- For domain research (use vault `learn` or `deep-dive` skills).
- For reading the current code state (use `rtk read` / `rtk grep` — RTK is an
  optional external tool; falls back to standard commands if not installed).
- For task tracking (use TaskCreate / TaskList).
