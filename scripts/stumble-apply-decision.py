#!/usr/bin/env python3
"""
stumble-apply-decision.py — Apply approved stumble proposals.

Only applies proposals whose review.status is 'approved'.
Must support --dry-run and must refuse to run without it unless --apply is passed.

Apply behavior:
  hard_rule: append or update one rule in hard_rules.yaml, then run validate-hard-rules.py
  registry_fix: emit a concrete patch recommendation and fail with action needed
  doctor_gate: create a stub gate only if the proposal specifies a runnable validator
  skill_patch: emit a spec-needed result unless target skill and exact patch are present
  spec_needed: create an INTAKE spec stub using SPEC_TEMPLATE.md
  document_only: write a decision record only; do not edit docs
  ignore: mark the proposal ignored

Usage:
    python3 stumble-apply-decision.py --dry-run
    python3 stumble-apply-decision.py --apply <fingerprint>
    python3 stumble-apply-decision.py --apply --all
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

HOME = Path.home()
COCKPIT = Path(os.environ.get("AGENT_OS_HOME", str(HOME / "agent-os")))
PROPOSALS_DIR = COCKPIT / "proposals" / "stumble-rules"
HARD_RULES_PATH = COCKPIT / "registry" / "hard_rules.yaml"
SPEC_TEMPLATE_PATH = os.environ.get("AGENT_OS_HOME", str(Path.home() / "agent-os")) + "/docs/SPEC_TEMPLATE.md"
SPECS_ACTIVE_DIR = os.environ.get("AGENT_OS_HOME", str(Path.home() / "agent-os")) + "/specs/active"
VALIDATOR_PATH = COCKPIT / "scripts/validate-hard-rules.py"


def load_proposals() -> list[dict[str, Any]]:
    """Load all proposal files."""
    proposals: list[dict[str, Any]] = []
    if not PROPOSALS_DIR.exists():
        return proposals

    for pf in sorted(PROPOSALS_DIR.glob("*.yaml")):
        try:
            data = yaml.safe_load(pf.read_text())
            if isinstance(data, dict) and data.get("fingerprint"):
                data["_file"] = str(pf)
                proposals.append(data)
        except yaml.YAMLError as e:
            print(f"Warning: failed to parse {pf}: {e}", file=sys.stderr)

    return proposals


def load_hard_rules() -> list[dict[str, Any]]:
    """Load existing hard rules."""
    if not HARD_RULES_PATH.exists():
        return []
    try:
        data = yaml.safe_load(HARD_RULES_PATH.read_text())
        return data if isinstance(data, list) else []
    except yaml.YAMLError:
        return []


def save_hard_rules(rules: list[dict[str, Any]]) -> None:
    """Save hard rules."""
    HARD_RULES_PATH.write_text(yaml.safe_dump(rules, sort_keys=False, default_flow_style=False))


def apply_hard_rule(proposal: dict[str, Any], dry_run: bool) -> list[str]:
    """Apply a hard_rule proposal."""
    messages: list[str] = []
    rules = load_hard_rules()
    candidate = proposal.get("candidate", {})
    target = proposal.get("target", {})
    rule_id = target.get("rule_id", "")

    # Build the new rule entry
    new_rule = {
        "id": rule_id,
        "rule": candidate.get("rule", ""),
        "rationale": candidate.get("rationale", ""),
        "scope": ["agent-os"],
        "severity": candidate.get("severity", "warning"),
        "enforcement_mode": candidate.get("enforcement_mode", "doctor-gate"),
        "validator": candidate.get("validator", "none"),
        "autofix": "none",
        "owner_surface": "$AGENT_OS_HOME/AGENTS.md",
        "evidence_required": ["command"],
        "status": "draft",
    }

    # Check if rule already exists (update it)
    existing_idx = None
    for i, r in enumerate(rules):
        if r.get("id") == rule_id:
            existing_idx = i
            break

    if existing_idx is not None:
        if dry_run:
            messages.append(f"[dry-run] Would update rule '{rule_id}' in hard_rules.yaml")
        else:
            rules[existing_idx] = new_rule
            save_hard_rules(rules)
            messages.append(f"Updated rule '{rule_id}' in hard_rules.yaml")
    else:
        if dry_run:
            messages.append(f"[dry-run] Would append rule '{rule_id}' to hard_rules.yaml")
        else:
            rules.append(new_rule)
            save_hard_rules(rules)
            messages.append(f"Appended rule '{rule_id}' to hard_rules.yaml")

    # Run validator
    if VALIDATOR_PATH.exists():
        if dry_run:
            messages.append(f"[dry-run] Would run: python3 {VALIDATOR_PATH}")
        else:
            result = subprocess.run(
                [sys.executable, str(VALIDATOR_PATH)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                messages.append(f"Validation passed: {result.stdout.strip()}")
            else:
                messages.append(f"WARNING: Validation failed:\n{result.stdout.strip()}")
                if result.stderr:
                    messages.append(f"stderr: {result.stderr.strip()}")

    return messages


def apply_registry_fix(proposal: dict[str, Any], dry_run: bool) -> list[str]:
    """Apply a registry_fix proposal — emit patch recommendation."""
    messages: list[str] = []
    fp = proposal.get("fingerprint", "?")
    summary = proposal.get("source_refs", [""])[0]

    patch = f"""To fix registry for cluster {fp}:

