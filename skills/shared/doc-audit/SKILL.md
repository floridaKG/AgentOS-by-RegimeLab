---
id: doc-audit
name: doc-audit
description: Re-run the Agent OS doc-sprawl audit rubric against the canonical SAST. One batch per invocation. Use when top-level docs start accumulating drift, duplication, undated frontmatter, or stale specs masquerading as canonical.
trigger:
  - /doc-audit
scope: cockpit
status: stable
version: "1.0"
user-invocable: true
allowed-tools: Read, Write, Edit, Bash, Grep, Glob
companion_to: $AGENT_OS_HOME/docs/SYSTEM_ARCHITECTURE_SOURCE_OF_TRUTH.md
archive_run_1: $AGENT_OS_HOME/docs/archive/2026-05/DOC_AUDIT_run-1.md
last_reviewed: 2026-06-15
---

# /doc-audit — Agent OS Doc-Sprawl Audit Skill

This skill is the durable replacement for the original `DOC_AUDIT.md` (archived 2026-05-31)
(Run 1 completed 2026-05-17). It re-runs the rubric on demand when sprawl
risks returning. One batch per invocation, then stop.

**North star:** `SYSTEM_ARCHITECTURE_SOURCE_OF_TRUTH.md` (SAST) is canonical.
Every other doc must justify its existence against SAST or be removed.

To start a new audit run, create a tracking file at
`agent-os-docs/DOC_AUDIT.md` with the Status / Next Batch / Audit Log
sections, then execute Template A per batch. Archive run output to
`agent-os-docs/archive/<YYYY-MM>/DOC_AUDIT_run-N.md` at end-state.

## Pre-Flight: Read Coverage

Before applying any rubric, read every doc in scope. A surface pass that only checks last_updated dates and file names misses zombie docs that look maintained but are unused. The goal is not just to flag stale counts but to understand each doc's actual role in the harness.

### Pre-Classification: Tier Assignment

After reading each doc, assign a tier-level assessment BEFORE applying the verdict rubric. This distinguishes "how important is this doc" from "what do we do with it."

| Tier | Definition | Example |
|------|-----------|---------|
| **CORE** | Read by every agent on every boot via scan_path | AGENTS.md, BOOT_FACTS.yaml, ACP docs |
| **ROUTING** | Useful indexes and routing files, read on demand | AGENT_OS_INDEX.md, SOURCE_OF_TRUTH.md |
| **REFERENCE** | Important but rarely read, changes slowly | HANDOFF_AUTHORING_STANDARD.md, SPEC_TEMPLATE.md |
| **ZOMBIE** | Exists but not read or maintained in practice. Has stale content nobody updates. | CURRENT.md, ISSUES.md, NOW.md |
| **REDUNDANT** | Content fully captured in another doc. Duplicates boot chain or routing. | AGENT_OS_EXECUTION_BRIEF.md |

ZOMBIE and REDUNDANT files are candidates for archiving, but must go through the Salvage Before Archive protocol before any verdict is applied.

## Salvage Before Archive Protocol

**This is the critical step that was missing from Run 1.** When a file is classified as ZOMBIE or REDUNDANT, DO NOT archive it without first reading it for salvageable content. Zombie docs often contain valuable insights, workflows, design decisions, or tracking items that would be lost if archived without extraction.

### Step 1: Read the Complete Zombie

Read the entire file. Don't skim. The most valuable content is often in the sections that look stale at a glance — hidden gems in outdated boilerplate.

### Step 2: Classify Each Piece of Content

For each substantive section or claim, decide:

