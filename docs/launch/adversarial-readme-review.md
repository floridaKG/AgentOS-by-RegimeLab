# Adversarial review — public tree (package 4)

**Date:** 2026-07-16  
**Reviewer posture:** Assume marketing is wrong; hunt disconfirming evidence.  
**Tree:** OSS staging repo after claim-safe README + cold-path pass.

## Stranger test

| Question | Answer from public tree only |
|---|---|
| What installs? | Local harness: CLIs under `bin/`, SQLite memory, skills, workflow scripts (`./install.sh`) |
| What must the user supply? | Python 3.10+, Git, Bash; agent CLIs + API keys only for multi-agent/MOE; ACPx for real dispatch; optional backend keys |
| Is review automatic? | **No.** Red-team / adversarial patterns are runnable workflows, not an automatic gate |

## Findings

| Sev | Finding | Disposition |
|---|---|---|
| BLOCKER | README `memory-st write` omitted required `--content-file` | **Fixed** — README + cold path |
| BLOCKER | Documented `recall "..."` is not the shipped CLI | **Fixed** — `memory-recall --text ...` |
| MAJOR | Narrative implied automatic memory injection on every agent start | **Fixed** — marked opt-in hook |
| MAJOR | ACP/MOE described as if zero-setup | **Fixed** — “with setup” / qualify |
| MAJOR | `memory/README` “works out of the box” | **Fixed** |
| MAJOR | Architecture “any agent / enforces” overclaim | **Fixed** — can connect / conventions |
| MAJOR | Private paths in `docs/assets/BRAND.md` | **Fixed** — in-repo assets only |
| MAJOR | Missing wiki overview video path for RESPEC | **Fixed** — `docs/assets/video/overview.mp4` |
| MINOR | CI could be read as full product guarantee | **Fixed** — CI honesty section |
| MINOR | Repo still **private** at review time | **Open** — owner package 5 live gate |
| INFO | Diagram HTML not interactive on github.com UI | **OK** — documented “open after clone” |
| INFO | Ambient maintainer env can leak keys into careless evidence captures | **Mitigated** — cold path uses `env -i`; evidence sanitized |

## Residual risks (not blockers for claim-safe draft)

- macOS untested (documented)  
- Installer warns if `pip` missing — core write/recall still worked after `memory-st init`  
- Hindsight wording remains optional (OK)  
- Public visibility is owner-only and not agent-complete  

## Verdict

**PASS for packages 1–4** after fixes, contingent on:

1. Cold-path evidence file present and PASS  
2. Static greps clean  
3. Package 5: push + public HTTP 200 (owner)

No unresolved BLOCKER/MAJOR remaining in the public docs after this pass, except
repository visibility (package 5).
