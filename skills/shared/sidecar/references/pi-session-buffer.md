# pi Session Buffer — Memory Ceiling

## What the buffer is

Every pi sidecar session holds its full transcript in memory: the sidecar's
chain-of-thought, every tool invocation, every file it read, every command
output, all the way back to when the session started. That running transcript
IS the buffer. pi caps it at a fixed size (e.g. 10 MB).

## What the abort looks like

`Message buffer exceeded <bytes>`, often followed by
`sidecar: prompt failed (exit 1) and did not look rate-limited`.

The abort is post-completion, not mid-task data loss: the sidecar can finish
its work and emit its report BEFORE the buffer overflows. The overflow kills
the session for FURTHER turns, not the answer already produced. Always verify
the sidecar's claimed output against live state.

## Mitigation

- One substantial task per session; use a fresh session name for the next.
- `sidecar history [name]` before a big task — if it shows unrelated prior
  turns, start a new name.
- If a session is getting large, finish and checkpoint its result, then move
  on under a new name rather than piling more work on the same buffer.
