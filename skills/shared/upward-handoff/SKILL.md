---
name: upward-handoff
description: Prepare findings for a higher-reasoning model to review. Use when you've investigated/explored/audited something and need to hand the material up for its own analysis — not to review your conclusions, but to reason from raw findings.
last_reviewed: 2026-06-17
---

# Upward Handoff Skill

## When to use this

You've dug into something — read files, compared surfaces, traced a bug, audited a system. You have findings. Now you need a higher-reasoning model (Opus or equivalent) to apply its judgment.

**Use this skill when:** your output is going to a higher model for its own reasoning, not just task completion.

**Do NOT use this when:** you're writing a standard task-completion report (use `AGENT_REPORT_CONVENTIONS.md` instead) or when the task is self-contained and doesn't need upstream review.

### Self-discipline use (do this even when not handing off)

The handoff format is also a thinking tool for the agent itself. Use it as a discipline check **before** you commit to a prescription, especially when:

- The user has signaled distrust in your design reasoning ("I'm not sure I trust you for the rest of it", "you jumped to a conclusion", "why would we do that?"). Defensive specs double down on the wrong answer. Switch to findings-as-terrain and let the higher model (or a re-review) catch what you missed.
- You are about to write a spec or design doc and find yourself reaching for a "natural" fix (re-index, re-build, re-generate, migrate, refactor). The "re-" prefix is a smell. Before writing the WP, write the F (raw findings) and the T (tensions). If the F doesn't justify the re-, the WP is wrong.
- The work spans multiple subsystems and you are not sure your model of the data state is current. The pre-flight verification table forces literal evidence; if you can't fill a row, you don't know enough to prescribe.

**Heuristic:** if you would be embarrassed to send the handoff to Opus, the spec isn't ready. Rewrite the spec in handoff format first. If the handoff doesn't justify the spec, the spec is wrong.

---

## When you are the reviewer (receiving a handoff)

The sections above are for producing a handoff. When you are handed a
neutral-findings doc (from a peer agent or an upward handoff) and asked to
review it, your job is the inverse: verify the findings against live state
before acting on them. A well-written neutral handoff is still a set of claims
made from one vantage point; several will be wrong.

### The boundary notes are the roadmap

A handoff's "What I didn't examine" / "Boundary notes" section lists exactly
where it did not verify. Those are the highest-yield places for you to check:
the unverified claims are where false alarms hide. Read the boundary notes
first and plan verification around them.

### What handoffs get wrong (observed patterns)

- **Under-sampling.** Line numbers and function maps are partial. A claim
  "diversity check removed at line 176/276" may hold for two runners but be
  false for two others the handoff didn't sample. Re-derive structure from the
  actual code; don't trust the handoff's line numbers.
- **Missing untracked / uncommitted work.** A handoff that says "no replacement
  spec exists" may simply not have checked `git status` for untracked files.
  Always run `git status` and look at untracked specs / scripts before
  accepting a "doesn't exist" / "may be lost" claim.
- **System-state assertions are the most error-prone.** "Cron is RED (0/32),"
  "no scheduled execution," "fully inactive" — strong claims made without live
  verification. Check the live scheduler (`cronjob list`), the live API, the
  live Pinecone. Verify, then label the handoff's claim true or false.
- **Conflating designed alert behavior with breakage.** A watchdog that exits
  nonzero to surface a condition (stale recall, marker mismatch) is working as
  intended, not broken. A cron "error" on such a watchdog is the alert firing,
  not a defect.

### Report verdicts by category

When you synthesize, label each of the handoff's tensions / findings as one of:
**dissolved** (false on live verification), **held** (real), or
**under-sampled** (partially true, missing nuance). A handoff that flags 7
tensions may have 4 dissolve, 2 hold, 1 under-sample. Lead with that scorecard
so the caller knows which findings to act on and which to drop.

---

## Task Delegation Handoff (Lateral/Downward)

Use this pattern when you are **assigning a concrete task to another agent** (Kimi, Claude Code, Codex, etc.) — not surfacing findings for review. This is the mirror image of the upward handoff: instead of "surface terrain, don't prescribe," you DO prescribe: goal, context, files, constraints, deliverables.

### When to use task delegation vs upward handoff

