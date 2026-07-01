# Pre-Commit Adversarial Review Checklist

## When to use

Before `git commit` when you have:
- Multi-file code changes (3+ files)
- File relocations (mv, rename, restructure)
- Changes touching `.gitignore` patterns
- Untracked working docs in the repo
- Credential-sensitive work

## Attack Vectors

### 1. Gitignore interactions
- Are any moved files landing in gitignored directories?
- `git status --short --ignored` — verify nothing is silently excluded
- `.gitignore` rules like `archive/` can swallow relocated tracked files

### 2. Sensitive file content
- Scan untracked files for API key prefixes, token patterns, credential material
- Look for `sk-`, `Bearer`, `api_key`, `.env` patterns

### 3. Incomplete commit boundary
- `git status --short` vs your review brief — any modified files you forgot to mention?
- Untracked `bin/` scripts, auto-generated files, sidecar artifacts

### 4. Code correctness
- `python3 -m py_compile` on all changed Python files
- `pytest` on related test suites
- `git diff --check` for whitespace/merge conflicts

### 5. Doc sync
- Check that AGENTS.md and other canonical docs are in sync
- Verify no unexpected diffs

## Dispatch template

```
Read the review brief.
Then read each modified file and check for:
1. Regressions, edge cases, correctness
2. git status, gitignore interactions, untracked files
3. Sensitive content in untracked files
DO NOT commit or stage. Report verdict and findings.
```
