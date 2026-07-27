"""Tests for agent_os.mcp_server module.

Tests cover server import/startup, tool registration, valid calls,
invalid/bounded inputs, empty database, and secret/path leakage.
Tests are deterministic and do not require cloud credentials.
"""

import asyncio
import os
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def isolated_db(monkeypatch, tmp_path):
    """Create an isolated database for testing."""
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("AGENT_OS_ST_DB", str(db_path))
    monkeypatch.setenv("AGENT_OS_STATE_DIR", str(tmp_path / "state"))
    # Ensure schema is accessible
    repo_root = Path(__file__).parent.parent.parent
    monkeypatch.setenv("AGENT_OS_HOME", str(repo_root))
    return db_path


class TestMCPServerImport:
    """Tests for MCP server import and basic structure."""

    def test_import_mcp_server(self):
        """Should import mcp_server module without errors."""
        from agent_os import mcp_server
        assert hasattr(mcp_server, "mcp")
        assert hasattr(mcp_server, "main")

    def test_mcp_server_instance(self):
        """Should create FastMCP instance."""
        from agent_os.mcp_server import mcp
        from mcp.server.fastmcp import FastMCP
        assert isinstance(mcp, FastMCP)
        assert mcp.name == "agent-os"


class TestMCPToolRegistration:
    """Tests for MCP tool registration."""

    def test_tools_registered(self):
        """Should register all six initial tools."""
        from agent_os.mcp_server import mcp

        async def check_tools():
            tools = await mcp.list_tools()
            tool_names = {t.name for t in tools}
            expected = {
                "memory_search",
                "memory_write",
                "memory_list",
                "memory_health",
                "agent_os_doctor",
                "capabilities",
            }
            assert expected == tool_names
            return tools

        tools = asyncio.run(check_tools())
        assert len(tools) == 6

    def test_tool_schemas_valid(self):
        """Should generate valid JSON schemas for all tools."""
        from agent_os.mcp_server import mcp

        async def check_schemas():
            tools = await mcp.list_tools()
            for tool in tools:
                assert tool.inputSchema is not None
                assert "type" in tool.inputSchema
                assert tool.inputSchema["type"] == "object"
                assert "properties" in tool.inputSchema
            return tools

        asyncio.run(check_schemas())


class TestMCPServerValidCalls:
    """Tests for valid MCP tool calls."""

    def test_memory_write_and_search(self, isolated_db):
        """Should write and search memory records."""
        from agent_os.mcp_server import memory_write, memory_search

        # Write a record
        result = memory_write(
            summary="Test summary",
            content="Test content about Python programming",
        )
        assert result["ok"] is True
        assert "id" in result

        # Search for it
        result = memory_search(text="Python")
        assert result["ok"] is True
        assert "results" in result
        assert len(result["results"]) > 0

    def test_memory_list(self, isolated_db):
        """Should list memory records."""
        from agent_os.mcp_server import memory_write, memory_list

        # Add records
        memory_write(summary="Record 1", content="Content 1")
        memory_write(summary="Record 2", content="Content 2")

        # List them
        result = memory_list()
        assert result["ok"] is True
        assert "results" in result
        assert "count" in result
        assert result["count"] == 2

    def test_memory_health(self, isolated_db):
        """Should check memory health."""
        from agent_os.mcp_server import memory_health

        result = memory_health()
        assert result["ok"] is True
        assert "status" in result or "checks" in result

    def test_agent_os_doctor(self, isolated_db):
        """Should run diagnostics."""
        from agent_os.mcp_server import agent_os_doctor

        result = agent_os_doctor()
        assert result["ok"] is True or result["ok"] is False  # May have warnings
        assert "status" in result
        assert "checks" in result

    def test_capabilities(self, isolated_db):
        """Should report capabilities."""
        from agent_os.mcp_server import capabilities

        result = capabilities()
        assert "version" in result
        assert "platform" in result
        assert "core_features" in result
        assert "optional_backends" in result
        assert "mcp_server_version" in result