| Category | Action |
|----------|--------|
| **Active workflow** (numbered steps, procedures, exact commands) | Extract to the appropriate living skill or doc |
| **Design decision** (why X was chosen over Y) | Move to AGENTS.md design decisions section or the relevant workspace doc |
| **Open tracking item** (TODO, open issue, deferred work) | Move to the active tracking mechanism (kanban, BOOT_FACTS.yaml open_specs, or a living issue tracker) |
| **Verified baseline** ("these systems work, don't break them") | Move to AGENTS.md non-negotiables or BOOT_FACTS.yaml |
| **Session history** (blow-by-blow of what happened on a specific date) | If significant (ships a feature, fixes a bug), keep a one-line entry in CHANGELOG.md. Otherwise discard. |
| **Stale boilerplate** (template instructions, "how to use this file" sections, empty tables) | Discard. No extraction needed. |

### Step 3: Migrate Before Archive

For each piece of content worth saving:
1. Identify the target living doc (AGENTS.md, BOOT_FACTS.yaml, the appropriate skill, a kanban card)
2. Write the content concisely — zombies are often verbose; compress to actionable density
3. Fold into the target doc — verify it flows naturally with existing content
4. Verify the target doc wasn't already covering this content (zombies often duplicate living docs)

### Step 4: Extract the Systemic Pattern

Before closing the zombie, ask: **why did this file go stale?** Common patterns:

| Pattern | Root cause | Fix for the harness |
|---------|-----------|---------------------|
| Manual state doc | Nobody remembered to update it after sessions | Replace with generated state (a command agents run instead of reading a file) |
| Good idea, no enforcement | Everyone agreed to maintain it, nobody did | Either automate or archive — manual-only maintenance always decays |
| "Seemed useful at the time" | Created during a spike, never referenced again | Archive. No extraction needed unless it has unique content. |
| Cross-reference inertia | Doc is maintained by other docs referencing it, not by anyone reading it | If nobody reads it, archive it. Break the ref chain. |
| Too many on_demand docs | BOOT_FACTS.yaml lists 13 on_demand docs; agents read 0 of them | Cut to 3 max. Everything else goes to archive. |

Document each pattern found and what the fix would be. This becomes the input for the Root Cause Analysis report.

## Classification Rubric

For each doc, decide one verdict:

| Verdict | Meaning | Action |
|---|---|---|
| **KEEP** | SAST references it as canonical, OR it's a workspace/agent contract referenced by SAST. | Add/refresh frontmatter (`last_updated`, `status`). No content change unless drift. |
| **FOLD** | Content duplicates or extends a SAST section. Useful bits go into SAST. | Extract useful content into SAST (cite section). Replace doc body with a one-line redirect, then archive after a grace period. |
| **DEMOTE** | Real spec content but not a runtime contract. Shipped or in-flight. | `git mv` to `agent-os-docs/specs/` (in-flight) or `agent-os-docs/archive/<YYYY-MM>/` (shipped or superseded). Add `status:` frontmatter. |
| **ARCHIVE** | ZOMBIE or REDUNDANT after salvage. Content extracted or no unique value. | Run Salvage Before Archive protocol first. Then move to archive. Write a one-line pointer stub. |
| **DELETE** | Stale, contradicted, never used, or pure history with no extractable value. | `git rm`. Note the reason in the audit log row. |

If unsure between FOLD and DEMOTE: FOLD if SAST has a section it belongs in,
DEMOTE if it's standalone narrative.

If unsure between ARCHIVE and DELETE: ARCHIVE. Deletion is cheap to revert from
git history but expensive to relitigate; archiving is the safe default.

If unsure between ZOMBIE and REDUNDANT: ZOMBIE (it probably has salvageable content). REDUNDANT should be reserved for byte-identical duplicates.

## Audit Record Format

One row per doc:

```
| path | verdict | extracted into | reason | gate that would catch this | done by | date |
```

- `path` — relative to repo root or absolute if outside.
- `verdict` — KEEP / FOLD / DEMOTE / DELETE.
- `extracted into` — SAST section name if FOLD; new path if DEMOTE; `—` otherwise.
- `reason` — one short clause.
- `gate that would catch this` — the enforcement gate that would have prevented this finding from recurring (a check script, governance-check rule, lint, or generated-truth surface). `—` if none exists yet (then propose one in Self-Maintenance Recommendations). See the Gate-per-finding convention below.
- `done by` — agent or human identifier.
- `date` — YYYY-MM-DD.

