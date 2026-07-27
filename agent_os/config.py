"""Safe configuration loading and initialization for Agent OS."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from agent_os.paths import get_agent_os_home, get_state_dir


# Sensitive key patterns that must never be included in output
_SENSITIVE_PATTERNS = (
    "key", "secret", "token", "password", "credential", "api_key",
    "private", "auth", "session_key",
)


def _is_sensitive(key: str) -> bool:
    """Check if a config key name looks sensitive."""
    lower = key.lower()
    return any(pat in lower for pat in _SENSITIVE_PATTERNS)


def get_safe_config() -> dict[str, Any]:
    """Load non-sensitive configuration values.

    Reads from config.env.template (if present) and environment variables.
    Sensitive values (keys matching credential patterns) are excluded.
    """
    home = get_agent_os_home()
    config: dict[str, Any] = {}

    # Read template if available (for documentation purposes only)
    template = home / "config.env.template"
    if template.exists():
        try:
            with open(template) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        key = line.split("=", 1)[0].strip()
                        if not _is_sensitive(key):
                            config[key] = "(template default)"
        except (OSError, UnicodeDecodeError):
            pass

    # Overlay actual env vars (non-sensitive only)
    for key in ("AGENT_OS_HOME", "AGENT_OS_STATE_DIR", "AGENT_OS_ST_DB"):
        val = os.environ.get(key)
        if val and not _is_sensitive(key):
            config[key] = val

    config["home"] = str(home)
    config["state_dir"] = str(get_state_dir())

    return config


def init_workspace(force: bool = False) -> dict[str, Any]:
    """Initialize the workspace state directories.

    If force=False, preserves existing config and data.
    Returns a summary of what was done.
    """
    from agent_os.paths import ensure_state_dirs

    state_dir = get_state_dir()
    created = []
    existed = []

    if state_dir.exists() and not force:
        existed.append(str(state_dir))
    else:
        created.append(str(state_dir))

    dirs = ensure_state_dirs()
    for d in dirs:
        if d.exists() and str(d) not in created:
            existed.append(str(d))

    return {
        "ok": True,
        "state_dir": str(state_dir),
        "created": created,
        "existed": existed,
        "force": force,
    }
