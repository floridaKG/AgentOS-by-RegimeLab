# Testing

## Purpose

Agent OS uses a gate-based testing approach. Instead of a traditional test runner, verification is performed through structured gate scripts that validate different aspects of the system.

## Test types

### Privacy gate

`tests/privacy/privacy_gate.sh` — scans all shipped content for prohibited patterns:

- Owner identifiers and private paths
- Service identifiers
- API keys, tokens, and credentials
- Prohibited file types (.env, .sqlite, .pem, etc.)
- Registry consistency (all entries resolve to shipped files)
- YAML validity

Run:
```bash
bash tests/privacy/privacy_gate.sh .
```

### Cold boot test

`tests/smoke/cold_boot.sh` — validates repository structure and syntax:

- Checks that all required files and directories exist
- Validates YAML registry syntax
- Verifies script permissions
- Checks for dangling file references

### Release gate

`scripts/gate-release.sh` — comprehensive validation that combines all checks:

1. Privacy gate (23 checks)
2. Syntax and registry validation
3. Negative fixture tests
4. Clean-room installation (86 checks)
5. Vault init tests (9 checks)
6. SuperDocs init tests (27 checks)
7. No nested .ossbuild under shipped directories
8. Permission and dangling-command checks
9. No .git directory

### Clean-room test

`tests/clean-room/install_and_verify.sh` — proves that a new user can install Agent OS in an isolated temporary HOME without access to the owner's machine, private repositories, services, or filesystem layout.

### Manifest truth gate

`tests/manifest-truth-gate.sh` — validates that the EXPORT_MANIFEST.yaml accurately reflects the current state.

## Test scripts

Additional test scripts:

| Script | Purpose |
|---|---|
| `tests/test-init-vault.sh` | Tests Vault OS initialization |
| `tests/test-init-superdocs.sh` | Tests SuperDocs initialization |
| `scripts/hard-rule-smoke.sh` | Smoke-tests hard rules enforcement |
| `scripts/registry-check.py` | Validates registry consistency |

## Writing tests

New gates should be added as standalone shell scripts under `tests/` or `scripts/`. Each gate should:

1. Accept the staging directory as its first argument
2. Exit 0 on success, non-zero on failure
3. Produce clear PASS/FAIL output for each check
4. Be idempotent

## Key source files

| File | Purpose |
|---|---|
| `tests/privacy/privacy_gate.sh` | Privacy scanning gate |
| `tests/smoke/cold_boot.sh` | Structure and syntax validation |
| `tests/smoke/release_gate.sh` | Comprehensive release validation |
| `tests/clean-room/install_and_verify.sh` | Clean-room installation proof |
| `tests/manifest-truth-gate.sh` | Manifest consistency check |
| `scripts/gate-release.sh` | Consolidated release gate |
| `scripts/gate-privacy.sh` | Privacy gate runner |
| `scripts/gate-cleanroom.sh` | Clean-room gate runner |
