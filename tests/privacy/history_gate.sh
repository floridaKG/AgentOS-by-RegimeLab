#!/usr/bin/env bash
# Scan every reachable Git commit and blob for private release material.
set -euo pipefail

ROOT="${1:-.}"
ROOT="$(cd "$ROOT" && pwd)"

if ! git -C "$ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "FAIL_SCAN: history gate requires a Git checkout" >&2
  exit 2
fi

ROOT="$ROOT" python3 <<'PY'
import os
import pathlib
import re
import subprocess
import sys

root = pathlib.Path(os.environ["ROOT"])


def git(*args, text=False):
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=text,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() if text else result.stderr.decode(errors="replace").strip()
        print(f"FAIL_SCAN: git {' '.join(args)} failed: {detail[:160]}", file=sys.stderr)
        raise SystemExit(2)
    return result.stdout


owner = os.environ.get("OWNER_USERNAME", "")
private_services = tuple(
    s.strip() for s in os.environ.get("PRIVATE_SERVICE_NAMES", "").split(",") if s.strip()
)
known_private_email = os.environ.get("PRIVATE_EMAIL", "").encode()

# Files that legitimately contain scanner patterns (gate scripts, docs, tests).
# These are excluded from the scan because security scanners must contain the
# patterns they scan for — this is architecturally necessary and documented
# in PRIVACY_BOUNDARY.md.
SAFE_PATH_PREFIXES = (
    b"tests/",  # test fixtures may embed scanner patterns / historical owner strings
    b"scripts/gate-privacy.sh",
    b"scripts/gate-release.sh",
    b"PRIVACY_BOUNDARY.md",
    b"LICENSE",
    b"SECURITY.md",
    b"droid-wiki/",
    b".github/workflows/",  # CI may set OWNER_USERNAME for scans
    b"bin/rtk",  # pre-built Rust binary — embedded Rust crate paths (/home/runner/.cargo/…) and public project emails are toolchain artifacts, not leaks
)

# Generic/example usernames that appear in documentation and test patterns.
# These are NOT private identifiers — they are placeholder examples.
SAFE_HOME_USERS = {b"example-user", b"user", b"username", b"testuser"}

byte_patterns = []
if owner:
    byte_patterns.append(("owner identifier", owner.encode()))
    byte_patterns.append(("owner Linux path", ("/home/" + owner).encode()))
    byte_patterns.append(("owner WSL path", ("/mnt/c/Users/" + owner).encode()))
if known_private_email:
    byte_patterns.append(("private email", known_private_email))
if private_services:
    for service in private_services:
        byte_patterns.append(("private infrastructure reference", service.encode()))

