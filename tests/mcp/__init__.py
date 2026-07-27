"""MCP server tests for agent_os package.

Extend the package path so pytest's test package does not hide the MCP SDK.
"""

from pkgutil import extend_path

__path__ = extend_path(__path__, __name__)
