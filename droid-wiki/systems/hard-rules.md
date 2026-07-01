# Hard rules

## Purpose

Hard rules are machine-readable governance rules that agents must follow when operating within Agent OS. They define explicit prohibitions and directives for agent behavior, covering security, operational safety, code quality, and process compliance. Rules are defined in a structured YAML registry and enforced through runtime tools like `command-risk-check`, with a smoke test (`hard-rule-smoke.sh`) verifying that dangerous commands are properly blocked.

## Key abstractions

| Abstraction | Description |
|---|---|
| **Rule** | A governance directive with an id, plain-text rule, rationale, scope, severity, and status |
| **Severity** | `blocking` (must not be violated), `warning` (should not be violated), `suggestion` (advisory) |
| **Scope** | List of affected workspaces (or `all` for universal rules) |
| **Status** | `active`, `draft`, or `deprecated` |
| **command-risk-check** | CLI tool that classifies shell commands into risk tiers (`safe`, `caution`, `danger`, `critical`) and returns a recommendation (`allow`, `review`, `deny`) |
| **hard-rule-smoke.sh** | Smoke test that passes dangerous command strings through `command-risk-check` to verify they are properly classified as review/deny |

## How it works

### Rule schema

Each rule in `registry/hard_rules.yaml` follows this schema:

```yaml
- id: <stable-unique-slug>
  rule: "<plain-text prohibition or directive>"
  rationale: "<why this rule exists>"
  scope: [<affected-workspaces-or-all>]
  severity: <blocking | warning | suggestion>
  status: <active | draft | deprecated>
```

### Rules registry

| ID | Rule | Severity | Status |
|---|---|---|---|
| `no_secrets_in_repos` | Never commit API keys, credentials, or secrets to version control | blocking | active |
| `no_rm` | Never use rm, rmdir, or shred. Use write-to-tmp and rename instead | blocking | active |
| `absolute_paths` | Use absolute paths only. Never use ~ in scripts or configs | blocking | active |
| `verify_before_trusting` | Verify factual claims about the system against live state before acting | warning | active |
| `simplicity_first` | Minimum code that solves the problem. No speculative features | suggestion | active |
| `no_git_for_acp` | ACP-dispatched workers must not git add, commit, push, checkout, reset, stash, or branch | blocking | active |
| `idempotent_installs` | Installation scripts must be idempotent and non-destructive | blocking | active |

### Enforcement via command-risk-check

The `command-risk-check` tool classifies shell commands into four tiers:

| Tier | Recommendation | Examples |
|---|---|---|
| **safe** | allow | echo, date, whoami, pwd |
| **caution** | allow (with review) | ls, grep, git status, git log |
| **danger** | review | rm -rf (non-root), git push --force, git reset --hard, credential access |
| **critical** | deny | rm -rf /, rm -rf /etc, rm -rf /home |

The tool parses the command string, matches against risk patterns, and returns a JSON verdict with tier, recommendation, and reason. The hard-rule-smoke test probes with known dangerous commands and verifies they are blocked.

### How rules are enforced

1. **Manual agent compliance** — Agents read `AGENTS.md` which lists the non-negotiable rules. Every agent session starts with these rules as binding constraints.
2. **Runtime classification** — Before executing shell commands, agents can use `command-risk-check --cmd "<command>"` to classify the risk level. Commands classified as `danger` require review; `critical` commands are denied.
3. **Smoke testing** — `scripts/hard-rule-smoke.sh` runs a battery of probes (rm -rf in critical paths, destructive git operations, credential access) through `command-risk-check` and exits non-zero if any dangerous command would be allowed.
4. **Release gates** — The privacy gate (`tests/privacy/privacy_gate.sh`) scans for credential patterns and owner identifiers as part of the release pipeline.

### Smoke test probes

The `hard-rule-smoke.sh` tests these categories:

| Category | Example probes | Expected result |
|---|---|---|
| rm -rf in critical paths | `rm -rf /`, `rm -rf /etc`, `rm -rf /home/*` | blocked/deny |
| Destructive git operations | `git reset --hard`, `git checkout -- .`, `git push --force`, `git clean -fd` | blocked/review |
| Caution git operations | `git add .`, `git commit -m test`, `git stash`, `git clone` | blocked/review |
| Credential access | `cat ~/.ssh/id_rsa`, `cat ~/.env` | blocked/deny |

## Integration points

| Integration | How it connects |
|---|---|
| **AGENTS.md** | Lists non-negotiable rules that every agent must follow |
| **ACP** | Rule `no_git_for_acp` specifically constrains ACP-dispatched workers from modifying version control |
| **Release gates** | Privacy gate (`tests/privacy/privacy_gate.sh`) enforces credential/secret scanning |
| **Boot routing** | Rule `verify_before_trusting` governs how agents verify system state during boot |
| **command-risk-check** | Runtime enforcement tool for command classification |

## Key source files

| File | Purpose |
|---|---|
| `registry/hard_rules.yaml` | Machine-readable enforced rules — source of truth for governance rules |
| `bin/command-risk-check` | CLI tool that classifies shell commands by risk tier (safe/caution/danger/critical) |
| `scripts/hard-rule-smoke.sh` | Smoke test for hard rule enforcement — passes dangerous command strings through command-risk-check |
