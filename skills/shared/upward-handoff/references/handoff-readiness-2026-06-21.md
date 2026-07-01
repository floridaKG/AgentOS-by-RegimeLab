# Handoff Readiness — Not Just Document Creation

## The Lesson

A handoff document is not ready just because it exists. Writing a parts list of broken components is not the same as asking the architectural questions that would let a higher model design the solution.

## What Happened (2026-06-21)

First version of the Agent OS hardening handoff was a status report: "here's what's broken, here's what's missing, here are 5 decisions." The user rejected it:

> "The handoff is not ready. Just because you created it does not mean it is ready. We need to ask the right questions."

The document listed parts (NTM enforcement is off, skills aren't automated, stumble pipeline isn't wired) but didn't ask the architectural questions that would let a higher model reason about the design:
- What is the stumble-to-harness pipeline architecture?
- What is the enforcement architecture?
- What does "finished" look like?
- What is the cross-agent contract?

## The Pattern

**Level 1 (status report):** "X is broken, Y is missing, Z needs fixing." — This is a parts list. It tells the reviewer WHAT but not WHY or HOW.

**Level 2 (architectural questions):** "Here are the systems, here are the gaps, here are the questions nobody is asking." — This gives the reviewer TERRAIN to reason from.

**Level 3 (design brief):** "Here's the architecture, here's the implementation plan." — This is a spec, not a handoff. Only appropriate when explicitly asked.

The upward handoff should be Level 2. The user wants the higher model to do the reasoning. Your job is to surface the terrain and the questions, not the answers.

## The Checklist

Before submitting any handoff, ask:
- [ ] Am I listing broken parts, or asking architectural questions?
- [ ] Would a higher model feel free to disagree with my framing?
- [ ] Are my "open questions" genuine questions, or leading prompts?
- [ ] Did I prescribe solutions? (if yes, move them to open questions as questions)
- [ ] Is the document ready for review, or just created?
