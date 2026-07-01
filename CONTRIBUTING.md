# Contributing to Agent OS

Thanks for considering contributing to Agent OS.

## How to contribute

1. **Fork the repo** on GitHub
2. **Create a branch** for your change (`git checkout -b my-feature`)
3. **Make your changes** — keep them focused and surgical
4. **Run the privacy gate** — `bash tests/privacy/privacy_gate.sh .`
5. **Run the release gate** — `bash tests/clean-room/install_and_verify.sh`
6. **Submit a pull request** against `main`

## Guidelines

- **Keep changes surgical.** Touch only the files needed for your change. No refactoring, no speculative abstraction.
- **Write tests.** If you add functionality, add a test. If you fix a bug, add a regression test.
- **Preserve the privacy boundary.** Don't include personal paths, credentials, or internal infrastructure references.
- **Follow the existing style.** Shell scripts use `set -euo pipefail`. Python follows PEP 8.

## Code of Conduct

This project has a Code of Conduct (see `CODE_OF_CONDUCT.md`). By participating, you agree to uphold it.