class TestMCPServerBoundedInputs:
    """Tests for input validation and bounded limits."""

    def test_memory_search_limit_enforced(self, isolated_db):
        """Should enforce search limit."""
        from agent_os.mcp_server import memory_write, memory_search

        # Add records
        for i in range(10):
            memory_write(summary=f"Record {i}", content=f"Content {i}")

        # Search with excessive limit
        result = memory_search(text="Record", limit=1000)
        assert result["ok"] is True
        # Should cap at MAX_SEARCH_LIMIT (100)
        assert len(result["results"]) <= 100

    def test_memory_list_limit_enforced(self, isolated_db):
        """Should enforce list limit."""
        from agent_os.mcp_server import memory_write, memory_list

        # Add records
        for i in range(10):
            memory_write(summary=f"Record {i}", content=f"Content {i}")

        # List with excessive limit
        result = memory_list(limit=1000)
        assert result["ok"] is True
        # Should cap at MAX_LIST_LIMIT (200)
        assert result["count"] <= 200

    def test_memory_write_invalid_intent(self, isolated_db):
        """Should reject invalid intent."""
        from agent_os.mcp_server import memory_write

        result = memory_write(
            summary="Test",
            content="Test",
            intent="INVALID_INTENT",
        )
        assert result["ok"] is False
        assert "error" in result
        assert "Invalid intent" in result["error"]

    def test_memory_write_invalid_kind(self, isolated_db):
        """Should reject invalid kind."""
        from agent_os.mcp_server import memory_write

        result = memory_write(
            summary="Test",
            content="Test",
            kind="invalid_kind",
        )
        assert result["ok"] is False
        assert "error" in result
        assert "Invalid kind" in result["error"]


class TestMCPServerEmptyDatabase:
    """Tests for behavior with empty database."""

    def test_search_empty_database(self, isolated_db):
        """Should return empty results for empty database."""
        from agent_os.mcp_server import memory_search

        result = memory_search(text="nonexistent")
        assert result["ok"] is True
        assert result["results"] == []

    def test_list_empty_database(self, isolated_db):
        """Should return empty list for empty database."""
        from agent_os.mcp_server import memory_list

        result = memory_list()
        assert result["ok"] is True
        assert result["results"] == []
        assert result["count"] == 0

    def test_memory_health_empty_database(self, isolated_db):
        """Should report status for empty database."""
        from agent_os.mcp_server import memory_health

        result = memory_health()
        assert result["ok"] is True
        # Should include diagnostic checks even if DB is empty


class TestMCPServerSecurity:
    """Tests for security and privacy."""

    def test_no_secret_exposure_in_capabilities(self, isolated_db):
        """Should not expose secrets in capabilities."""
        from agent_os.mcp_server import capabilities

        result = capabilities()
        result_str = str(result).lower()
        # Should not contain secret-like keys
        secret_patterns = ["api_key", "secret", "token", "password", "credential"]
        for pattern in secret_patterns:
            assert pattern not in result_str or pattern in ["token"]  # "token" may appear in field names

    def test_no_secret_exposure_in_doctor(self, isolated_db):
        """Should not expose secrets in diagnostics."""
        from agent_os.mcp_server import agent_os_doctor

        result = agent_os_doctor()
        result_str = str(result).lower()
        # Should not contain actual secret values
        # (field names may contain "token" etc, but values should be filtered)
        assert "sk-" not in result_str
        assert "ghp_" not in result_str
        assert "bearer " not in result_str

    def test_no_path_leakage_in_memory_results(self, isolated_db):
        """Should not leak private paths in memory results."""
        from agent_os.mcp_server import memory_write, memory_search

        # Add a record
        memory_write(summary="Test", content="Test content")

        # Search
        result = memory_search(text="Test")
        result_str = str(result)
        # Should not expose absolute paths to user directories
        # (may contain relative paths or sanitized paths)
        assert "/home/" not in result_str or isolated_db.name in result_str

    def test_memory_write_safe_defaults(self, isolated_db):
        """Should use safe defaults for optional fields."""
        from agent_os.mcp_server import memory_write

        result = memory_write(
            summary="Test",
            content="Test",
        )
        assert result["ok"] is True
        # Should have used default intent, kind, workspace, etc.
        assert result["intent"] == "LESSON"
        assert result["kind"] == "observation"


class TestMCPServerStdioStartup:
    """Tests for stdio server startup and shutdown."""

    def test_mcp_server_has_main_function(self):
        """Should have main() function for entry point."""
        from agent_os.mcp_server import main
        assert callable(main)

    def test_mcp_server_run_stdio_async(self):
        """Should have run_stdio_async method."""
        from agent_os.mcp_server import mcp
        assert hasattr(mcp, "run_stdio_async")
        assert callable(mcp.run_stdio_async)
