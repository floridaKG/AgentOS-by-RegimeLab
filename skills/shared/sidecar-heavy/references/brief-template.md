# Sidecar-Heavy Brief Template

Use this structure when dispatching a heavy reasoning model (via CLI or Codex MCP). Fill in the bracketed sections. Delete any section that doesn't apply.

```markdown
You are a pure-reasoning advisor. You have NO access to tools or the filesystem — you can only think and respond. The [user role, e.g. "project owner"] and a cheap agent (me) will implement based on your guidance.

## Context

[3-5 paragraphs giving the driver's perspective. Cover:
- What system or project this is about
- Current state (what's working, what's broken)
- What has already been tried or decided
- Who the stakeholders are and what they care about]

## Key constraints

- [Architecture rule 1, e.g. "DuckDB is cold store only"]
- [Business constraint 1, e.g. "SPX needs scheduled RTH pulls"]
- [Technical limitation 1, e.g. "All schedulers run in-process"]

## What we need from you

### [Topic A: e.g. "Kalshi pipeline assessment"]

[Specific questions to answer:
- What's the root cause of X?
- What's the smallest fix?
- What's the largest risk?]

### [Topic B: e.g. "Priority ordering"]

[If you need a ranked list, specify the criteria:
- Impact on users
- Resource waste
- Ease of fix]

## Format for your response

Structure your reply exactly as:

1. **Executive summary** (3-4 sentences — what should we do first and why)
2. **Priority ranking** (1-N, with rationale per item)
3. **Per-topic deep dives** (one section per topic with assessment + action plan)
4. **Open questions** (anything we need to verify in the live system before acting)

Be specific about file paths and function names where possible. Recommend the smallest effective change for each problem.
```

## Writing tips

- **Tell it what you already know.** The first sentence after "Key constraints" should be "You don't need to rediscover X — here's what we've already verified." This saves 30-50% of the heavy's tokens.
- **Number your questions.** Makes it trivial for the heavy to address each one and for you to verify nothing was missed.
- **Give format instructions last.** The heavy pays more attention to the end of the prompt (recently bias).
- **Lead with context, follow with ask.** Don't bury the questions after 10 paragraphs of setup — structure: context → constraints → numbered questions → format.
