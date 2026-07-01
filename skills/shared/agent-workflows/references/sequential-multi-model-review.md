# Sequential Multi-Model Review

A workflow pattern where a document is reviewed by multiple models in sequence, each seeing the previous model's output, then the orchestrator synthesizes all reviews.

## When to use

- Architecture decisions that benefit from multiple perspectives
- Complex design questions where one model's blind spots are another's strengths
- When you want to stress-test an idea before building

## How it works

```
Write handoff doc
    |
    v
Dispatch to Model A (e.g., Claude Opus via hard_escalation)
    |  (waits for response)
    v
Package: original + Model A review
    |
    v
Dispatch to Model B (e.g., GPT-5.5 via escalation)
    |  (waits for response)
    v
Synthesize: consensus, divergences, new insights
    |
    v
Present to user with both reports saved
```

## Example from real session (2026-06-13)

Dispatched architecture brainstorm for Innovation Channel + MOE to:
1. Claude Opus (hard_escalation role) - got detailed architecture critique
2. GPT-5.5 (escalation role) - got deeper operational analysis, found existing `agent-workflow learn` substrate

Both agreed on core direction (derive don't poll, build only missing MOE tier). GPT-5.5 caught things Claude missed (role routing drift, kill criteria, prompt injection risk).

## ACP roles used

| Model | Role | Provider |
|-------|------|----------|
| Claude Opus | `hard_escalation` | claude/opus |
| GPT-5.5 | `escalation` | codex/gpt-5.5 |

## Prompt structure

For Model A, send the full handoff with specific review questions:
```
Read the full document, then provide:
1. Architecture critique (what is right, what is wrong)
2. Missing considerations
3. Your recommended approach
4. Specific implementation suggestions
```

For Model B, package both the original AND Model A's review:
```
You are reviewing an architecture brainstorm + a prior agent review. Synthesize both, provide your own analysis.

=== ORIGINAL BRAINSTORM ===
[full text]

=== PRIOR REVIEW ===
[full text]

=== YOUR TASK ===
1. Do you agree with the prior critique? What did it get right/wrong?
2. What did BOTH agents miss?
3. Your recommended architecture
4. Specific implementation priorities
5. Any concerns
```

## Pitfalls

- **Sequential adds latency.** Each model takes 30-180s. Total: 1-6 minutes. Only worth it for high-stakes decisions.
- **Second model may anchor on first model's framing.** Mitigate by asking "what did both miss?" explicitly.
- **Cost.** Claude Opus + GPT-5.5 = expensive. Reserve for architecture decisions, not routine questions.
- **ACP timeout.** Set `--wait` without `--timeout` (flag not supported). Default timeout is ~6 minutes.
