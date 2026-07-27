"""Tests for agent_os.capabilities module."""

import pytest

from agent_os import capabilities


class TestGetCapabilities:
    """Tests for get_capabilities()."""

    def test_returns_dict(self):
        """Should return a dictionary."""
        result = capabilities.get_capabilities()
        assert isinstance(result, dict)

    def test_includes_version(self):
        """Should include version field."""
        result = capabilities.get_capabilities()
        assert "version" in result
        assert isinstance(result["version"], str)

    def test_includes_platform_info(self):
        """Should include platform information."""
        result = capabilities.get_capabilities()
        assert "platform" in result
        assert "system" in result["platform"]
        assert "python_version" in result["platform"]

    def test_includes_core_features(self):
        """Should include core features."""
        result = capabilities.get_capabilities()
        assert "core_features" in result
        assert isinstance(result["core_features"], dict)
        # All core features should be enabled
        for feature, enabled in result["core_features"].items():
            assert enabled is True

    def test_includes_optional_backends(self):
        """Should include optional backends."""
        result = capabilities.get_capabilities()
        assert "optional_backends" in result
        assert isinstance(result["optional_backends"], dict)

    def test_includes_mcp_server_version(self):
        """Should include MCP server version."""
        result = capabilities.get_capabilities()
        assert "mcp_server_version" in result
