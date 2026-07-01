# Effective Sidecar Briefs

## The core rule: one session, one tight objective

The sidecar is NOT a general-purpose research assistant. It is an execution
partner. If you give it a broad research mandate, it will explore broadly
and shallowly. If you give it a specific execution task, it will execute.

## Brief template (narrow, good)

```
What I already know (don't re-derive):
- [context point 1]
- [context point 2]

Read [specific file path] and answer:
1. What does function X call?
2. What's the return shape of function Y?
3. Does function Z write to table T?

Run [specific command] and report:
- [specific output to capture]

Do NOT:
- Read other files unless the trace forces it
- Comment on architecture or design quality
- Propose fixes — just report what's there
```

## Brief template (broad, know what you're getting)

Use this only when you genuinely want the sidecar to survey unknown
territory. Accept that the result will be a map, not a deep dive.

```
What I already know:
- [boundary of what's known]

Explore [directory or area] and report:
1. What files exist and what each does (one line each)
2. Any signs of stale/broken code
3. Any quick wins you spot

Narrow to [specific sub-area] for details. Flag anything interesting
outside scope as a single note at the end.
```

## Recipe for a good sidecar prompt

| Element | Do | Don't |
|---------|----|-------|
| **Context** | "I've already verified X, Y, Z." | Omit what you know, making it re-derive |
| **Scope** | "Read this one file." | "Investigate this area" (5+ files) |
| **Questions** | "What does function X return?" | "Tell me everything about this pipeline" |
| **Boundaries** | "Do NOT explore beyond file X." | Unbounded exploration |
| **Output format** | "Three bullet points + specific values" | "Report your findings" (narrative) |
