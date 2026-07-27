# Architecture Decision Validation Prompt

Use this template when you need a higher-reasoning model to validate a proposed architecture change. The structure is:

1. **Describe the current architecture** — data flow, file dependency chain, key line numbers
2. **State the proposed change** — what you want to do specifically
3. **List files to review** — exact paths with what to read in each and why
4. **Ask specific questions** — what to validate, edge cases to catch, execution order

## Template

```
You are reviewing an architecture decision for [project]. The goal: [single sentence].
I need you to validate the approach and identify edge cases I might miss.

## Current Architecture

[Describe the data flow. Use specific file paths and line numbers.
 Include the actual dependency chain — what reads what, what writes what.]

[File A]: lines X-Y does Z
[File B]: does Z, calling [File A] at line N
[File C]: consumes output of [File B]

## The Problem

[What's wrong with the current approach. Specific metrics or behaviors.]

## Proposed Change

[What you want to do. Exact files to modify and the nature of the change.]

## Files to Review (read each)

Read these in order. For each, note what to pay attention to.

### Must-read files:

1. path/to/file.py — full file (N lines). Pay attention to:
   - Line X: the specific line we'd change
   - Key functions and their signatures

2. path/to/other.py — read:
   - Function A at line N — does X
   - Function B at line M — does Y

### Reference files (skim):

3. path/to/config.yaml — config schema this depends on

### Docs:

4. path/to/doc.md — relevant context

## Questions to Answer

1. **Is the approach sound?** Are there hidden assumptions?
2. **[Specific concern 1]:** How to handle X?
3. **[Specific concern 2]:** What about Y?
4. **What's the minimal first commit?** The smallest safe change that proves the pattern.

## Deliverable

A brief analysis:
- Validation of the approach (green/yellow/red with reasoning)
- Edge cases identified and how to handle each
- The sequence of commits that gets from today to the goal
- The single most important thing to get wrong
```

## Example from real session

A prompt sent to a higher-reasoning model for an architecture refactor decision used this exact pattern. The current architecture described a multi-step data pipeline with specific file paths. The proposed change was to have the legacy pipeline write directly to a database instead of going through intermediate serialization. The "questions to answer" section asked about state management during pipeline execution, partial failure states, and the minimal first commit.

Key detail from that session: the reasoning model validated the approach but the user then corrected it to skip the legacy pipeline entirely and go straight to database-native compute. The template works even when the answer is "do something even simpler."