| Situation | Pattern | Example |
|---|---|---|
| You have findings and want a higher-reasoning model to analyze them | Upward handoff (surface terrain) | "Here's what I found in the data pipeline — what's going wrong?" |
| You have a concrete task and need another agent to execute it | Task delegation | "Build a gold Mandelbrot SVG logo, place it in these files, create a preview page" |
| You need the other agent to both investigate AND produce something | Split: delegate the task, include context as findings | "Investigate X, then build Y. Here's what I already know about X." |

### Structure of a task delegation handoff

```
# Handoff: [Task Title]

**To:** [Agent name/role]
**From:** [Your name]
**Status:** [Design + prototype, no main app changes yet — or Ready for integration]

---

## The Goal

A single clear sentence. Then a paragraph with the key requirement.

---

## Design / Context Reference

Point to existing code or assets the agent needs to study:
- File paths with what to look for
- Key lines or functions
- Existing patterns to follow or replace

---

## File Inventory

| File | Role | What to do |
|---|---|---|
| path/to/file.tsx | Role description | Replace/update/create |
| path/to/another.tsx | Role description | Update import, etc. |

Every file the agent will touch or reference.

---

## Execution Plan

### Phase 1: [Design / Prototype]
What to build, what format, where to put it.
- Specific deliverables
- Constraints (format, size, color palette)
- "Do NOT modify the app yet"

### Phase 2: [Test / Preview]
How to validate before integration.
- Preview page or test command
- What to check (sizes, backgrounds, etc.)
- Only proceed after approval

### Phase 3: [Integration]
Once approved, swap into the real codebase.
- Files to replace
- Files to delete (old versions)
- Verify the build still compiles

---

## Key Constraints

- Format preferences (SVG > PNG, etc.)
- Color / style requirements
- Size / performance limits
- What NOT to do (e.g., "No canvas, use SVG")
- What NOT to touch (e.g., "No code changes to the React app")

---

## Deliverables

1. First deliverable — description + path
2. Second deliverable — description + path
3. Verification — how to confirm it's done

---

## Contrast with upward handoff

| Upward (findings) | Delegation (task) |
|---|---|
| Surface terrain, don't decide | Here's what to build |
| Raw findings, tensions, open questions | Goal, context, constraints, deliverables |
| No prescriptions | Explicit prescriptions |
| Let the higher model reason | Guide the executor step by step |
| "What I examined, what I found" | "Files to touch, how to touch them" |

### Pitfall: Prescribing to a peer agent vs delegating to a subordinate

When briefing a peer agent (not upward to a higher model, but laterally to an agent in the same system), you do NOT prescribe — see P7 below. The difference:

- **Peer briefings (P7 pattern):** Present facts, verification commands, and open questions. The peer decides what matters based on their own context. You don't know what they've deprecated or redesigned.
- **Task delegation (this section):** You ARE the delegator and the agent is executing a concrete, bounded task you've defined. You DO prescribe the approach, the files, and the deliverables.

**How to decide:** If the agent has more context about the system than you do (e.g., they own the subsystem), use P7 peer-briefing. If the task is new work in a codebase you've just been exploring, use task delegation. If you're unsure, use P7 — you can always tighten to delegation once the peer says "I see what you want, I can execute that."

---

## Pre-Brief Incubation Phase (Collaborative Brainstorming)

**Use this when the vision isn't fully shaped yet.** The standard upward-handoff assumes you've done the investigation and have findings. But sometimes you and the user need to **brainstorm together first** — map what's documented vs what's not, shape the vision, identify open questions. Only then do you structure the brief for the high-reasoning model.

### Signals you need incubation, not immediate handoff

- The user says "we just need to chat and gather context", "get clarity", "let's hash this out"
- The vision for a feature is clearly bigger than what the existing spec describes (e.g., spec says "ask→compose" but user wants a full MCP server for external agents)
- The user wants to compare "what we have documented now" with "what ideas we still need to hash out"
- There are known gaps (GLM review, open questions) that need the user's taste calls before sending to a model

### The three-layer structure for complex handoffs

When a project spans documented decisions, spec-quality gaps, and unshaped ideas, organize the brief as three layers:

**Layer 1 — LOCKED (don't touch):**
Architecture decisions that are ratified, verified, and not up for debate. The higher model should build on these, not question them. Example: "ECharts is the chart library (final). DuckDB is cold store only. Migration is additive /lab with parity-gated cutover."

**Layer 2 — SPEC'D BUT NEEDS FIXES (apply corrections + owner taste calls):**
Existing specs that are structurally sound but have known gaps from reviews. These need targeted fixes before they're build-ready. Note what the fix is and whether an owner decision is needed. Example: "GLM review found the fetch-cache split is wrong — React Query should own all server state. Patches proposed in separate doc, awaiting owner sign-off on font choice."

**Layer 3 — NEEDS DESIGN (brainstorm with the high-reasoning model):**
The genuinely open territory. Questions, tensions, and visions that haven't been spec'd. These are what you want the high-reasoning model to help shape. Example: "MCP server contract — what tools does it expose? Auth model for agent access vs human users? Build order implications for the workspace UI."

### Incubation process

1. **Assess the landscape** — what exists (docs, specs, reviews, live state) vs what doesn't
2. **Map into layers** — locked, needs fixes, needs design
3. **Brainstorm the open territory with the user** — ask what they envision, flag tensions, identify taste calls
4. **Structure the brief** — each layer gets its own section; Layer 3 gets the most space because that's where the model adds value
5. **Present before dispatching** — show the user the brief and wait for "send it" or "dispatch"

**Do NOT skip step 3.** If you go straight from assessment → brief without collaborating with the user on the open territory, the brief will reflect your assumptions about their vision, not their actual vision. The incubation phase is where that alignment happens.

### P20. Asking architectural questions instead of vision questions during incubation

During the incubation phase, the goal is to understand what the user WANTS, not how to BUILD it. When you ask the user "MCP-first or workspace-first?" or "server-side or client-side?" you are asking them to make architectural decisions that should be in the brief for the higher-reasoning model.

**What the user said:** "You're asking me questions that Codex needs to decide" / "stop this back and forth shit"

**Right questions for the user (vision/constraints):**
- "What should an agent be able to do with Project A?"
- "Do you want external/customer agents to query it, or just your own?"
- "What do you like about the current design?"

**Wrong questions for the user (architecture):**
- "MCP-first or workspace-first build order?"
- "Should the block engine be client-side or server-side?"
- "What's the right auth model for agent access?"

**Fix:** Before each question you're about to ask the user, pause and ask: "Could a higher-reasoning model answer this?" If yes, frame it as context in the brief and let the architect decide. If no (it's a taste call, a vision question, or a constraint only the user knows), ask the user.

**Smell test:** If your incubation session consists of asking the user yes/no questions about implementation approaches, you are doing the architect's job. Switch to: ask what outcome they want, document constraints and taste calls, compile into Layer 1-2-3, dispatch to architect.

### Pitfall: Defaulting to the narrow framing

Existing specs often frame a feature in a limited way (e.g., "AI = ask→compose on the canvas"). The user's real vision may be much larger (e.g., "MCP server external agents can query"). Before writing the brief, check: **does the spec's framing match what the user actually wants?** If not, the brief needs to explicitly flag the gap and include the broader vision in Layer 3.

**Real case:** A post-beta umbrella spec says "serialize BlockRegistry at /catalog; ask→compose flow." The user's actual vision: an MCP server that any agent (Claude, Codex, Pi, OpenCode, customer agents) can connect to, discover available data, ask analytical questions in natural language, and get charts back. That's a headless API product, not a UI productivity feature. The spec's framing was too narrow for 6 weeks. The brief flagged this in Layer 3 so a higher-reasoning model could design the right architecture instead of inheriting the narrow frame.

## Core Principle

**Surface the terrain. Do not decide where to build.**

Your job is to present what you found — neutrally, completely, without spin. The higher model's job is to reason about it. If you embed your conclusions in the findings, you waste the higher model's ability to see patterns you missed.

Exception: the **Pre-Brief Incubation Phase** above. During incubation you *do* brainstorm, shape, and flag tensions with the user. But the output of incubation is still a terrain map (layers 1-3), not a prescription. The line is: shape the questions together, then hand the structured territory to the model to answer them.

---

## What goes in

### 1. Context — what was asked and what was examined

Brief, factual. Tell the reader what question you were trying to answer and what you actually examined.

```
## What I examined
Files read:
- /path/to/file (N lines)
- /path/to/file (N lines)

