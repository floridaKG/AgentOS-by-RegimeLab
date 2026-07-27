"""Tests for agent_os.paths module."""

import os
import tempfile
from pathlib import Path

import pytest

from agent_os import paths


class TestGetAgentOsHome:
    """Tests for get_agent_os_home()."""

    def test_returns_default_path_when_env_not_set(self, monkeypatch):
        """Should return package parent when AGENT_OS_HOME is not set."""
        monkeypatch.delenv("AGENT_OS_HOME", raising=False)
        result = paths.get_agent_os_home()
        assert isinstance(result, Path)
        assert result.exists()

    def test_returns_env_path_when_set(self, monkeypatch, tmp_path):
        """Should return AGENT_OS_HOME when set."""
        test_path = tmp_path / "custom_home"
        test_path.mkdir()
        monkeypatch.setenv("AGENT_OS_HOME", str(test_path))
        result = paths.get_agent_os_home()
        assert result == test_path.resolve()

    def test_resolves_symlinks(self, monkeypatch, tmp_path):
        """Should resolve symlinks in AGENT_OS_HOME."""
        real_path = tmp_path / "real"
        real_path.mkdir()
        link_path = tmp_path / "link"
        link_path.symlink_to(real_path)
        monkeypatch.setenv("AGENT_OS_HOME", str(link_path))
        result = paths.get_agent_os_home()
        assert result == real_path.resolve()


class TestGetStateDir:
    """Tests for get_state_dir()."""

    def test_returns_default_when_env_not_set(self, monkeypatch):
        """Should return ~/.local/state/agent-os when AGENT_OS_STATE_DIR not set."""
        monkeypatch.delenv("AGENT_OS_STATE_DIR", raising=False)
        result = paths.get_state_dir()
        expected = Path.home() / ".local" / "state" / "agent-os"
        assert result == expected

    def test_returns_env_path_when_set(self, monkeypatch, tmp_path):
        """Should return AGENT_OS_STATE_DIR when set."""
        test_path = tmp_path / "custom_state"
        monkeypatch.setenv("AGENT_OS_STATE_DIR", str(test_path))
        result = paths.get_state_dir()
        assert result == test_path.resolve()


class TestGetShortTermDbPath:
    """Tests for get_short_term_db_path()."""

    def test_returns_default_path(self, monkeypatch):
        """Should return memory/short_term.sqlite under state dir."""
        monkeypatch.delenv("AGENT_OS_ST_DB", raising=False)
        result = paths.get_short_term_db_path()
        expected = paths.get_state_dir() / "memory" / "short_term.sqlite"
        assert result == expected

    def test_returns_env_path_when_set(self, monkeypatch, tmp_path):
        """Should return AGENT_OS_ST_DB when set."""
        test_path = tmp_path / "custom.db"
        monkeypatch.setenv("AGENT_OS_ST_DB", str(test_path))
        result = paths.get_short_term_db_path()
        assert result == test_path.resolve()


class TestGetSchemaPath:
    """Tests for packaged and source-tree schema resolution."""

    def test_schema_exists_without_source_tree_home(self, monkeypatch, tmp_path):
        """Should resolve the bundled schema when AGENT_OS_HOME has no schema."""
        monkeypatch.setenv("AGENT_OS_HOME", str(tmp_path))
        result = paths.get_schema_path()
        assert result.exists()
        assert result.name == "schema_short_term.sql"


class TestEnsureStateDirs:
    """Tests for ensure_state_dirs()."""

    def test_creates_directories(self, monkeypatch, tmp_path):
        """Should create state and memory directories."""
        state_dir = tmp_path / "state"
        monkeypatch.setenv("AGENT_OS_STATE_DIR", str(state_dir))
        result = paths.ensure_state_dirs()
        assert len(result) == 2
        assert state_dir.exists()
        assert (state_dir / "memory").exists()

    def test_idempotent(self, monkeypatch, tmp_path):
        """Should not fail when directories already exist."""
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        (state_dir / "memory").mkdir()
        monkeypatch.setenv("AGENT_OS_STATE_DIR", str(state_dir))
        result = paths.ensure_state_dirs()
        assert len(result) == 2
        assert state_dir.exists()