secret_patterns = [
    ("private key", re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("AWS key", re.compile(rb"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("GitHub token", re.compile(rb"\bgh[opurs]_[A-Za-z0-9]{20,}\b")),
    ("Google API key", re.compile(rb"\bAIza[0-9A-Za-z_-]{30,}\b")),
    ("npm token", re.compile(rb"\bnpm_[A-Za-z0-9]{30,}\b")),
    ("Pinecone key", re.compile(rb"\bpcsk_[A-Za-z0-9_-]{20,}\b")),
    ("Slack token", re.compile(rb"\bxox[baprs]-[A-Za-z0-9-]{20,}\b")),
    ("Stripe live key", re.compile(rb"\b[rs]k_live_[A-Za-z0-9]{16,}\b")),
    ("OpenAI-style key", re.compile(rb"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("JWT", re.compile(rb"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")),
    ("credentialed URL", re.compile(rb"[a-z][a-z0-9+.-]*://[^\s/:]+:[^\s/@]+@", re.I)),
    ("bearer token", re.compile(rb"\bBearer\s+[A-Za-z0-9._~-]{20,}\b", re.I)),
]
home_patterns = [
    re.compile(rb"/home/([A-Za-z0-9._-]+)(?:/|\b)"),
    re.compile(rb"/Users/([A-Za-z0-9._-]+)(?:/|\b)"),
    re.compile(rb"/mnt/[a-z]/Users/([A-Za-z0-9._-]+)(?:/|\b)", re.I),
    re.compile(rb"[A-Za-z]:\\Users\\([A-Za-z0-9._-]+)(?:\\|\b)", re.I),
]
email_pattern = re.compile(rb"\b[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b")
public_email_domains = {b"users.noreply.github.com", b"example.com", b"example.org", b"example.net"}
quoted_assignment = re.compile(
    rb"(?:api[_-]?key|access[_-]?key|auth[_-]?token|session[_-]?token|secret|token|password)"
    rb"\s*(?:=|:)\s*(['\"])([^'\"]{8,})\1",
    re.I,
)
unquoted_assignment = re.compile(
    rb"^\s*[A-Z0-9_]*(?:API[_-]?KEY|ACCESS[_-]?KEY|AUTH[_-]?TOKEN|SESSION[_-]?TOKEN|SECRET|TOKEN|PASSWORD)"
    rb"\s*(?:=|:)\s*([^\s#,]{8,})"
)
placeholder = re.compile(
    rb"(?:placeholder|example|sample|changeme|replace[-_]?me|your[-_]|here|not[-_]?set|"
    rb"none|null|dummy|redacted|\*{4,}|\$\{|<|os[.]environ|getenv)",
    re.I,
)

findings = set()


def is_safe_path(location):
    """Check if the location is a file that legitimately contains scanner patterns."""
    if not location.startswith("blob:"):
        return False
    # Extract path from "blob:oid:path" format
    parts = location.split(":", 2)
    if len(parts) < 3:
        return False
    path = parts[2].encode()
    for prefix in SAFE_PATH_PREFIXES:
        if path.startswith(prefix):
            return True
    return False


def scan_payload(data, location):
    # Skip files that legitimately contain scanner patterns
    if is_safe_path(location):
        return

    folded = data.lower()
    for kind, marker in byte_patterns:
        if marker.lower() in folded:
            findings.add((kind, location))
    for pattern in home_patterns:
        match = pattern.search(data)
        if match:
            # Extract the username from the match
            username = match.group(1).lower()
            # Skip generic/example usernames
            if username not in SAFE_HOME_USERS:
                findings.add(("private home path", location))
    for match in email_pattern.finditer(data):
        if match.group(1).lower() not in public_email_domains:
            findings.add(("personal email", location))
    for kind, pattern in secret_patterns:
        if pattern.search(data):
            findings.add((kind, location))
    for line in data.splitlines():
        quoted = quoted_assignment.search(line)
        unquoted = unquoted_assignment.search(line)
        value = quoted.group(2) if quoted else (unquoted.group(1) if unquoted else b"")
        if value and not placeholder.search(value):
            # Skip ENV_ prefixed variables — they store env var names, not credentials
            if unquoted:
                var_name = unquoted.group(0).split(b"=")[0].strip()
                if var_name.startswith(b"ENV_"):
                    continue
            findings.add(("hardcoded credential assignment", location))


for commit in git("rev-list", "--all", text=True).splitlines():
    # Commit objects include author/committer identities and the complete message.
    scan_payload(git("cat-file", "-p", commit), f"commit:{commit[:12]}")

objects = git("rev-list", "--objects", "--all", text=True)
for line in objects.splitlines():
    oid, _, path = line.partition(" ")
    if not path:
        continue
    scan_payload(path.encode(), f"path:{oid[:12]}:{path}")
    if git("cat-file", "-t", oid, text=True).strip() != "blob":
        continue
    data = git("cat-file", "-p", oid)
    scan_payload(data, f"blob:{oid[:12]}:{path}")

if findings:
    for kind, location in sorted(findings, key=lambda item: (item[1], item[0])):
        print(f"FAIL: {kind}: {location}")
    print(f"History Gate: FAIL ({len(findings)} findings)")
    raise SystemExit(1)

print("History Gate: PASS")
PY
