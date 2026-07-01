# Adversarial Re-Attack Methodology for Doc/Review Audits

After producing a findings set, re-attack your OWN findings with live
read-only probes before reporting them confirmed. This is the distinct
second half of verify-before-trust: the first half guards against trusting
other docs; this half guards against trusting your own unverified inferences.

## Probe categories (all read-only)

- Counts: Pinecone `describe_index_stats` (MCP), Neo4j via health
  endpoints or CLI, SQLite record counts via the `bin/memory-*` wrappers.
- Schedules: read the live scheduler state directly. Do NOT trust crontab
  or systemd claims for memory jobs — they live in the scheduler, and
  docs frequently disagree on the job model (1-job vs 2-job promote).
- CLI claims: `<cmd> --help` to confirm flags/subcommands a doc cites. Two
  flags that look contradictory may both be valid on different scopes
  (e.g. `-q` on a subcommand vs `-z` as a global flag).
- Gate behavior: read the gate script source. A gate can claim to enforce X
  while explicitly excluding the file in question (e.g. `if p.name !=
  'AGENTS.md'`). The source is the only reliable answer.
- Paths/refs: `find`/`ls`/`test`/`cmp` against the live filesystem. A "missing"
  ref may just have graduated from `specs/active/` to `specs/completed/`.
- Byte-identity: `cmp -s` across all canonical/mirror copies.

## Finding-revision table (worked example, 2026-06-18 GLM-5.2 pass)

Re-attack changed 3 of ~20 finding statuses:

| Original | Probe | Revised |
|---|---|---|
| HIGH: "spec ref MISSING in roles.toml" | `find` both repos | DOWNGRADED: spec exists in `completed/`; stale `active/` path, not dangling |
| MEDIUM: "gate blind to AGENTS.md byte-identity" | read governance-check src | STRENGTHENED: gate explicitly excludes AGENTS.md by name (line 109) |
| MEDIUM: "tool -q vs -z, one is wrong" | `<tool> --help` | DOWNGRADED to LOW: both valid flags on different scopes |

Lesson: a findings report that skips re-attack ships at least one
wrong-severity claim. Budget the probes; they are cheap and read-only.

## Subagent self-report caveat

Parallel research subagents return unverified summaries. Re-verify each
material claim (count/path/schedule/status) with your own probes before
folding it into the audit record. A contradicting subagent claim may be a
transient (e.g. an auto-promote job flushing a backlog mid-session so a
Pinecone count reads 3405 then 5536 minutes later), not a subagent error —
but you only know that after re-verification.
