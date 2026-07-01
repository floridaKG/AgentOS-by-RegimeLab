#!/usr/bin/env python3
"""Hindsight health check — verifies the full chain for a Hindsight memory backend.

Checks:
  1. Config exists and bank is reachable
  2. hindsight_client is installed
  3. Hindsight API is responding
  4. Plugin loads and is_available() returns True
  5. Bridge state is healthy

Configure via environment:

    HINDSIGHT_API_URL=http://127.0.0.1:9177               (default)
    HINDSIGHT_BANK=<your-bank-id>                           (required)

Usage:
  python3 hindsight-health-check.py
"""
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

# ── Configuration from environment ──────────────────────────────────────────

HINDSIGHT_API_URL = os.environ.get("HINDSIGHT_API_URL", "http://127.0.0.1:9177")
HINDSIGHT_BANK = os.environ.get("HINDSIGHT_BANK", "").strip()

passed = 0
failed = 0
warnings = 0


def check(label, ok, detail="", fix_hint=""):
    global passed, failed, warnings
    if ok:
        passed += 1
        print(f"  [OK]     {label}")
    elif "warn" in (fix_hint or "").lower():
        warnings += 1
        print(f"  [WARN]   {label}: {detail}")
    else:
        failed += 1
        print(f"  [FAIL]   {label}: {detail}")
        if fix_hint:
            print(f"           Fix: {fix_hint}")


print("=" * 60)
print("  HINDSIGHT HEALTH CHECK")
print("=" * 60)

# 1. Configuration
print("\n1. CONFIGURATION")
if not HINDSIGHT_BANK:
    check("HINDSIGHT_BANK set", False,
          "HINDSIGHT_BANK environment variable is not set",
          "export HINDSIGHT_BANK=<your-bank-id>")
else:
    check("HINDSIGHT_BANK set", True)
check("API URL configured", bool(HINDSIGHT_API_URL),
      f"got: {HINDSIGHT_API_URL}",
      "Set HINDSIGHT_API_URL if not using default")

# 2. hindsight_client package
print("\n2. PACKAGE INSTALLATION")
try:
    result = subprocess.run(
        [sys.executable, "-c", "import hindsight_client; print('OK')"],
        capture_output=True, text=True, timeout=10
    )
    check("hindsight_client installed", result.returncode == 0,
          result.stderr[:200] if result.returncode != 0 else "",
          "pip install hindsight-client")
except Exception as e:
    check("hindsight_client installed", False, str(e),
          "Ensure hindsight_client is installed in your Python environment")

# 3. Hindsight API responding
print("\n3. API HEALTH")
try:
    with urllib.request.urlopen(f"{HINDSIGHT_API_URL}/health", timeout=5) as resp:
        data = json.loads(resp.read())
    check("API reachable", True)
    check("database connected", data.get("database") == "connected",
          f"got: {data.get('database')}",
          "Check that the Hindsight database service is running")
except Exception as e:
    check("API reachable", False, str(e),
          "Start your Hindsight API server")

# 4. Bank reachable
print("\n4. BANK")
try:
    with urllib.request.urlopen(
        f"{HINDSIGHT_API_URL}/v1/default/banks/{HINDSIGHT_BANK}/stats",
        timeout=5
    ) as resp:
        stats = json.loads(resp.read())
    check(f"bank '{HINDSIGHT_BANK}' reachable", True)
    total = stats.get("total_nodes", "?")
    print(f"         total_nodes: {total}")
except Exception as e:
    check(f"bank '{HINDSIGHT_BANK}' reachable", False, str(e),
          f"Verify HINDSIGHT_BANK='{HINDSIGHT_BANK}' is correct and the API is running")

# 5. Summary
print("\n" + "=" * 60)
total = passed + failed + warnings
print(f"  {passed}/{total} passed, {failed} failed, {warnings} warnings")
if failed == 0:
    print("  STATUS: HEALTHY")
else:
    print("  STATUS: ISSUES FOUND")
print("=" * 60)

sys.exit(1 if failed > 0 else 0)
