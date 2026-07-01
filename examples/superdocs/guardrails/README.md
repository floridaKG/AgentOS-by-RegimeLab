# Guardrails

Purpose: operational guardrails and conventions for your project.

Guardrails protect live contracts that must not change without explicit
unlock procedures. Each guardrail names the locked surface, states the rule,
and documents the enforcement mechanism.

## How to Add a Guardrail

1. Name the locked surfaces (file paths, symbols, APIs).
2. State the rule in one sentence.
3. Cite the incident or concern that motivated it.
4. Point to the enforcing test, or mark `enforcement: docs-only`.
5. Document the unlock procedure.

## Files

| File | Protects |
|---|---|
| `conventions.md` | Coding conventions and standards |