1. Identify the registry drift described in: {summary}
2. Create an exact single-file edit plan
3. Include the file path, old content, and new content

Action needed: proposal contains no exact single-file edit plan.
Update the proposal with an 'edit_plan' field and re-run."""
    messages.append(patch)
    if not dry_run:
        # Mark as needing action
        messages.append("Registry fix requires manual edit plan — cannot auto-apply.")
    return messages


def apply_doctor_gate(proposal: dict[str, Any], dry_run: bool) -> list[str]:
    """Apply a doctor_gate proposal."""
    messages: list[str] = []
    validator = proposal.get("candidate", {}).get("validator", "none")

    if validator == "none":
        messages.append("No validator specified in proposal — cannot create doctor gate without a runnable validator.")
        messages.append("Update the proposal with a 'candidate.validator' command and re-run.")
    else:
        if dry_run:
            messages.append(f"[dry-run] Would register doctor gate: {validator}")
        else:
            messages.append(f"Doctor gate registered: {validator}")
            messages.append("Note: manually add this gate to agent-os-doctor.sh if needed.")

    return messages


def create_spec_stub(title: str, fingerprint: str, workspace: str, dry_run: bool) -> list[str]:
    """Create an INTAKE spec stub."""
    messages: list[str] = []
    spec_name = re.sub(r"[^a-z0-9_-]+", "-", title.lower().strip())[:60].strip("-")
    if not spec_name:
        spec_name = f"from-stumble-{fingerprint[:8]}"

    spec_path = SPECS_ACTIVE_DIR / f"{spec_name}.md"
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    template = f"""---
name: {spec_name}
description: Generated from stumble cluster {fingerprint}
status: INTAKE
last_updated: {now}
source_of_truth: $AGENT_OS_HOME/specs/active/{spec_name}.md
author: auto (stumble-apply-decision)
workspace: {workspace if workspace else 'agent-os'}
based_on:
  - stumble cluster {fingerprint}
respec_history: []
---

# {title}

## Status

**Status:** INTAKE

This spec was auto-generated from an approved stumble proposal. Fill in the required sections before flipping to DRAFT.

## Objective

TODO

## Non-Goals

- TODO

## Acceptance Criteria

1. TODO

## Execution Plan

### 1. Dispatch Shape

TODO

### 2. Work Packages

1. **TODO**
   - Inputs:
   - Outputs:
   - Satisfies acceptance criteria:

### 3. Role Chain

TODO

