# Vault Wikilink-Graph Audit Methodology

Sibling audit mode to the SAST doc-sprawl audit. Use when auditing the Knowledge
Vault at `$VAULT` — an Obsidian-style flat graph of atomic insights linked by
`[[wikilinks]]`, not a filesystem docs repo. The mechanics (wikilink resolution,
orphan detection, MOC integrity) differ from path-drift/canonical-status audits.

The vault has its own `/validate` skill (`.claude/skills/validate/SKILL.md`) but it
uses basename-only resolution and over-reports broken links (see pitfalls). This
mode goes deeper: correct resolution, source-type classification, rename-target
verification, and MOC coverage measurement.

## Skip automated LLM pre-scans for the vault

Automated LLM crawls couple deterministic sweeps to slow, rate-limited LLM loops
and cover only a small subset of files in a short time. For a 600+ file graph,
run a bare Python sweep with no LLM in the loop for Phase 1 (full coverage
in seconds), then use the model only for classification and verification.

## Obsidian wikilink resolution rules (get this wrong and every count is garbage)

Obsidian resolves a `[[target]]` by **basename OR path**. A correct resolver MUST:

1. Strip the alias: `[[target|display text]]` -> `target`.
2. Strip the heading/blockref: `[[target#heading]]` and `[[target^blockid]]` -> `target`.
3. Strip the `.md`/`.MD` extension if present: `[[AGENTS.md]]` -> `AGENTS`.
4. An empty target after stripping (`[[#heading]]`) is a valid self-link -> resolves true.
5. Match the remaining token against: (a) any file basename (no ext) in the vault,
   OR (b) any relpath-without-ext, OR (c) any relpath ending in `/<token>`.

A basename-only resolver (step 5a only) over-reports broken links badly. On the
2026-06-18 pass it reported 319 broken; the correct resolver reported 128, and
revealed all 6 MOCs as clean (the basename-only pass had flagged ~30 path-style
MOC links like `[[docs/vault-os/BOOT]]` as broken — all false positives).

## The 4-phase arc (matches the doc-sprawl audit's shape)

1. **Deterministic sweep** (no LLM, full coverage): one Python script walks all
   `.md` files and extracts every dimension below into raw signal.
2. **Classify**: bucket raw findings into real-signal / false-positive / needs-verify.
   Filter aggressively.
3. **Verify**: for every load-bearing finding, check against the live vault.
4. **Write findings doc**: tiered fix list + per-dimension evidence + STUMBLES/CONFIRMED.

Expected noise funnel (2026-06-18): 2,023 wikilinks -> 128 unresolved -> 81
classified -> ~13 actionable. Most "broken" hits are false positives (taxonomy below).

## Dimensions to sweep

1. **Broken wikilinks**: every `[[target]]` that does not resolve. Dedupe by target.
2. **Orphan nodes**: notes with zero inbound wikilinks. Report insights separately
   from all-notes — zero orphan insights is the core health invariant; orphan
   non-insights (Leading-AI-Books, AI-Infrastructure notes) are softer signal.
3. **MOC integrity**: for each map-of-content file, do outbound links resolve? Then
   measure *coverage*: how many insights are linked by ANY MOC. (2026-06-18: 277 of
   278 insights were NOT MOC-linked — likely by design if MOCs are domain hubs, not
   insight indexes; needs owner intent to call it a defect.)
4. **Schema consistency** (insights/ only): frontmatter `summary` and `domain`
   required; `domain` must be knowledge-work / life-strategy / strategy (or type:moc).
5. **Capture backlog**: files in `capture/` with zero inbound links = unprocessed
   intake (awaiting `/extract` or `/ralph`). Report count + date span.
6. **Filesystem path drift**: `/mnt/...`, `$AGENT_OS_HOME/...`, `~/...` cited in vault
   docs that don't exist. See the backtick pitfall below.

## False-positive taxonomy (filter these before classifying)

- **Skill-doc example syntax**: `[[target-insight]]`, `[[new-insight-1]]`,
  `[[paper-slug-strategy-index]]` inside `.agents/skills/*/SKILL.md` and
  `.claude/skills/*/SKILL.md`. Illustrative, not real links.
- **Cross-workspace refs**: `[[Project A]]`, `[[Project B]]`. Expected
  missing — vault rule says stay in vault; these are other workspaces.
- **Template placeholders**: `[[filename]]`, `[[title]]`, `[[map-name]]` in
  `templates/` and `CLAUDE.md`.
- **Obsidian canvas artifacts**: `[[Drop Here]]` (drop-zone text) and
  `capture/🪤 Drop Here.md`.
- **Archive-sourced refs**: links inside `archive/` to old topic paths. Historical,
  not drift. Demote archive-only findings out of the real-signal set.

## Rename-rot verification (the high-value step)

Most real broken links are **rename-rot**: a note was renamed (often via `/refactor`)
but inbound links still use the old slug. To verify a candidate is a rename:

1. Fuzzy token-match the old slug against all basenames (share a distinctive 6+ char
   token) to surface candidate new slugs.
2. Then **confirm by exact-basename existence** of the candidate in the live file
   index before calling it a Tier-1 rename fix. Fuzzy alone is unreliable for
   short/generic targets (`career`, `ai-safety` match on tokens to unrelated notes)
   — downgrade those to "investigate," do not auto-classify as renames.

Worked renames (2026-06-18, all exact-confirmed):
- `nvidias-moat-is-software-hardware-standard-control-not-chip-spec-lead` ->
  `nvidias-capital-light-control-doctrine-do-as-much-as-necessary-as-little-as-possible`
- `china-export-controls-buy-time-but-accelerate-domestic-stack-localization` ->
  `china-export-controls-validated-nvidia-moat-thesis-by-helping-competitors-build-ecosystems`

## Resolver / regex pitfalls (hit on 2026-06-18)

- **Basename-only resolution over-reports broken links.** Obsidian resolves
  path-style and `.md`-suffixed links too. A basename-only pass flagged all 6 MOCs
  as broken. Fix: implement the full 5-step resolution above before trusting any
  broken-link count.
- **Trailing markdown backticks inflate path-drift 9x.** A path regex that includes
  `` ` `` in its character class absorbs the closing backtick of a code span
  (`$VAULT` + `` ` ``), so `$VAULT` reads as "missing" because the
  tested path has a trailing backtick. 149 raw drift claims collapsed to 16 real
  after excluding backtick from the character class. Of the 16, most were globs
  (`$AGENT_OS_HOME/bin/acp-*`), examples, or plan-doc aspirational paths. Real drift
  was ~2-3 items.

## Output shape

Write to `$AGENT_OS_HOME/docs/vault-audit-findings.md` (the docs repo,
NOT the vault — the vault is read-only during audit). Tiered fix list:

- Tier 1: confirmed rename-rot (repoint the link, do NOT rename the note back).
- Tier 2: capture backlog (workflow cadence; `/ralph` is the relief valve).
- Tier 3: dangling concept links (forward-refs to notes never written; owner
  decides create-or-remove) + loosely-matched candidates needing owner eyes.
- Tier 4: structural observations (e.g. MOC coverage gap) needing owner intent.
- Tier 5: confirmed false positives (leave alone).

## Emoji directory names

The vault uses emoji-prefixed directories: `🏷️ Topics/`, `📊 Processed/`,
`📥 Inbox/`, `🔍 Queries/`. `os.walk` handles them fine; just don't hardcode ASCII
path filters that miss them.
