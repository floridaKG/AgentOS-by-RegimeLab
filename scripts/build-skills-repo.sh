#!/usr/bin/env bash
# Regenerate the unified Agent OS skills distribution repo from the canonical source.
#
# Canonical source of truth:  $AGENT_OS_HOME/skills/shared/<name>/SKILL.md
# Generated distribution repo: $AGENT_OS_HOME/agent-os-skills
#
# Serves the "install camp" agents that cannot dir-scan the canonical path:
#   - Codex : `install-skill-from-github.py --repo YOUR_GITHUB_ORG/agent-os-skills --path plugins/agent-os-shared/skills/<name>`
#   - Claude Code (alt to symlinks): `claude plugin marketplace add <git-url>` then install agent-os-shared
#             (reads .claude-plugin/marketplace.json + plugins/agent-os-shared/.claude-plugin/plugin.json)
#
# Dir-scan camp (Pi, Claude Code, OpenCode) does NOT need this repo; they read the
# canonical path / symlinks live. This repo is a COPY, so re-run after any skill edit.
# Commit/push explicitly after reviewing the generated diff; this script never writes git history.
set -euo pipefail

SRC=$AGENT_OS_HOME/skills/shared
REPO=$AGENT_OS_HOME/agent-os-skills
PLUGIN="$REPO/plugins/agent-os-shared"
ARCHIVE="$PLUGIN/archive"

# Skill list is DERIVED from canonical, not hardcoded: every shared skill whose
# SKILL.md frontmatter status is NOT deprecated/retired/disabled/inactive is
# distributed. This is the same is_active() rule skills-sync.sh uses, so a new
# active skill auto-distributes to the copy camp (Codex) and a deprecated
# one (e.g. 'now', rtk) auto-drops — no manual array edit, no two-camps drift.
# (History: rtk removed 2026-06-04 — ambient boot behavior, not a skill; this
# array was static through 2026-06-10 and silently dropped agent-os-governance-review,
# which is what motivated deriving it dynamically 2026-06-16.)
is_active() {
  local fm; fm=$(sed -n '/^---/,/^---/p' "$1/SKILL.md")
  ! grep -qiE '^status:[[:space:]]*(deprecated|retired|disabled|inactive)' <<<"$fm"
}
mapfile -t SKILLS < <(for d in "$SRC"/*/; do d="${d%/}"; [ -f "$d/SKILL.md" ] && is_active "$d" && basename "$d"; done | sort)
[ "${#SKILLS[@]}" -gt 0 ] || { echo "FATAL: no active skills under $SRC" >&2; exit 2; }

echo "Regenerating $REPO from $SRC ..."
mkdir -p "$REPO/.claude-plugin" "$PLUGIN/.claude-plugin"

# --- skills: clean copy from canonical (resolve symlinks with -L) ---
mkdir -p "$PLUGIN" "$ARCHIVE"
tmp_skills="$PLUGIN/skills.tmp.$$"
mkdir -p "$tmp_skills"
for s in "${SKILLS[@]}"; do
  if [ ! -f "$SRC/$s/SKILL.md" ]; then echo "MISSING canonical skill: $s" >&2; exit 1; fi
  cp -aL "$SRC/$s" "$tmp_skills/$s"
done
if [ -e "$PLUGIN/skills" ] || [ -L "$PLUGIN/skills" ]; then
  mv "$PLUGIN/skills" "$ARCHIVE/skills.$(date -u +%Y%m%dT%H%M%SZ)"
fi
mv "$tmp_skills" "$PLUGIN/skills"
echo "  copied ${#SKILLS[@]} skills into plugins/agent-os-shared/skills/"

# --- Claude Code marketplace manifest ---
cat > "$REPO/.claude-plugin/marketplace.json" <<'JSON'
{
  "$schema": "https://anthropic.com/claude-code/marketplace.schema.json",
  "name": "agent-os-skills",
  "description": "Agent OS shared skills - portable cross-agent harness skills (acp, agent-workflows, recall, lesson, digest, doc-audit, ingestr-data-pipeline, pinecone-search/upsert, changes-review, upward-handoff, multi-agent-opencode, codegraph-tools, tradingview-api, umbrella-refactor, sidecar).",
  "owner": { "name": "YOUR_GITHUB_ORG", "email": "your-github-email@example.com" },
  "plugins": [
    {
      "name": "agent-os-shared",
      "description": "The Agent OS os-shared skills. Portable floor: each needs only shell + file primitives.",
      "source": "./plugins/agent-os-shared",
      "category": "productivity"
    }
  ]
}
JSON

# --- plugin manifests ---
cat > "$PLUGIN/.claude-plugin/plugin.json" <<'JSON'
{
  "name": "agent-os-shared",
  "version": "0.1.0",
  "description": "Agent OS os-shared skills - portable across agents (shell + file primitives).",
  "author": { "name": "YOUR_GITHUB_ORG" }
}
JSON

# --- README ---
cat > "$REPO/README.md" <<'MD'
# agent-os-skills

Generated distribution of the **Agent OS os-shared skills**. Do not edit here.

- **Canonical source:** `$AGENT_OS_HOME/skills/shared/<name>/SKILL.md`
- **Regenerate:** `bash $AGENT_OS_HOME/scripts/build-skills-repo.sh` then commit + push.

## Skills

All skills are listed in the `SKILLS` array in `build-skills-repo.sh`.
Any new active skill in `$AGENT_OS_HOME/skills/shared/` must also be added there.

This repo exists to serve agents that cannot dir-scan the canonical path. The dir-scan
camp (Pi, Claude Code, OpenCode) reads the canonical path / symlinks live and does
**not** need this repo.

## Install

**Codex** (per skill, or loop the skills)
```
$AGENT_OS_HOME/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
  --repo YOUR_GITHUB_ORG/agent-os-skills --path plugins/agent-os-shared/skills/recall
# then: restart Codex
```

**Claude Code** (alternative to $AGENT_OS_HOME/.claude/skills symlinks)
```
claude plugin marketplace add https://github.com/YOUR_GITHUB_ORG/agent-os-skills.git
claude plugin install agent-os-shared@agent-os-skills
```

## Layout
```
.claude-plugin/marketplace.json     # Claude Code marketplace
plugins/agent-os-shared/
  ├─ .claude-plugin/plugin.json
  └─ skills/<name>/SKILL.md          # the skills (copied from canonical)
```
MD

cat > "$REPO/.gitignore" <<'MD'
.DS_Store
plugins/agent-os-shared/archive/
MD

echo "  wrote manifests + README"
echo "Done. Skills in repo: $(ls -1 "$PLUGIN/skills" | wc -l)"