## Per-Batch Hygiene

Every batch agent must, as the final step before reporting:

1. `git -C $AGENT_OS_HOME/agent-os-docs add -A` the audited files and any SAST/DOC_AUDIT edits.
2. `git -C $AGENT_OS_HOME/agent-os-docs commit -m "audit(batch-N): <one-line summary>"`. Do not push.
3. Then run `$AGENT_OS_HOME/bin/sync-docs` and report.

The docs repo is a SEPARATE git repo at `$AGENT_OS_HOME/docs/`. The home-layer no-git-write rule does NOT apply there.

## Root Cause Analysis (Required Deliverable)

Every audit run must include a systemic root cause analysis. Flagging individual stale docs is not enough — you must identify the patterns that allow them to accumulate.

### Analysis Format

```
## Systemic Patterns (Root Causes)

### Pattern N: [Title]

**Observation:** What you found — the specific stale claim, dead reference, or unmaintained doc.

**Root cause:** Why it happened. Not "nobody updated it" but "why didn't someone update it?"

**Fix for the harness:**
- Short-term: fix the doc
- Long-term: prevent recurrence (automation, enforcement, consolidation, or archive)

### Pattern N+1: ...
```

### Common Patterns (drawn from real audits)

| Pattern | Shows up as | Root cause | Harness fix |
|---------|-----------|-----------|-------------|
| **Manual state decay** | CURRENT.md, ISSUES.md, NOW.md all stale within days of last update | Manual maintenance has no enforcement. Agents forget or skip it. | Replace with generated state (a command or query agents run instead of a file they read). OR automate a cron that alerts when stale. |
| **on_demand as archive proxy** | BOOT_FACTS.yaml lists 13 on_demand docs; agents read 0 | on_demand feels like a safe middle ground but just hides the problem. Nobody has time to read 13 files. | Cut on_demand list to 3 max. Archive the rest. |
| **Cross-reference inertia** | Doc X only survives because 5 other docs reference it, not because anyone reads it | Docs accumulate references over time. Nobody breaks the chain because "it might be useful." | If nobody reads it directly, archive it and break the refs. The pain of updating refs is one-time; the pain of maintaining a zombie is ongoing. |
| **Good idea, no follow-through** | DOC_CHANGE_MAP.md, SHELF.md — created with intention, never touched again | Creating a doc feels like progress. Maintaining it doesn't. Without enforcement, every new doc decays. | Either automate it (cron, hook, generated) or don't create it. Manual-only maintenance is a promise that will be broken. |
| **Session history bloat** | CURRENT.md has 181+ lines of blow-by-blow that nobody reads after the current session | Agents treat session logs as permanent records. They should be ephemeral. | Keep session logs in CHANGELOG.md (one line per shipped change). The ACP run ledger and memory stack store the detail. |

## Self-Maintenance Recommendations (Required Deliverable)

Every audit must end with actionable recommendations for preventing future decay. A clean doc set that will be stale again in 30 days is not a win.

**Gate-per-finding convention (one-to-one hardening):** for each finding you FOLD, fix, or archive, name the specific enforcement gate that would have caught it — a check script, a governance-check rule, a lint, a generated-truth surface. Findings without a corresponding gate are one-off fixes that recur. This turns the audit from a cleanup into a hardening pass: the surface gets strictly harder to lie about over time. The Self-Maintenance Recommendations table below is the aggregate view; the gate-per-finding map is the per-item view. Both are required.

### Recommendation Format

| What | How | Who enforces | Priority |
|------|-----|-------------|----------|
| Replace CURRENT.md session state with agent-os-boot output | agent-os-boot already reads live state. Remove the manual update step. | Agent design (read a command, not a file) | P1 |
| Add last_updated check to agent-os-boot | agent-os-boot warns if BOOT_FACTS.yaml is >7 days stale | agent-os-boot script | P1 |
| Set up cron to archive unmaintained docs monthly | Script finds docs with last_updated > 60 days and not in boot chain, moves to archive | Cron job | P2 |
| Reduce BOOT_FACTS.yaml on_demand to 3 files | Trim the list, archive everything else | Manual (one-time) | P1 |