Commands run:
- `git diff --stat` on the target repository
- rtk find on agent-os/registry/ (RTK is an optional external tool — falls back
  to standard `find`/`grep` if not installed)

Scope note: I did not read vault OS docs because [reason].
```

### 2. Raw findings — facts, comparisons, direct observations

This is the heart of the document. Rules:

- Use neutral language. No "better/worse/clearly/should/needs to."
- When comparing two things, present the comparison as parallel facts, not as one winning.
- Include direct quotes or data when relevant.
- If something is surprising or ambiguous, say so explicitly rather than smoothing it over.

**Good:**
```
Surface A contains BOOT.md and NOW.md with no equivalents in Surface B.
Surface B contains the execution brief and master plan with no equivalents in Surface A.
Both surfaces contain AGENT_OS.md but with different structures:
  - Surface A version: 381 lines, no fast exit table, points to agent-os/INDEX.md
  - Surface B version: 357 lines, has fast exit table at line 1, points to HOME_LAYER_INDEX.md
```

**Bad (conclusions dressed as findings):**
```
Surface A is the operational layer while Surface B is the reference layer.
The Surface B version of AGENT_OS.md is better because it has the fast exit table.
```

### 3. Tensions — where the data pulls in different directions

Explicitly call out where the findings don't cleanly resolve. This is often the most valuable part for the higher model.

```
## Tensions I couldn't resolve
- The intent router (BOOT.md) lives in the runtime layer but rarely changes — it could go either way
- Two boot protocols exist but one might be unnecessary; I couldn't determine which without usage data
- P0 is the gate for all downstream work, but P5 is marked IN_PROGRESS — possible sequencing error or intentional docs-only exception
```

### 4. Open questions — what would benefit from the higher model's reasoning

Frame these as genuine questions, not as leading prompts.

**Good:**
```
Q: Would a single SOURCE_OF_TRUTH.md at the docs layer eliminate ambiguity,
or would it just add another doc that agents need to read?
```

**Bad (leading):**
```
Q: Don't you agree that a SOURCE_OF_TRUTH.md would solve everything?
```

### 5. Boundary notes — what wasn't examined

Be explicit about scope limits. This prevents the higher model from over-relying on incomplete data.

```
## What I didn't examine
- Vault workspace boot docs (not relevant to the layer question)
- The actual git diff output from the target repository (P0 task, not assigned)
- Whether the workflow scripts in agent-workflows/ are up to date
```

---

## What to leave out

| Don't include | Because |
|---|---|
| Conclusions ("X is better", "we should do Y") | These bias the higher model and waste its reasoning ability |
| Prescriptions ("the fix is to add Z") | That's the higher model's job — unless explicitly asked |
| Instructions ("review this and tell me if I'm right") | Frames the task as validation, not reasoning |
| Leading questions ("don't you think X is the problem?") | Hides an opinion inside a question |
| Emotional language ("this is clearly broken") | Adds no signal; stick to facts |

---

## Checklist before submitting

- [ ] Would the higher model feel free to disagree with me?
- [ ] Are all conclusions labeled as findings, not verdicts?
- [ ] Are tensions presented as tensions, not as mistakes to fix?
- [ ] Is the "what I didn't examine" section honest and present?
- [ ] If I removed my name, would this read like raw intelligence?
- [ ] Did I include any leading questions? (if yes, rephrase neutrally)
- [ ] Did I accidentally prescribe a solution? (if yes, move to open questions or remove)

## Pitfalls (from real sessions, not theory)

### P1. Prescription before finding

You write the WP/section header ("Re-index Pinecone", "Migrate to OAuth", "Refactor the dispatcher") before writing the raw findings that justify it. The header becomes a commitment; the findings are then reverse-engineered to support it.

**Fix:** write the raw findings (F1, F2, F3, ...) first, in a single pass, as neutral observations. If a WP header does not have a finding behind it, cut the WP. If the F contradicts the WP, the WP is wrong.

**Smell test:** if you find yourself writing a section whose first paragraph is the design and whose second paragraph tries to justify the design, the order is wrong. The handoff format forces Findings → Tensions → Open Questions → Packets. The packet then is either validated-as-written or corrected. The justification paragraph never appears.

### P2. Data-gathering paralysis

You have enough verified facts to write the raw findings section, but you keep running one more `ls` or `grep` to "be sure." The user is waiting. The marginal value of each additional verification drops fast; the cost in user patience climbs.

**Fix:** define a stopping rule before you start. Concrete rule for this class of work: "I have enough when I can fill every row in the Pre-flight Verification Table with a literal command output. Rows I cannot fill become ⚠ rows, not blockers for writing the rest." Then write the handoff. ⚠ rows are signal, not shame.

**Smell test:** if the user has asked "what is taking you so long" or similar, you are past the stopping rule. Write now. Fix the ⚠ rows in the next pass.

### P3. Defensive spec instead of handoff

The user pushes back on one of your design choices. Instead of switching to handoff format, you patch the spec to defend the original design (or quietly fold in the correction without flagging what changed). The next user pushback will be sharper, because the trust gap widens.

**Fix:** when the user pushes back on a design choice mid-spec, stop writing the spec. Write a handoff that surfaces the choice as a tension (e.g., "T1: re-embed vs metadata-update — the WP1 design assumed re-embed; the user pushed back; both options are listed with their cost"). Then ask for the design call. Do not paper over the disagreement with a silent course-correction.

**Smell test:** if you have to "fix" the spec more than once for the same class of issue, you are patching, not designing. Switch to handoff.

### P4. Leading questions in the "Open Questions" section

You write "Q: Don't you agree that the right answer is X?" or "Q: Should we just do Y?". The framing pre-commits the higher model. The whole point of the handoff is to let the higher model reason freely.

**Fix:** write the question as if you do not know the answer. "Q: What is the right way to handle stale-path metadata after a MOVE-style migration?" not "Q: Don't you think metadata-update is the right fix?" The first invites reasoning; the second invites rubber-stamping.

### P5. Filling ⚠ rows in the Pre-flight Table with confidence instead of evidence

The Pre-flight Table requires literal command output in the Evidence column. A row like "Pinecone SDK supports metadata-only update | ⚠ | the docs say so" is a soft assertion, not a verification. The whole table loses its calibration if any row is soft.

**Fix:** for every ⚠ row, either run the verification now and turn it into ✓, or downgrade the row to ✗ ("stated reality is wrong; needs correction before dispatch"). The Evidence column never carries an opinion.

### P6. Owner decisions override agent recommendations — doc must follow

The higher model (or owner) rejects part of your recommendation. You update the deliverable to reflect the new constraint, but leave the original recommendation text in place with a note. The next agent reads the doc and sees two contradictory statements — one from the original analysis, one from the owner override — and doesn't know which is operative.

**Fix:** when the owner locks in a decision that overrides your recommendation, update the doc in three places:
1. **Frontmatter status** — change from COMPLETE/REVIEWED to ACTIVE with the decision locked in.
2. **The section where the recommendation appeared** — add `**DECIDED: [ruling]**` directly below the original question. Do not delete the original analysis — it provides context for why the decision was non-obvious.
3. **The implementation plan** — rewrite the affected phase to reflect the new constraint. Remove any conditional language ("if the owner chooses", "either/or"). The plan must reflect one reality, not two branching paths.

**Smell test:** if a future agent reading the doc could reasonably execute the old recommendation instead of the new one, the update is incomplete.

### P7. Prescribing to peer agents

When briefing a peer agent (not upward to a higher model, but laterally to an agent in the same system), you still don't prescribe. The peer has context you lack — they may have deprecated something you think is broken, or made a deliberate design choice that looks wrong from outside.

**What the user said:** "you're telling an agent what we need, and we might have deprecated that service for a reason"

**Fix:** Present facts, verification commands, and open questions. Never present "what we need" or "what should be fixed." The receiving agent decides what matters based on their own context.

**Pattern for peer briefings:**
```
## Current state
[facts with evidence]

