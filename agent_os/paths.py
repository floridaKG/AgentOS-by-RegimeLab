"""Centralized path resolution for Agent OS installation and state directories."""

from __future__ import annotations

import os
from pathlib import Path
from importlib.resources import files


def get_agent_os_home() -> Path:
    """Return the Agent OS installation root.

    Uses AGENT_OS_HOME environment variable if set, otherwise resolves
    from the package location (parent of agent_os/ directory).
    """
    env_home = os.environ.get("AGENT_OS_HOME")
    if env_home:
        return Path(env_home).resolve()
    # Package is at <repo>/agent_os/, so home is parent
    return Path(__file__).resolve().parent.parent


def get_state_dir() -> Path:
    """Return the local state directory for Agent OS data.

    Uses AGENT_OS_STATE_DIR if set, otherwise defaults to
    $HOME/.local/state/agent-os.
    """
    env_state = os.environ.get("AGENT_OS_STATE_DIR")
    if env_state:
        return Path(env_state).resolve()
    home = Path.home()
    return home / ".local" / "state" / "agent-os"


def get_memory_dir() -> Path:
    """Return the memory state directory."""
    return get_state_dir() / "memory"


def get_short_term_db_path() -> Path:
    """Return the path to the short-term memory SQLite database.

    Respects AGENT_OS_ST_DB environment variable for test isolation.
    """
    env_db = os.environ.get("AGENT_OS_ST_DB")
    if env_db:
        return Path(env_db).resolve()
    return get_memory_dir() / "short_term.sqlite"


def get_schema_path() -> Path:
    """Return the path to the short-term memory schema file."""
    source_schema = get_agent_os_home() / "memory" / "core" / "schema_short_term.sql"
    if source_schema.exists():
        return source_schema
    packaged_schema = files("agent_os.resources").joinpath("schema_short_term.sql")
    return Path(str(packaged_schema))


def ensure_state_dirs() -> list[Path]:
    """Create required state directories if they don't exist.

    Returns list of directories created or verified.
    """
    dirs = [
        get_state_dir(),
        get_memory_dir(),
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
    return dirs