### Categories of Recommendation

1. **Automation** — scripts, crons, hooks that do the work without an agent remembering
2. **Consolidation** — merging overlapping docs so there's fewer surfaces to maintain
3. **Elimination** — archiving docs that have no unique value (they stop being maintenance liabilities)
4. **Enforcement** — checks that block or warn when maintenance is skipped

### Integration with SELF_MANAGEMENT.md

After identifying self-maintenance gaps, the audit should produce specific changes to SELF_MANAGEMENT.md:

- Add new doc maintenance rules (what gets updated when something changes)
- Add new enforcement mechanisms (how the system knows the rules were followed)
- Add new expiry policies (when docs auto-archive)


## Automated Precursor: Dream

Before running a manual doc-audit batch, consider running **Dream** first (`/dream` or `python3 dream/dream.py run`). Dream is an automated read-only crawl that:
- Verifies every file reference against the live filesystem
- Asks an LLM to verdict each doc as CLEAN or DRIFT
- Produces a digest with dangling references and drift findings

Dream catches the mechanical issues (broken paths, stale tool references, missing files) that would otherwise consume manual audit time. Run Dream, verify its findings, then use doc-audit for the higher-judgment work: tier assignment, salvage-before-archive, root cause analysis, and self-maintenance recommendations.

**Dream → doc-audit workflow:**
1. Run Dream: `python3 dream/dream.py run --goal "audit docs" --boundary dream/boundaries/docs-v1.yaml --max-iterations 40`
2. Verify DRIFT findings against live state (classify: regression/drift/artifact/false-positive)
3. Fix regressions and drift directly
4. Run doc-audit batch for remaining judgment calls (tier assignment, archival decisions)

## Related Workflow: Vault Wikilink-Graph Audit

`doc-audit` handles the `agent-os-docs/` SAST-baseline sprawl audit. A sibling
task the same skill supports: a deep read-only audit of the Knowledge Vault at
`$VAULT` — an Obsidian-style flat graph of atomic insights linked by
`[[wikilinks]]`, not a filesystem docs repo. Trigger phrases: "audit the vault",
"vault review", running `vault-audit-prompt.md`.

The vault has its own `/validate` skill, but it uses basename-only wikilink
resolution and over-reports broken links. This mode goes deeper: correct
Obsidian resolution, source-type classification, rename-target verification, and
MOC coverage measurement. Do NOT use `dream.py` for the vault (too slow /
rate-limited for a 600+ file graph) — run a bare Python sweep for the
deterministic phase, model only for classify/verify.

Full methodology, resolution rules, false-positive taxonomy, rename-rot
verification, and the resolver/regex pitfalls are in
`references/vault-wikilink-audit.md`. The 2026-06-18 pass found a structurally
healthy vault (zero orphan insights, zero broken MOC links, ~93% schema-compliant)
with a narrow actionable set: 3 confirmed rename-rot links, a 13-item capture
backlog, ~10 dangling concept links, and a MOC-coverage observation.

Output goes to `$AGENT_OS_HOME/docs/vault-audit-findings.md` (the
docs repo, NOT the vault). The vault itself is read-only during the audit.

## Related Workflow: DRAFT Spec Pre-READY Review

`doc-audit` handles batch audits of the docs surface. A sibling task the same skill should support: reviewing a single DRAFT spec in `agent-os-docs/specs/active/` before the owner flips it to `READY_FOR_IMPLEMENTATION`. Trigger phrases: "review this spec", "what do you think of <name>.md", "is this ready".

### When to apply

A spec is reviewable (not auditable) when:
- It is a single DRAFT file in `specs/active/` with `status: DRAFT` frontmatter
- It proposes a contract change touching core harness files (AGENTS.md, agent-os-boot, BOOT_FACTS.yaml, scan_path) or durable provider surfaces
- The owner wants feedback before READY, not a post-hoc drift audit

