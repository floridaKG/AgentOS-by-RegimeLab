"""Tests for agent_os.config module."""

import os
import tempfile
from pathlib import Path

import pytest

from agent_os import config


class TestGetSafeConfig:
    """Tests for get_safe_config()."""

    def test_returns_dict(self):
        """Should return a dictionary."""
        result = config.get_safe_config()
        assert isinstance(result, dict)

    def test_includes_home_and_state_dir(self):
        """Should include home and state_dir keys."""
        result = config.get_safe_config()
        assert "home" in result
        assert "state_dir" in result

    def test_excludes_sensitive_keys(self, monkeypatch):
        """Should exclude keys matching sensitive patterns."""
        monkeypatch.setenv("API_KEY", "secret123")
        monkeypatch.setenv("SECRET_TOKEN", "token456")
        result = config.get_safe_config()
        assert "API_KEY" not in result
        assert "SECRET_TOKEN" not in result

    def test_includes_safe_env_vars(self, monkeypatch, tmp_path):
        """Should include safe environment variables."""
        test_home = tmp_path / "home"
        test_home.mkdir()
        monkeypatch.setenv("AGENT_OS_HOME", str(test_home))
        result = config.get_safe_config()
        assert "AGENT_OS_HOME" in result
        assert result["AGENT_OS_HOME"] == str(test_home)


class TestInitWorkspace:
    """Tests for init_workspace()."""

    def test_creates_state_dirs(self, monkeypatch, tmp_path):
        """Should create state directories."""
        state_dir = tmp_path / "state"
        monkeypatch.setenv("AGENT_OS_STATE_DIR", str(state_dir))
        result = config.init_workspace(force=False)
        assert result["ok"] is True
        assert state_dir.exists()
        assert (state_dir / "memory").exists()

    def test_idempotent(self, monkeypatch, tmp_path):
        """Should not fail when called twice."""
        state_dir = tmp_path / "state"
        monkeypatch.setenv("AGENT_OS_STATE_DIR", str(state_dir))
        result1 = config.init_workspace(force=False)
        result2 = config.init_workspace(force=False)
        assert result1["ok"] is True
        assert result2["ok"] is True

    def test_force_flag(self, monkeypatch, tmp_path):
        """Should respect force flag."""
        state_dir = tmp_path / "state"
        monkeypatch.setenv("AGENT_OS_STATE_DIR", str(state_dir))
        result = config.init_workspace(force=True)
        assert result["force"] is True
        assert result["ok"] is True
