# Handoff Authoring Standard

> How to write a handoff document for upward review by a
> higher-reasoning model.

## When to Write a Handoff

Write a handoff when you have completed a batch of work and need a
higher-reasoning reviewer to:

- Validate the correctness of your changes
- Catch edge cases or assumptions you missed
- Surface hidden tensions between competing constraints
- Decide on deferred choices that require broader judgment

Do NOT write a handoff for simple, single-file changes that fit in
a normal report.

## Structure

Every handoff document must follow this structure:

### Context

What was the task? What were you asked to do? Include the original
prompt or a concise summary. State which files you started with
and which workspace you operated in.

### Raw Findings

Bulleted facts. What did you observe? What did you change? What
did you try that didn't work? No interpretation — just what
happened and what the system showed you.

Example style:
- File X had Y pattern; changed to Z because...
- Tool A returned error B; workaround was C
- Variable D was undefined; traced to missing config E

### Tensions

Where do constraints pull in opposite directions? Examples:

- Speed vs. correctness in a script that has no error handling
- Portability vs. dependency on a specific tool version
- Simplicity vs. handling all edge cases

List each tension as a separate bullet. State both sides neutrally.

### Open Questions

What could not be resolved during this work? For each question,
provide:
- The question itself
- Why it matters
- Any options you considered but couldn't decide between

### Boundary Notes

What is outside the scope of this handoff? What did you explicitly
not investigate? This prevents the reviewer from wasting time on
intentional gaps.

## Voice and Tone

- **Neutral language.** No prescriptions. No "we should." No "clearly."
- **Surface terrain, don't decide.** Your job is to map what you found.
  The reviewer's job is to decide what to do about it.
- **Be precise.** Prefer specific file paths, line numbers, error
  messages, and command output over generalizations.
- **Separate fact from interpretation.** If you are drawing a conclusion,
  label it as interpretation or speculation.