If the spec is past READY or already implemented, route to `changes-review` for post-fix audit.

### Live-Verify Before Reviewing

Specs are usually correct about their conclusions and wrong about their substrate. Before forming a verdict:

1. Read the spec end-to-end. Note every factual claim it makes about the system — file paths, file contents, command outputs, ordering, who prints what.
2. For each claim, verify against the live system: `cat` the file, run the command, `grep` the field. The spec's own `based_on` block names the substrate; use it.
3. Confirm or deny the spec's diagnosis explicitly in the review. A spec that is right about the problem but wrong about which file is causing it is still wrong.

This catches the most common spec failure mode: the spec author copy-pasted a description of the system from an old doc or memory, and the live state has drifted. A review that just agrees with the spec's framing inherits that drift.

### Review Output Shape

Match the user preference profile (concise, verdict-first, distilled):

1. **Verdict** (1 line) — sound direction / sound with gaps / needs rework
2. **Live-verified claims** — bullet list of the spec's claims that you confirmed against the live system, with the literal evidence. Proves the review is grounded, not vibes.
3. **Concerns in priority order** — gaps, missing file paths, missing verification coverage, scope creep, self-contradictions. Most important concern first. Each concern names the file/line/AC it touches.
4. **What the spec gets right** — short list, so the owner can act on what's already solid. Don't bury this in the concerns section.

End with `STUMBLES:` and `CONFIRMED:` per `AGENTS.md` non-negotiables. `STUMBLES` is empty for clean reviews; `CONFIRMED` lists the surfaces touched and verified.

### Common Spec Defects to Look For

| Defect | What to check |
|---|---|
| **Filename with spaces** | The spec self-references its own path. WSL quoting pain. If `name:` frontmatter is kebab-case but the filename has spaces, the filename is wrong. |
| **Vague source citation** | "Based on 2026-06-03 review" with no path or handoff. The claim is ungrounded — ask for the source. |
| **AC with no verification coverage** | Acceptance criteria the Section 5 verification block cannot prove. Either expand the verification or narrow the AC. |
| **Self-reference in scan_path** | `every_agent: [BOOT_FACTS.yaml, AGENTS.md]` — file lists itself. Logically odd; flag it. |
| **Phases masquerading as roles** | "architect / executor / reviewer" with no ACP dispatch shape. Clarify these are sequential phases, not separate agents, unless the spec actually dispatches them. |
| **Rollback list missing the spec itself** | If implementation invalidates the spec, rollback should include the spec file. Easy to forget. |
| **Overlay drift** | Spec says "do not widen into general docs cleanup" but ACs touch provider docs. Re-state the boundary in the role chain. |

### What This Section Is Not

- Not a replacement for `doc-audit` batch audits. One spec at a time.
- Not a replacement for `changes-review` post-fix audits. Pre-READY, not post-merge.
- Not a replacement for `spec-to-execution-handoff`. That skill creates specs; this reviews them.
- Not a path to rewriting the spec. Review produces feedback; the owner (or the spec author) decides what changes. Do not silently rewrite the spec and report success.

## Lessons & Pitfalls

- **"Inbox" means agent-mail, not todo.md.** When the user says to put something in another agent's inbox (e.g. "put this in Claude's inbox"), they mean `agent-mail send claude "subject" --summary "..." --body "..."`. Do NOT add it to `tasks/todo.md` or any workspace task file. Task files are for workspace-scoped execution tracking; agent-mail is for inter-agent async messaging. The user created agent-mail specifically for this channel. If you're unsure which to use, ask rather than guess wrong.

Patterns observed in Run 1. Read before launching the next agent.

