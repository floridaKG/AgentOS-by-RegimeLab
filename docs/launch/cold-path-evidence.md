# Cold-path evidence

**Date:** 2026-07-16T16:11Z
**Method:** clean HOME via `env -i` (no cloud API keys injected)

## Commands (matches README after claim-safe pass)

```bash
./install.sh --no-path
source ~/.config/agent-os/config.env
export PATH="$AGENT_OS_HOME/bin:$PATH"
memory-st init
memory-st write ... --content-file ... --summary "Cold path unique lesson $UNIQUE"
memory-recall --text "$UNIQUE" --tier short_term
```

## Captured output
```
=== WRITE ===
{"ok": true, "id": "st_20260716_8DCKNR", "promote_state": "none", "boundary_kind": null}
=== RECALL ===
{"ok": true, "command": "memory-recall", "query": "coldpath-1784218292-2133966", "limit": 5, "workspace": null, "boundary_filter": null, "scope": null, "graph_entities": [], "timestamp": "2026-07-16T16:11:32Z", "fallback_active": false, "tier_results": {"claude_memory": {"status": "skipped", "results": []}, "short_term": {"status": "available", "result_count": 1, "results": [{"id": "st_20260716_8DCKNR", "tier": "short_term", "summary": "Cold path unique lesson coldpath-1784218292-2133966", "source_path": "docs/launch/cold-path", "score": -0.0, "workspace": "demo", "tags": []}]}, "graph": {"status": "skipped", "results": []}, "semantic": {"status": "skipped", "results": []}}, "results": [{"id": "st_20260716_8DCKNR", "tier": "short_term", "summary": "Cold path unique lesson coldpath-1784218292-2133966", "source_path": "docs/launch/cold-path", "score": -0.0, "workspace": "demo", "tags": []}], "result_count": 1}
=== PASS ===
UNIQUE=coldpath-1784218292-2133966
```

**Verdict: PASS** — install, write (`"ok": true`), and `memory-recall` returned the unique lesson with no cloud credentials.
