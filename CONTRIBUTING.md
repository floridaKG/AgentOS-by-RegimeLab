# Contributing to Agent OS

Thanks for considering contributing to Agent OS.

## How to contribute

1. **Fork the repo** on GitHub
2. **Create a branch** for your change (`git checkout -b my-feature`)
3. **Make your changes** — keep them focused and surgical
4. **Install gate dependencies** — `pip install -r requirements.txt`
5. **Run the privacy gate** — `bash tests/privacy/privacy_gate.sh .`
6. **Run the release gate** — `bash scripts/gate-release.sh`
   (this includes clean-room install, SuperDocs/Vault init, and manifest truth)
7. **Submit a pull request** against `main`

CI runs the same gates on pull requests. A green local release gate is the
best predictor of a green CI run.

## Guidelines

- **Keep changes surgical.** Touch only the files needed for your change. No
  speculative refactoring or unused abstractions.
- **Write tests.** If you add functionality, add a test. If you fix a bug, add
  a regression test.
- **Preserve the privacy boundary.** Don't include personal paths, credentials,
  or internal infrastructure references. See `PRIVACY_BOUNDARY.md`.
- **Follow the existing style.** Shell scripts use `set -euo pipefail`. Python
  follows PEP 8.
- **Don't commit bytecode.** `__pycache__/` and `*.pyc` are gitignored; leave
  them untracked.

## Code of Conduct

This project has a Code of Conduct (see `CODE_OF_CONDUCT.md`). By participating,
you agree to uphold it.