- **FOLD activity is usually very light.** ~90% of verdicts in Run 1 were KEEP (with frontmatter refresh) or DEMOTE/DELETE. SAST was already strong. Resist the urge to fold marginally-useful content.
- **md5sum the root copy against `specs/active/` and `specs/completed/` FIRST.** Every Run 1 batch surfaced byte-identical duplicates from earlier doc-management drift. Detect → DELETE the root copy without ceremony.
- **Repointing cross-refs is real work.** When a doc gets DEMOTE'd to archive, every reference must be repointed. Always check HOME_LAYER_INDEX.md and MANIFEST.md after any DEMOTE.
- **SAST is the comparison baseline, not a thing to expand.** If SAST doesn't already have a section for it, it probably isn't architecture truth — DEMOTE the source doc instead.
- **Disagreements between checkpoint and next-batch agent should surface, not silently resolve.** Never silently downgrade a HIGH severity finding.
- **MANIFEST.md is auto-generated.** After any move/delete, regenerate with `python3 agent-os-docs/tools/generate_manifest.py`. Do not hand-edit.
- **AGENTS.md byte-identity rule.** Any edit must keep `$AGENT_OS_HOME/AGENTS.md` ≡ `agent-os-docs/AGENTS.md` ≡ root mirror. Verify with `cmp -s` on all three before committing.
- **Workspace AGENTS.md beats BOOT_FACTS when they conflict.** Each workspace owns its own entry path. BOOT_FACTS is a quick-reference; if it drifts, fix BOOT_FACTS, not the workspace.
- **Stale root mirrors survive archival.** `sync-docs` copies canonical → mirror but never cleans up mirrors when the canonical is archived. When verifying a file's existence for audit, check ALL three: canonical (`agent-os-docs/`), mirror (`$AGENT_OS_HOME/`), AND archive (`agent-os-docs/archive/<YYYY-MM>/`). The mirror may exist even though the canonical was archived months ago. This creates deceptive "file exists" results from mirror-only checks. Always declare which path you tested.
- **sync-docs diff tables in AGENTS.md are only as fresh as the last archive sweep.** AGENTS.md §File Sync Convention lists canonical→mirror pairs for files like GOALS.md. If the canonical was archived but the row was never removed, the table still claims a valid sync path. Cross-check every row in that table against actual file existence during audit — don't trust the table's claim that a file exists at the canonical path.
- **An archived doc's key claims can still enter agent context via session_search.** When an agent uses session_search to understand past work, it retrieves transcripts that may reference now-archived docs and their claims. Those claims may be stale or incorrect. Always verify key factual claims (counts, statuses, paths) against live state, not against session transcript snippets. Archive the doc, not its influence — session_search resurrects old claims without warning.
- **An archived doc's key claims can still enter agent context via session_search.** When an agent uses session_search to understand past work, it retrieves transcripts that may reference now-archived docs and their claims. Those claims may be stale or incorrect. Always verify key factual claims (counts, statuses, paths) against live state, not against session transcript snippets. Archive the doc, not its influence — session_search resurrects old claims without warning.
- **Adversarially re-attack your OWN findings with live read-only probes before reporting them confirmed.** This is the distinct second half of verify-before-trust: the first half guards against trusting other docs; this half guards against trusting your own unverified inferences. After producing a findings set, probe each factual claim (counts via Pinecone MCP / health endpoints, schedules by reading the live scheduler state directly, CLI flags via `--help`, gate behavior by reading the gate script source, paths/refs via `find`/`cmp`). In the 2026-06-18 review pass, re-attack changed 3 finding statuses: a HIGH ('spec ref missing') was downgraded (the spec existed in `completed/`, just a stale `active/` path); a finding was strengthened (the enforcement gate explicitly excluded the file it was supposed to guard — visible only by reading the gate source); a MEDIUM was downgraded to LOW (two CLI flags were both valid on different scopes). A findings report that skips this phase ships at least one wrong-severity claim. See `references/adversarial-reattack-methodology.md` for probe categories and a worked finding-revision table.

