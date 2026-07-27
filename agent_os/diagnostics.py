"""Diagnostic checks for Agent OS health and status."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from agent_os.models import DiagnosticItem, DiagnosticReport
from agent_os.paths import get_agent_os_home, get_schema_path, get_state_dir


def run_diagnostics() -> DiagnosticReport:
    """Run comprehensive diagnostic checks.

    Verifies installation, state directories, Python dependencies,
    and core functionality.
    """
    report = DiagnosticReport()
    home = get_agent_os_home()

    # Installation check
    if home.exists():
        report.add(DiagnosticItem(
            name="installation",
            status="ok",
            message=f"Agent OS home found at {home}",
            details={"home": str(home)},
        ))
    else:
        report.add(DiagnosticItem(
            name="installation",
            status="error",
            message=f"Agent OS home not found at {home}",
        ))
        return report

    # State directory
    state_dir = get_state_dir()
    if state_dir.exists():
        report.add(DiagnosticItem(
            name="state_directory",
            status="ok",
            message=f"State directory exists at {state_dir}",
        ))
    else:
        report.add(DiagnosticItem(
            name="state_directory",
            status="warn",
            message=f"State directory not found. Run 'agent-os init' to create it.",
            details={"state_dir": str(state_dir)},
        ))

    # Python version
    py_version = sys.version_info
    if py_version >= (3, 10):
        report.add(DiagnosticItem(
            name="python_version",
            status="ok",
            message=f"Python {py_version.major}.{py_version.minor}.{py_version.micro}",
        ))
    else:
        report.add(DiagnosticItem(
            name="python_version",
            status="error",
            message=f"Python 3.10+ required, found {py_version.major}.{py_version.minor}",
        ))

    # Required dependencies
    deps = {"yaml": "PyYAML"}
    for module, package in deps.items():
        try:
            __import__(module)
            report.add(DiagnosticItem(
                name=f"dependency_{package}",
                status="ok",
                message=f"{package} installed",
            ))
        except ImportError:
            report.add(DiagnosticItem(
                name=f"dependency_{package}",
                status="error",
                message=f"{package} not installed",
                details={"install": f"pip install {package}"},
            ))

    # Schema file
    schema = get_schema_path()
    if schema.exists():
        report.add(DiagnosticItem(
            name="schema",
            status="ok",
            message="Memory schema file found",
        ))
    else:
        report.add(DiagnosticItem(
            name="schema",
            status="error",
            message="Memory schema file not found",
            details={"expected": str(schema)},
        ))

    # Memory database
    try:
        from agent_os.memory import memory_health
        mem_result = memory_health()
        if mem_result.ok:
            mem_data = mem_result.data
            mem_status = mem_data.get("status", "ok")
            report.add(DiagnosticItem(
                name="memory",
                status=mem_status,
                message=f"Memory subsystem: {mem_status}",
                details=mem_data,
            ))
        else:
            report.add(DiagnosticItem(
                name="memory",
                status="error",
                message=f"Memory check failed: {mem_result.error}",
            ))
    except Exception as e:
        report.add(DiagnosticItem(
            name="memory",
            status="error",
            message=f"Memory check failed: {e}",
        ))

    # Core scripts
    core_scripts = [
        ("agent-os", "bin/agent-os"),
        ("memory-st", "bin/memory-st"),
        ("recall", "scripts/recall.sh"),
    ]
    for name, rel_path in core_scripts:
        script = home / rel_path
        if script.exists():
            report.add(DiagnosticItem(
                name=f"script_{name}",
                status="ok",
                message=f"{name} found",
            ))
        else:
            report.add(DiagnosticItem(
                name=f"script_{name}",
                status="warn",
                message=f"{name} not found at {rel_path}",
            ))

    return report


def run_health_check() -> DiagnosticReport:
    """Run a simplified health check (single verdict).

    Returns ok if core functionality is available, warn if degraded,
    error if critical components are missing.
    """
    report = DiagnosticReport()

    # Quick checks only
    home = get_agent_os_home()
    state_dir = get_state_dir()

    # Installation
    if not home.exists():
        report.add(DiagnosticItem(
            name="installation",
            status="error",
            message="Agent OS not installed",
        ))
        return report
    report.add(DiagnosticItem(
        name="installation",
        status="ok",
        message=f"Agent OS installed at {home}",
    ))

    # State
    if not state_dir.exists():
        report.add(DiagnosticItem(
            name="state",
            status="warn",
            message="State not initialized. Run 'agent-os init'.",
        ))

    # Memory quick check
    try:
        from agent_os.memory import memory_health
        result = memory_health()
        if result.ok:
            report.add(DiagnosticItem(
                name="memory",
                status="ok",
                message="Memory subsystem healthy",
            ))
        else:
            report.add(DiagnosticItem(
                name="memory",
                status="warn",
                message=f"Memory: {result.error}",
            ))
    except Exception as e:
        report.add(DiagnosticItem(
            name="memory",
            status="error",
            message=f"Memory check failed: {e}",
        ))

    return report