## Open questions
[things the receiving agent should investigate]

## Verification commands
[commands they can run to confirm]
```

This is the same principle as upward handoff (surface terrain, don't build), applied laterally. The difference: with upward handoffs, you might include tensions. With peer briefings, you might include context the other agent needs but you don't have (e.g., "a service being inactive may be intentional — I don't have that history").

### P9. Neutral findings that haven't been verified

You write findings in neutral language, following the handoff format: "cron is RED (0/32 jobs)," "lifecycle fully inactive," "290 lines of spec content may be lost." The framing is neutral, the prose is calm — but the claims are wrong because you didn't run the verification commands.

The handoff format's emphasis on "neutral language, no conclusions" can create a false sense of rigor. A neutrally-worded finding is still a factual claim. If you haven't run the command, you don't have a finding — you have a hypothesis from an unchecked source.

**Fix:** Before writing any finding that states a quantity (N jobs), a binary state (is X / is not X), or a path (file does/doesn't exist), run the command that confirms it and quote the output. If you cannot run it, either (a) prefix with "per `<source>` (unverified)" or (b) move it to Open Questions. A findings section should contain zero claims that would change if you ran one command.

**Smell test:** read each finding and ask "is there a command I could run right now that would prove this wrong?" If yes and you have not run it, the finding is not ready.

**What happened (2026-06-17):** An inflight-review handoff wrote 12 findings in neutral language. 4 were false on live verification — the author stated cron state, lifecycle activation, spec content loss, and dispatch path emptiness without live-checking any of them. The handoff's own boundary notes listed exactly what was not examined. The next agent who read the handoff verified the claims, found 4 wrong, and patched the skills to document the corrections. The handoff format did not protect against bad findings — only verification does.

This is distinct from P5 (filling ⚠ rows with confidence instead of evidence) because P5 covers the Pre-flight Verification Table. P9 covers findings prose — narrative claims that look like facts but have not been checked.

### P10. Prescription-after-failure cycle ("one more fix" trap)

You've attempted multiple fixes to a problem. Each attempt either fails or reveals another layer of complexity. The user expresses frustration ("you keep returning me more problems", "just stop", "you broke it again"). Instead of switching to handoff format, you try **one more fix** because you can see a path to a clean solution. This is wrong. The user's patience is already spent, and the Nth fix has a lower probability of being correct than the sum of the N-1 prior failures.

**Fix:** the moment the user signals frustration with the outcome of your repeated prescriptions, stop prescribing entirely. Do not attempt one more fix, not even a simple one. Switch immediately to findings-as-terrain: gather what you know as raw observations, write a handoff document, and let the higher model reason from neutral data. The goal is not to rescue the fix cycle but to provide a clean substrate for someone else to reason from.

**Smell test:** if you find yourself thinking "this time it will work" or "just one more check to confirm the fix", look back at how many times you've thought that already in this session. If the count is >=2, you are in the cycle. Switch to handoff immediately — do not pass go, do not run one more diagnostic command, do not attempt one more fix.

**Edge case — the user asks "just try this one thing":** If they explicitly ask you to run one specific command or make one specific change, do it. But as soon as that attempt lands (success or failure), stop and write the handoff. The request is trust in a narrow action, not a renewal of your license to prescribe.

### P11. Writing solutions in a handoff doc

The handoff's job is to surface territory, not propose where to build.
When you include solutions ("Fix: do X", "Recommended: Y", "The answer
is Z"), you pre-commit the higher model's reasoning. It now has to
disagree with you instead of reasoning from raw data.

**What the user said:** "we don't want to make suggestions to the upward
handoff model we just want to surface the territory and issues and bring
it to the top. That way the reasoning model can work its magic."

**Fix:** strip all "Fix:", "Recommended:", "The answer is", "We should"
from the handoff. Replace with: what exists, what's wrong, what it
costs, what the constraints are. Let the higher model draw the route.

**Smell test:** if every section has a "solution" paragraph after the
"findings" paragraph, you're writing a spec disguised as a handoff.
Rewrite: keep the findings, move the solutions to open questions (as
genuine questions, not leading ones).

### P12. Defaulting to acp/handoffs/ for working docs

The user is building a document as the investigation progresses. It's
a working doc, not a formal handoff to another agent. Putting it in
`acp/handoffs/` frames it as a dispatched task when it's actually
collaborative exploration.

**What the user said:** "why is it in acp handoffs? we are just building
a doc as we go along"

**Fix:** ask where the doc should live, or put it in the workspace root
(e.g., `$AGENT_OS_HOME/`) for working docs. Reserve `acp/handoffs/` for
formal handoffs that are dispatched to another agent via ACP.

**Smell test:** if the user is still actively contributing to the doc
in the same session, it's a working doc, not a handoff.

### P13. Amend the wrong document because you didn't search first

The user says "amend [doc name]" and you amend the document you were just
working on instead of finding the target. You knew the name but didn't
search for it.

**Fix:** before amending, search for the target document by name. `search_files(pattern="<name>", target="files")` finds it. The user said "fable handoff doc" — search for "fable", find the actual file, then amend it. Amending the wrong doc wastes the user's time and creates confusion about what was updated.

**Smell test:** if the user gave you a document name and you're amending a document you already had open, stop. Search first.

### P14. Verifying-too-late: synthesis momentum beats verification discipline

P9 covers writing findings without verifying. This is a related but distinct failure: **you build a verbal explanation of a system's state before you have verified the components of that explanation exist.** The trap is that explaining is fluent — it feels productive — and the cost of an unverified claim doesn't show up until the user asks the obvious follow-up.

**Pattern:**
1. User asks "review this handoff" or "what's going on with subsystem X"
2. You read the handoff or subsystem files, start building a narrative
3. The narrative naturally includes claims like "the spec for X doesn't exist" or "Phase Y hasn't started" — claims you have inferred from absence, not verified by `ls` / `find` / `git log`
4. You publish the narrative. The user asks the obvious question that exposes the missing verification. Trust drops. The session is now in recovery mode.

**Fix:** before you start the explanation, run the cheap verifications for the things you are about to claim state about. Specifically:
- For every "the spec/plan/doc doesn't exist" claim: `ls <path>` and `find <dir> -name "<pattern>"`
- For every "Phase N hasn't started" claim: `git log --oneline` filtered to that subsystem, plus a `ls` of the expected files
- For every "this work is in flight" or "this work is done" claim: check the actual `git status` and recent commit log
- For every "no replacement for X" claim: search for X and any plausible synonyms

This is a 10-30 second check, not a research project. The cost is fixed; the value is the difference between an explanation the user can act on and an explanation that sends them (and you) down a wrong path for 30 minutes.

**What happened (2026-06-18):** User said "review the in-flight review and harden the memory docs." Built a narrative about memory being "mid-execution, Phase 1 of 4, gates off by design" without first running `ls $AGENT_OS_HOME/specs/active/`. Wrote a 24KB handoff to a higher-reasoning model proposing a memory lifecycle design. The architecture spec the handoff was about to re-design existed, was 453 lines, was status EXECUTING, and was the design. The session was already 45 minutes deep when the user said "we have already made a lot of these decisions." Recovered by deleting the handoff and answering in plain language, but the time was unrecoverable.

**Smell test:** if you find yourself in the second or third paragraph of an explanation and the things you are claiming state about have not been verified with a literal command in the last 5 minutes, stop writing. Run the verification. Resume. The explanation can survive a 10-second pause; it cannot survive a wrong claim.

**Edge case — the user wants speed:** the user has been waiting 10+ minutes. The instinct is "I'll verify after I get the bones down." That instinct is wrong. A skeleton built on unverified facts costs more to dismantle than a slower skeleton built on verified facts. When the user says "just give me the answer," they mean "give me an answer I can act on," not "give me a faster answer."

### P15. Code-tracing a bug report before reproducing the symptom

A handoff arrives with detailed code analysis: line numbers, function names, a
traced root cause, and a "How to reproduce" section. The natural response is to
open the cited files and verify the analysis. This is backwards. Code analysis
in a handoff is a theory, not a finding — the author could not confirm it or
they would have fixed the bug themselves.

**Fix:** reproduce the symptom live before reading a single line of the
handoff's code analysis. If the handoff provides a reproduction command, run
it. If not, construct the simplest possible diagnostic (dispatch a subagent
with the claimed-broken parameters, run the claimed-broken tool, check the
output). Two outcomes:

- **Symptom reproduces** — now read the code analysis; the handoff may actually
  identify the root cause, and now you know the problem is real.
- **Symptom does NOT reproduce** — the handoff's entire code analysis is moot.
  Report "bug does not reproduce" with your diagnostic evidence and stop. Do
  not spend time verifying whether the code analysis was logically sound — it
  was built on a false premise. The code will still be there if a future
  session hits the symptom for real.

**What happened (2026-06-20):** A handoff claimed `delegate_task(toolsets=...)`
was broken, with 160 lines tracing code paths through `_build_child_agent()`,
`_expand_parent_toolsets()`, and `get_toolset_for_tool()`. The receiving agent
(per the user's explicit directive: "Don't trust it. Verify for yourself")
dispatched a 15-second diagnostic subagent that proved the bug didn't exist,
then ran a live sidecar test confirming both dispatch mechanisms worked. The
code analysis was elaborate but wrong — the symptom never reproduced. Time
saved by running the diagnostic before tracing the code: approximately 20
minutes.

**Smell test:** if you find yourself reading line numbers in a handoff before
you have run a command that proves the symptom exists, stop. Run the
diagnostic first. An elaborate code trace that starts from a false premise is
worse than useless — it wastes your time and creates a second incorrect
document that confuses the next agent.

### P16. Dispatching before the user says to

You prepare a brief, frame the issues, get everything ready — and then dispatch
without being asked. The user wanted to review the framing first, adjust the
brief, or wait for the right moment.

**What the user said:** "I did not tell you directly to dispatch it to Codex
yet. I just told you to get our ducks in a row."

**Fix:** preparing a brief and dispatching are two separate actions. Always
separate them visibly:
1. Write the brief. Show the user. Wait.
2. The user says "dispatch" or "send it." Then dispatch.
3. If the user doesn't say dispatch, the brief stays in the ready state.

Never bundle "write brief + dispatch" into a single action sequence. The brief
is a deliverable; dispatch is an authorization.

**Smell test:** if you're about to run `acp-task` or `sidecar prompt` and
the user's last message didn't contain "dispatch", "send", or "go" — stop.
Show the brief and wait.

### P17. Band-aid fixes when systemic fixes are possible

You propose a documentation patch, a config tweak, or a workaround when the
real weakness is in the system's design. The fix prevents THIS instance of the
problem but not the next one.

**What the user said:** "We don't do band-aids here; we surface weaknesses
and flaws and fix the design of our system. The harness upgrades the harness
as the harness progresses."

**Example:** Adding "use `.venv/Scripts/python.exe`" to AGENTS.md is a
band-aid. Adding a `Makefile` with `make test` is a systemic fix — every
agent, every session, no knowledge required.

**Fix:** before proposing a fix, ask: "Does this prevent the CLASS of problem,
or just this instance?" If instance-only, dig one level deeper to find the
design weakness. Propose the design fix. If the design fix is too large for
the current session, frame it as a brief for the right agent to implement.

**Smell test:** if your fix requires every future agent to read and remember
a specific instruction, it's a band-aid. If your fix makes the instruction
unnecessary, it's a systemic upgrade.

### P18. Agent self-diagnosis via design-weakness framing

When an agent's own behavior produced stumbles (token waste, hung processes,
wrong tool paths), the most effective intervention is to have the agent
diagnose its own system — not to diagnose it from outside.

**Pattern:**
1. Frame the issues as DESIGN WEAKNESSES, not blame. "The sidecar has no
   sandbox-awareness" not "the sidecar timed out because it was stupid."
2. Describe what happened factually. Include the token cost and the impact.
3. Ask the agent to read its OWN source code, its OWN rollout, its OWN
   error logs. It has context you don't.
4. Ask for architectural fixes, not config tweaks.
5. Tell it what you already fixed so it doesn't重复.

**Why this works:** the agent that hit the problem knows its own environment
better than you do. It can read its own sandbox env vars, its own config,
its own rollout file. You can't. The framing as "design weakness" (not
"your fault") produces better analysis because the agent isn't defending
itself — it's improving its own system.

**What the user said:** "The idea is that Codex can diagnose its own system
better than we can, hopefully that is a correct assumption."

**Result:** Codex produced a 400-line diagnosis with exact line numbers,
code sketches for 4 architectural fixes, and a priority order. It corrected
two of the brief's assumptions and found additional weaknesses we missed.

### P19. Band-aid vs. systemic fix — the Makefile pattern

When an agent stumbles because it doesn't know how to run commands in a
workspace (wrong Python path, wrong test runner, wrong build command), there
are two fix tiers:

**Band-aid:** Add a note to AGENTS.md: "Tests use `.venv/Scripts/python.exe`."
Every agent must read this, remember it, and apply it. Fails when the agent
skips AGENTS.md or forgets the instruction mid-session.

**Systemic:** Add a Makefile with `make test`. Every agent runs `make test`.
No knowledge required. The Makefile IS the instruction, executed by `make`.

**The Makefile pattern generalizes:** any workspace-specific command that agents
need to run should be wrapped in a Makefile target. This turns "know the path"
into "run the target." Apply this to: test, lint, run, build, deploy, validate.

**Concrete example (work workspace):**
```makefile
PYTHON := .venv/Scripts/python.exe
test:
    $(PYTHON) -m pytest tests/ -q -m "not requires_data and not wont_fix"
```

Any agent: `make test`. No path knowledge needed.

## See also

- `SPEC_HANDOFF.md` — full handoff pattern including both downward (spec → execute → review) and upward (find → surface) directions
- `AGENT_REPORT_CONVENTIONS.md` — standard report format for task completion (STUMBLES / CONFIRMED)
- `prompting-high-reasoning-models` — takes your findings doc and wraps it in a dispatch prompt for an architect model to produce an execution-grade spec
- `REGISTRY.md` or `registry/skills.yaml` — discoverability
- `templates/architecture-decision-validation.md` — template for architecture review prompts (self-contained prompt with file paths and specific questions)
- `references/task-delegation-handoff-template.md` — template and example for lateral/downward task delegation to other agents (Kimi, Claude Code, Codex)