- **BOOT_FACTS.yaml `runtime_active_specs` paths are stale — check `completed/` and `archive/` before calling a file missing.** This is the single most common source of false-positive "missing file" claims in Agent OS doc audits. The `runtime_active_specs` section in BOOT_FACTS.yaml is a convenience view maintained by agents during sessions, not a reliable inventory — paths in it routinely lag behind actual file locations after lifecycle transitions (EXECUTING→DONE moves to `completed/`, RESEARCH→idle moves to `archive/`). When BOOT_FACTS references a file at `specs/active/<name>.md`, always run `find <specs_root> -name '<name>'` to locate it across all lifecycle directories before declaring it missing. The 2026-06-23 completeness check produced two false claims (memory-lifecycle-architecture.md at active/→actually completed/; memory-lifecycle-ml-scoring-research.md at active/→actually archive/) from exactly this pattern.
- **Wikilink-graph audits (vault): basename-only resolution over-reports broken links.** Obsidian resolves a `[[target]]` by basename OR path, and tolerates `.md` suffixes, `|alias`, `#heading`, `^blockref`. A resolver that checks basename only flagged all 6 vault MOCs as broken (319 reported vs 128 real) because path-style links like `[[docs/vault-os/BOOT]]` and `[[AGENTS.md]]` failed the basename check. On a 2026-06-18 vault pass this also masked that the vault was actually healthy (zero orphan insights, zero broken MOCs). Always implement full Obsidian resolution before trusting a broken-link count. See `references/vault-wikilink-audit.md`.
- **Wikilink-graph audits (vault): trailing markdown backticks inflate path-drift ~9x.** A path-extraction regex whose character class includes the backtick absorbs the closing backtick of a code span, so `$VAULT` is tested as `$VAULT\`` and reports "missing." 149 raw drift claims collapsed to 16 after excluding backtick from the class, and most of the 16 were globs/examples. Exclude backtick (and other markdown fence chars) from path regexes, then re-verify.
- **Rename-rot is the dominant real broken-link signal in a wikilink graph — verify by exact-basename existence, not fuzzy match.** When a note is renamed (often via `/refactor`), inbound links keep the old slug. Fuzzy token-matching surfaces candidates, but only exact-basename confirmation of the new slug is safe to call a Tier-1 fix; fuzzy alone misfires on short/generic targets like `[[career]]` or `[[ai-safety]]`. Downgrade unconfirmed matches to "investigate."
- **Subagent summaries are self-reports — re-verify their claims against live state before trusting them.** When you dispatch Explore/research subagents in parallel, their returned summaries are unverified. Re-verify each material claim (counts, paths, schedules, statuses) with your own read-only probes before folding it into the audit record. A contradicting subagent claim may be a transient (e.g. an auto-promote job flushing a backlog mid-session), not a subagent error — but you only know that after re-verification. Never let a subagent summary bypass the re-attack phase above.

## Prompt Templates

The next unit of work is one of: a standard batch, a checkpoint, or an
end-state pass. Pick the matching template, fill in the bracketed slots,
execute.

### Template A — Standard batch

