"""Tests for agent_os.diagnostics module."""

import pytest

from agent_os import diagnostics


class TestRunDiagnostics:
    """Tests for run_diagnostics()."""

    def test_returns_diagnostic_report(self):
        """Should return a DiagnosticReport object."""
        result = diagnostics.run_diagnostics()
        assert hasattr(result, "items")
        assert hasattr(result, "overall_status")

    def test_includes_installation_check(self):
        """Should include installation check."""
        result = diagnostics.run_diagnostics()
        check_names = [item.name for item in result.items]
        assert "installation" in check_names

    def test_includes_python_version_check(self):
        """Should include Python version check."""
        result = diagnostics.run_diagnostics()
        check_names = [item.name for item in result.items]
        assert "python_version" in check_names

    def test_includes_memory_check(self):
        """Should include memory subsystem check."""
        result = diagnostics.run_diagnostics()
        check_names = [item.name for item in result.items]
        assert "memory" in check_names

    def test_report_has_overall_status(self):
        """Should have an overall status."""
        result = diagnostics.run_diagnostics()
        assert result.overall_status in ["ok", "warn", "error"]


class TestRunHealthCheck:
    """Tests for run_health_check()."""

    def test_returns_diagnostic_report(self):
        """Should return a DiagnosticReport object."""
        result = diagnostics.run_health_check()
        assert hasattr(result, "items")
        assert hasattr(result, "overall_status")

    def test_includes_installation_check(self):
        """Should include installation check."""
        result = diagnostics.run_health_check()
        check_names = [item.name for item in result.items]
        assert "installation" in check_names

    def test_includes_memory_check(self):
        """Should include memory check."""
        result = diagnostics.run_health_check()
        check_names = [item.name for item in result.items]
        assert "memory" in check_names