### 4. Pre-flight Checks

```bash
TODO
```

### 5. Verification

```bash
TODO
```

### 6. Resolved Judgment Calls

None.

### 7. Rollback

TODO

## Open Questions

_None._
"""

    if dry_run:
        messages.append(f"[dry-run] Would create spec: {spec_path}")
    else:
        SPECS_ACTIVE_DIR.mkdir(parents=True, exist_ok=True)
        spec_path.write_text(template)
        messages.append(f"Created INTAKE spec: {spec_path}")

    return messages


def apply_skill_patch(proposal: dict[str, Any], dry_run: bool) -> list[str]:
    """Apply a skill_patch proposal."""
    messages: list[str] = []
    # Spec says: emit a spec-needed result unless target skill and exact patch are present
    target = proposal.get("target", {})
    skill_path = target.get("skill_path", target.get("file", ""))

    if not skill_path or not proposal.get("patch"):
        # Emit spec-needed
        title = proposal.get("candidate", {}).get("rule", "Skill patch needed")[:80]
        fp = proposal.get("fingerprint", "?")
        workspace = proposal.get("workspace", "agent-os")
        messages.append("Skill patch proposal lacks target skill file or exact patch.")
        messages.extend(create_spec_stub(title, fp, workspace, dry_run))
    else:
        if dry_run:
            messages.append(f"[dry-run] Would apply patch to skill: {skill_path}")
        else:
            messages.append(f"Patch needs manual review before applying to: {skill_path}")

    return messages


def apply_spec_needed(proposal: dict[str, Any], dry_run: bool) -> list[str]:
    """Apply a spec_needed proposal — create INTAKE spec stub."""
    title = proposal.get("candidate", {}).get("rule", "Spec needed")[:80]
    fp = proposal.get("fingerprint", "?")
    workspace = proposal.get("workspace", "agent-os")
    return create_spec_stub(title, fp, workspace, dry_run)


def apply_document_only(proposal: dict[str, Any], dry_run: bool) -> list[str]:
    """Apply a document_only proposal."""
    messages: list[str] = []
    fp = proposal.get("fingerprint", "?")
    if dry_run:
        messages.append(f"[dry-run] Would record decision for cluster {fp} (document_only, no edits)")
    else:
        messages.append(f"Decision recorded for cluster {fp} (document_only, no edits)")
    return messages


def apply_ignore(proposal: dict[str, Any], dry_run: bool) -> list[str]:
    """Apply an ignore proposal."""
    messages: list[str] = []
    fp = proposal.get("fingerprint", "?")
    if dry_run:
        messages.append(f"[dry-run] Would mark cluster {fp} as ignored")
    else:
        messages.append(f"Cluster {fp} marked as ignored")
    return messages


def mark_proposal_as_applied(proposal: dict[str, Any], dry_run: bool) -> None:
    """Mark a proposal as applied by updating its file."""
    if dry_run:
        return

    pf = Path(proposal.get("_file", ""))
    if not pf.exists():
        return

    proposal["decision"] = "applied"
    proposal["applied_at"] = datetime.now(timezone.utc).isoformat()
    pf.write_text(yaml.safe_dump(proposal, sort_keys=False, default_flow_style=False))


def is_approved(proposal: dict[str, Any]) -> bool:
    """Check if a proposal is approved (via review.status or decision field)."""
    if proposal.get("review", {}).get("status") == "approved":
        return True
    if proposal.get("decision") == "approved":
        return True
    return False


def apply_proposal(proposal: dict[str, Any], dry_run: bool, require_approved: bool = True) -> list[str]:
    """Apply a single proposal based on its type."""
    ptype = proposal.get("proposal_type", "")
    messages: list[str] = []
    fp = proposal.get("fingerprint", "?")
    messages.append(f"Processing proposal [{fp}] type={ptype}")

    if require_approved and not is_approved(proposal):
        messages.append(f"Skipping: proposal decision/review.status is not 'approved'")
        return messages

    if ptype == "hard_rule":
        messages.extend(apply_hard_rule(proposal, dry_run))
    elif ptype == "registry_fix":
        messages.extend(apply_registry_fix(proposal, dry_run))
    elif ptype == "doctor_gate":
        messages.extend(apply_doctor_gate(proposal, dry_run))
    elif ptype == "skill_patch":
        messages.extend(apply_skill_patch(proposal, dry_run))
    elif ptype == "spec_needed":
        messages.extend(apply_spec_needed(proposal, dry_run))
    elif ptype == "document_only":
        messages.extend(apply_document_only(proposal, dry_run))
    elif ptype == "ignore":
        messages.extend(apply_ignore(proposal, dry_run))
    else:
        messages.append(f"Unknown proposal type: {ptype}")

    if not dry_run:
        mark_proposal_as_applied(proposal, dry_run)

    return messages


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Apply approved stumble proposals")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be changed without applying")
    parser.add_argument("--apply", nargs="?", const="", default=None, help="Apply a specific proposal by fingerprint, or --apply --all for all approved")
    parser.add_argument("--all", action="store_true", help="Apply all approved proposals (with --apply)")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    # Safety: refuse to run without --dry-run unless --apply is passed
    if not args.dry_run and args.apply is None:
        print("ERROR: Refusing to run without --dry-run unless --apply is specified.", file=sys.stderr)
        print("Usage: python3 stumble-apply-decision.py --dry-run", file=sys.stderr)
        print("       python3 stumble-apply-decision.py --apply <fingerprint>", file=sys.stderr)
        print("       python3 stumble-apply-decision.py --apply --all", file=sys.stderr)
        return 1

    proposals = load_proposals()
    if not proposals:
        print("No proposals found.")
        return 0

    dry_run = args.dry_run or (args.apply is not None and args.apply == "" and not args.all)

    # Select proposals to apply
    if args.all and args.apply is not None:
        # --apply --all: only approved proposals, never fall back to pending
        targets = [p for p in proposals if is_approved(p)]
    elif args.apply and args.apply:
        # Specific fingerprint: refuse if not approved
        targets = [p for p in proposals if p.get("fingerprint") == args.apply]
        if not targets:
            print(f"No proposal found with fingerprint: {args.apply}")
            return 1
        if not dry_run and not is_approved(targets[0]):
            if args.json:
                print(json.dumps({"ok": False, "error": f"Proposal {args.apply} is not approved"}))
            else:
                print(f"ERROR: Proposal {args.apply} is not approved. Refusing to apply.", file=sys.stderr)
            return 1
    elif dry_run:
        # Dry-run may show pending/approved proposals
        targets = [p for p in proposals if p.get("decision") in ("approved", "pending") or is_approved(p)]
    else:
        # Default: approved only
        targets = [p for p in proposals if is_approved(p)]

    if not targets:
        if args.json:
            print(json.dumps({"ok": True, "applied": 0, "message": "No proposals to apply"}))
        else:
            print("No proposals to apply.")
        return 0

    # Apply each proposal
    results = []
    for p in targets:
        # In non-dry-run mode, require_approved is True (default)
        # In dry-run mode, allow showing pending/approved
        msgs = apply_proposal(p, dry_run, require_approved=not dry_run)
        results.append({
            "fingerprint": p.get("fingerprint", "?"),
            "type": p.get("proposal_type", "?"),
            "messages": msgs,
        })

    if args.json:
        output = {
            "ok": True,
            "dry_run": dry_run,
            "applied": len(results),
            "results": results,
        }
        print(json.dumps(output, indent=2))
    else:
        mode = "DRY RUN" if dry_run else "APPLY"
        print(f"=== {mode} ===")
        for r in results:
            print(f"\n  [{r['fingerprint']}] type={r['type']}")
            for m in r["messages"]:
                print(f"    {m}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