```
You are running Batch [N] of the rolling Agent OS doc audit — [BATCH NAME].
One batch, then stop.

Context (read in this order):
1. agent-os-docs/SYSTEM_ARCHITECTURE_SOURCE_OF_TRUTH.md (SAST) — the
   comparison baseline. Read sections relevant to this batch's family.
2. The docs in scope for Batch [N].
3. agent-os-docs/DOC_GOVERNANCE_MATRIX.md — governance rules and cleanup matrix.

> NOTE: The original DOC_AUDIT.md audit log was archived 2026-05-31.
> This skill.md IS the living audit tool. If you need prior audit findings,
> check agent-os-docs/archive/2026-05/doc-governance/DOC_AUDIT.md.

First action: if the Carryover Tracker shows "Batch [N-1] commits NOT yet
applied," commit the prior batch's staged changes first under its own
commit message, then start this batch.

Pre-batch md5sum: for each doc in scope, md5sum it against any same-named
file in agent-os-docs/specs/active/ and agent-os-docs/specs/completed/.
Byte-identical matches get DELETE on the root copy without ceremony.

Use Explore subagents (read-only) in parallel for research. Split the batch
by sub-theme, give each subagent 2-4 docs, ask for a tight summary
classifying each as runtime contract / in-flight spec / shipped spec /
historical narrative, plus SAST overlap if any, plus unique facts worth
folding. Cap each subagent at ~400 words.

Apply verdicts per the rubric. Use git mv / git rm only — never plain
mv/rm. Before any DELETE: grep agent-os-docs/, $AGENT_OS_HOME/,
$AGENT_OS_HOME/bin/, $AGENT_OS_HOME/.config/ for the filename. If anything
references it, FOLD or DEMOTE instead. If a DEMOTE'd doc is referenced
by HOME_LAYER_INDEX.md or MANIFEST.md, repoint in the same batch.

Done means:
1. Every in-scope doc has a verdict applied on disk.
2. SAST contains any folded facts with source cited; bump SAST
   last_updated if edited.
3. Findings recorded in this session's report. DOC_AUDIT.md is archived —
   this skill.md serves as the audit tool.
4. Per-Batch Hygiene applied (commit in docs repo + sync-docs).
5. Report under 250 words.

Hard rules:
- Do NOT start the next batch.
- Do NOT edit docs outside this batch's scope except SAST.
- Surface checkpoint/prior-batch disagreements loudly in the report.
```

### Template B — SAST coherence checkpoint (mid-run)

```
You are running the SAST coherence checkpoint. Read-only pass. Do NOT
rewrite SAST.

Context:
1. agent-os-docs/SYSTEM_ARCHITECTURE_SOURCE_OF_TRUTH.md (SAST) — end-to-end.
   (DOC_AUDIT.md was archived 2026-05-31; carryover info is in this skill's history.)

Task: identify drift introduced by FOLD edits and frontmatter changes
across prior batches. Report:
- Duplicated content across SAST sections.
- Tonal mismatches.
- Dead cross-references.
- Sections that should be consolidated.
- Anything in SAST that is no longer accurate against the runtime.

Append findings to the session report. (DOC_AUDIT.md was archived 2026-05-31.)

Do NOT edit SAST.
```

### Template C — End-state pass

```
You are running the end-state pass. This concludes Run [N] of the audit.

Tasks:
1. Resolve remaining Carryover Tracker items or move them to
   agent-os-docs/POST_AUDIT_FOLLOWUPS.md.
2. Apply actionable SAST Coherence Pass findings.
3. Refresh $AGENT_OS_HOME/skills/doc-audit/SKILL.md if the rubric
   or pitfalls list has evolved.
4. Write the **Root Cause Analysis** — identify systemic patterns that
   allowed docs to go stale. Classify each pattern and propose a harness fix.
5. Write the **Self-Maintenance Recommendations** — specific actionable
   changes to prevent recurrence. Categorize as automation / consolidation /
   elimination / enforcement.
6. Archive the run-specific content (findings, RCA, recommendations) to
   agent-os-docs/archive/<YYYY-MM>/doc-audit-run-N.md.
   (DOC_AUDIT.md was already archived 2026-05-31 as a thin pointer doc.)
7. Verify $AGENT_OS_HOME/bin/docs-staleness-check still passes against the
   post-audit doc surface.
8. Bump SAST §Skills And Commands if anything changed.
9. Update CHANGELOG.md with a single entry summarizing the run.

Commit and sync-docs.
```

## See Also

- `references/vault-wikilink-audit.md` — Deep read-only audit of the Knowledge
  Vault (`$VAULT`): Obsidian wikilink resolution rules, the 4-phase sweep,
  false-positive taxonomy, rename-rot verification, and resolver/regex pitfalls.
  Use for "audit the vault" / running `vault-audit-prompt.md`.
- `references/registry-audit.md` — Methodology for verifying tools.yaml and
  skills.yaml claims against live system state. Use when adding a new agent,
  after registry edits, or during truth-harvest rounds.
