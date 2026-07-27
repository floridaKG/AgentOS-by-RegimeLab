"""Capability reporting for Agent OS."""

from __future__ import annotations

import platform
import sys
from typing import Any

from agent_os import __version__


def get_capabilities() -> dict[str, Any]:
    """Return a structured capability report.

    Includes version, platform, enabled features, and optional backend status.
    """
    from agent_os.paths import get_agent_os_home

    home = get_agent_os_home()

    # Platform info
    plat = {
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "python_version": sys.version.split()[0],
    }

    # Core features (always available in local mode)
    core_features = {
        "memory_short_term": True,
        "memory_search": True,
        "memory_list": True,
        "memory_health": True,
        "diagnostics": True,
        "capabilities": True,
        "init": True,
    }

    # Optional backends (check availability)
    optional = {}
    try:
        import pinecone
        optional["pinecone"] = True
    except ImportError:
        optional["pinecone"] = False

    try:
        import neo4j
        optional["neo4j"] = True
    except ImportError:
        optional["neo4j"] = False

    return {
        "version": __version__,
        "platform": plat,
        "home": str(home),
        "core_features": core_features,
        "optional_backends": optional,
        "mcp_server_version": __version__,
    }
