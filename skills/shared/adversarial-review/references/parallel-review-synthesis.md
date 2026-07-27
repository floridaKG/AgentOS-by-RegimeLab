# Parallel Review + Synthesis Pattern

When a spec needs comprehensive review, dispatch 3 agents in parallel and synthesize:

1. **Respec agent** — reads the spec, verifies claims against live codebase, rewrites as execution-ready
2. **Adversarial agent** — finds every flaw: wrong assumptions, missing dependencies, scope creep
3. **Improvement agent** — suggests cuts, simplifications, and additions

Then synthesize into a final spec that addresses all findings.

## Dispatch

```python
delegate_task(tasks=[
    {"goal": "Review and respec [spec path] against [context]. Write to [output path].", "toolsets": ["terminal", "file", "search"]},
    {"goal": "Adversarial review of [spec path]. Find every flaw. Write to [output path].", "toolsets": ["terminal", "file", "search"]},
    {"goal": "Read [spec path] and suggest improvements. Write to [output path].", "toolsets": ["terminal", "file", "search"]}
])
```

## Synthesis

Read all 3 outputs. The respec gives you the rewrite. The adversarial gives you what to fix. The improvements give you what to simplify. Apply adversarial fixes to the respec, incorporate simplifications, and write the final version.

## When to use

- Spec is large (200+ lines) and needs comprehensive review
- Multiple perspectives would catch different issues

## When NOT to use

- Small spec (<100 lines) — single adversarial review is enough
- Time-sensitive — parallel dispatch takes ~3 minutes total
