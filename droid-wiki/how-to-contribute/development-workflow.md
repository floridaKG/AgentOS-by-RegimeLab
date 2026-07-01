# Development workflow

## Purpose

This page describes the development workflow for Agent OS: how to set up a development environment, make changes, and get them merged.

## Branch strategy

Development happens on the `main` branch. Feature branches are used for larger changes and are merged via pull requests. The repository uses a linear history.

## Setup for development

1. Clone the repository:
   ```bash
   git clone https://github.com/floridaKG/AgentOS-by-RegimeLab.git
   cd AgentOS-by-RegimeLab
   ```

2. Run the installer in test mode:
   ```bash
   AGENT_OS_TEST=1 ./install.sh
   ```

3. Manually install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Making changes

1. Read `AGENTS.md` for the project's coding rules
2. Follow the patterns documented in [patterns-and-conventions.md](patterns-and-conventions.md)
3. Make surgical changes — touch only what you must
4. Update registry files if adding or modifying tools, skills, or workflows
5. Update schema files if modifying the memory system

## Verification

Before submitting, run:

```bash
# Registry consistency check
python3 scripts/registry-check.py

# Privacy gate
bash tests/privacy/privacy_gate.sh .

# Cold boot test
bash tests/smoke/cold_boot.sh

# Full release gate (comprehensive)
bash scripts/gate-release.sh
```

## Pull request process

1. Ensure all gates pass
2. Verify the EXPORT_MANIFEST.yaml is updated if adding new files
3. Submit the PR with a clear description of the change
4. Respond to review feedback
5. Squash-merge when approved

## Key source files

| File | Purpose |
|---|---|
| `install.sh` | Idempotent installer |
| `AGENTS.md` | Coding rules |
| `scripts/gate-release.sh` | Authoritative release gate |
| `EXPORT_MANIFEST.yaml` | Export allowlist |
