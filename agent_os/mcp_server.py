"""Agent OS MCP server — local stdio MCP server for memory and diagnostics.

Exposes six initial tools over stdio transport:
  - memory_search: Search memory records using FTS5
  - memory_write: Add a memory record with safe defaults
  - memory_list: List memory records with optional filters
  - memory_health: Check memory subsystem health
  - agent_os_doctor: Run comprehensive diagnostic checks
  - capabilities: Report version, platform, and features
"""

from __future__ import annotations

import asyncio
import re
from typing import Optional

from agent_os.memory import (
    add_memory,
    search_memory,
    list_memory,
    memory_health as mem_health_fn,
)
from agent_os.diagnostics import run_diagnostics
from agent_os.capabilities import get_capabilities

try:
    from mcp.server.fastmcp import FastMCP
except ModuleNotFoundError as exc:
    raise RuntimeError(
        "MCP support is not installed. Install it with: "
        "python -m pip install 'agent-os[mcp]'"
    ) from exc


# Create the MCP server
mcp = FastMCP(
    name="agent-os",
    instructions="Agent OS local memory and diagnostics server",
)

_ABSOLUTE_PATH = re.compile(r"(?:/[^\s,;)]{2,}|[A-Za-z]:\\[^\s,;)]{2,})")
_PATH_KEYS = {"home", "state_dir", "expected", "path", "db_path", "schema_path"}


def _redact_diagnostics(value):
    if isinstance(value, dict):
        return {
            key: "<redacted>"
            if key in _PATH_KEYS
            else _redact_diagnostics(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_diagnostics(item) for item in value]
    if isinstance(value, str):
        return _ABSOLUTE_PATH.sub("<local-path>", value)
    return value


@mcp.tool()
def memory_search(
    text: str,
    tier: str = "short_term",
    limit: int = 10,
) -> dict:
    """Search memory records using full-text search.
    
    Returns structured records with IDs, summaries, content, intent, timestamps,
    and source references. Results are bounded by the limit parameter.
    Does not return secrets or unrestricted environment contents.
    
    Args:
        text: Search query text
        tier: Memory tier (default: short_term)
        limit: Maximum number of results (default: 10, max: 100)
    
    Returns:
        Dictionary with ok status and results list
    """
    result = search_memory(text, tier=tier, limit=limit)
    return result.to_dict()


@mcp.tool()
def memory_write(
    summary: str,
    content: str,
    intent: str = "LESSON",
    kind: str = "observation",
    workspace: str = "default",
    agent_id: str = "user",
    run_id: Optional[str] = None,
    source_ref: str = "mcp:agent-os",
) -> dict:
    """Add a memory record to the short-term store.
    
    Only summary and content are required. Other fields receive safe defaults
    equivalent to the CLI behavior.
    
    Args:
        summary: Brief summary of the memory
        content: Full content text
        intent: Intent category (default: LESSON)
        kind: Record kind (default: observation)
        workspace: Workspace name (default: default)
        agent_id: Agent identifier (default: user)
        run_id: Run identifier (auto-generated if omitted)
        source_ref: Source reference (default: mcp:agent-os)
    
    Returns:
        Dictionary with ok status and record ID, intent, kind
    """
    result = add_memory(
        content,
        intent=intent,
        kind=kind,
        workspace=workspace,
        agent_id=agent_id,
        run_id=run_id,
        source_ref=source_ref,
        summary=summary,
    )
    return result.to_dict()


@mcp.tool()
def memory_list(
    intent: Optional[str] = None,
    workspace: Optional[str] = None,
    limit: int = 20,
) -> dict:
    """List memory records with optional filters.
    
    All filters are optional. Results are bounded by default and maximum limits.
    
    Args:
        intent: Filter by intent (e.g., LESSON, STUMBLE)
        workspace: Filter by workspace name
        limit: Maximum number of results (default: 20, max: 200)
    
    Returns:
        Dictionary with ok status, results list, and count
    """
    result = list_memory(
        intent=intent,
        workspace=workspace,
        limit=limit,
    )
    return result.to_dict()


@mcp.tool()
def memory_health() -> dict:
    """Check the health of the local memory subsystem.
    
    Returns database reachability, schema status, configured tier status,
    state path, and actionable remediation. Does not include credential values.
    
    Returns:
        Dictionary with ok status and diagnostic checks
    """
    return _redact_diagnostics(mem_health_fn().to_dict())


@mcp.tool()
def agent_os_doctor() -> dict:
    """Run comprehensive diagnostic checks.
    
    Verifies installation, state directories, Python dependencies,
    registries, memory readiness, and optional services.
    
    Returns:
        Dictionary with ok status, overall status, and check details
    """
    return _redact_diagnostics(run_diagnostics().to_dict())


@mcp.tool()
def capabilities() -> dict:
    """Return the Agent OS version, platform support, and enabled features.
    
    Includes version, platform support declaration, enabled local features,
    optional backend availability, and MCP server version.
    
    Returns:
        Dictionary with version, platform, home, core features, and optional backends
    """
    return _redact_diagnostics(get_capabilities())


def main() -> None:
    """MCP server entry point — runs stdio transport."""
    asyncio.run(mcp.run_stdio_async())


if __name__ == "__main__":
    main()
