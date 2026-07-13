---
topic: cass-session-archaeology
scope: installation, usage, integration with Agent OS
status: active
spec: $AGENT_OS_HOME/docs/specs/active/2026-06-08-agent-os-cass-and-ntm-integration-exploration.md
last_updated: 2026-06-09
---

# CASS -- Coding Agent Session Search

## What It Is

Rust binary from Dicklesworthstone that indexes and searches local coding agent session history across 11+ providers: Codex, Claude Code, Gemini CLI, Cline, OpenCode, Amp, Cursor, ChatGPT, Aider, Pi-Agent, GitHub Copilot Chat, Copilot CLI, OpenClaw, Clawdbot, Vibe, Crush, Hermes, Kimi Code, Qwen Code, and others.

**Key differentiator:** Cross-agent. Per-agent session_search tools only query their own state. CASS indexes ALL agent session formats into a single searchable timeline.

## Installation

```bash
curl -fsSL "https://raw.githubusercontent.com/Dicklesworthstone/coding_agent_session_search/main/install.sh" \
  | bash -s -- --easy-mode --verify
```

Pre-built binary for linux-amd64 (17MB). No daemon, no services. Binary lands at `~/.local/bin/cass` or `~/.cargo/bin/cass`.

Also available via: `brew install dicklesworthstone/tap/cass` (macOS/Linux).

## Robot Mode (for agents)

NEVER run bare `cass` in agent context -- it launches the TUI. Always use `--robot` or `--json`:

```bash
# Health + index
cass health --json || cass index --full

# Canonical Agent OS query: recent window, minimal payload, fresh index
cass search "auth error" --robot --fields minimal --days 30 --refresh --limit 5

# Inspect a hit
cass view /path/to/session.l -n 42 --json
cass expand /path/to/session.l -n 42 -C 3 --json
```

Key flags:
- `--robot` / `--json`: machine-readable output (stdout only)
- `--fields minimal`: lowest-token payload
- `--limit N`: cap results
- `--agent NAME`: filter (claude, codex, cursor, gemini, aider, etc.)
- `--days 30`: **default Agent OS window.** cass has no 30-day *index* retention —
  the full corpus stays indexed — so scope to recent at QUERY time. Use `--days N`
  or `--since -30d` to widen/narrow.
- `--refresh`: run an incremental index pass before searching so sessions created
  since the last cron run are matched (no-op when already fresh). Cheap; bounded
  by the memory cap below.

## Freshness & Memory (Agent OS integration)

- **Memory cap (REQUIRED):** `~/.local/bin/cass` is a wrapper that runs the real
  binary (`cass.real`) inside a `systemd-run --user --scope` with
  `MemoryHigh=5G / MemoryMax=6G`. `cass index` peaks ~5GB on this corpus and
  previously triggered the *global* OOM-killer, silently destroying tmux tiles.
  The cap contains any runaway to cass alone. A cass reinstall can clobber the
  wrapper — if `cass --version` ever runs uncapped, re-create `cass.real` + wrapper.
- **Freshness — on-demand, not cron:** every `cass index` pass costs ~4GB RAM and
  ~13s even when nothing changed (it rescans the whole corpus to find deltas), and
  on an active box the index goes "stale" within minutes anyway. So the
  The `cass-index-freshness` background job is **disabled** — agents get freshness by
  adding `--refresh` to the query, which pays that cost only when a search actually
  runs. Re-enable the nightly job only if you query cass often enough that the
  first-query catch-up latency becomes annoying.

## Integration Plan (post memory-layer-upgrade)

1. Install binary
2. Create wrapper at `$AGENT_OS_HOME/bin/session-archaeology` with guarded defaults
3. Add Agent OS doc distinguishing `session_search` vs `cass`
4. Smoke test: binary exists, help works, JSON mode callable

## When to Use Which

| Surface | Use when |
|---|---|
| `session_search` | Quick per-agent conversation lookup, lightweight in-agent history |
| `recall.sh` | Knowledge tier search (Pinecone, cockpit, vault) |
| `cass` | Cross-agent archaeology, structured packs, multi-provider history search |
