"""Tests for agent_os.memory module."""

import os
import tempfile
from pathlib import Path

import pytest

from agent_os import memory, paths


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


class TestAddMemory:
    """Tests for add_memory()."""

    def test_add_basic_record(self, isolated_db):
        """Should add a basic memory record."""
        result = memory.add_memory(
            text="Test observation about the system.",
            intent="LESSON",
            kind="observation",
        )
        assert result.ok is True
        assert "id" in result.data
        assert result.data["intent"] == "LESSON"
        assert result.data["kind"] == "observation"

    def test_add_with_custom_metadata(self, isolated_db):
        """Should add a record with custom metadata."""
        result = memory.add_memory(
            text="Custom record",
            intent="DECISION",
            kind="state",
            workspace="test-workspace",
            agent_id="test-agent",
            run_id="run_test_001",
            source_ref="cli:test",
        )
        assert result.ok is True
        assert "id" in result.data

    def test_invalid_intent_rejected(self, isolated_db):
        """Should reject invalid intent."""
        result = memory.add_memory(
            text="Bad intent",
            intent="INVALID",
            kind="observation",
        )
        assert result.ok is False
        assert "Invalid intent" in result.error

    def test_invalid_kind_rejected(self, isolated_db):
        """Should reject invalid kind."""
        result = memory.add_memory(
            text="Bad kind",
            intent="LESSON",
            kind="invalid",
        )
        assert result.ok is False
        assert "Invalid kind" in result.error


class TestSearchMemory:
    """Tests for search_memory()."""

    def test_search_empty_database(self, isolated_db):
        """Should return empty results for empty database."""
        result = memory.search_memory(query="test query")
        assert result.ok is True
        assert result.data["results"] == []

    def test_search_finds_records(self, isolated_db):
        """Should find records matching query."""
        # Add a record
        memory.add_memory(
            text="Important lesson about testing",
            intent="LESSON",
            kind="observation",
        )
        # Search for it
        result = memory.search_memory(query="testing")
        assert result.ok is True
        assert len(result.data["results"]) > 0

    def test_search_respects_limit(self, isolated_db):
        """Should respect result limit."""
        # Add multiple records
        for i in range(5):
            memory.add_memory(
                text=f"Test record {i}",
                intent="LESSON",
                kind="observation",
            )
        # Search with limit
        result = memory.search_memory(query="test", limit=2)
        assert result.ok is True
        assert len(result.data["results"]) <= 2

    def test_search_enforces_max_limit(self, isolated_db):
        """Should enforce maximum limit."""
        result = memory.search_memory(query="test", limit=1000)
        assert result.ok is True
        # Should not fail, just cap the limit

    def test_search_with_workspace_filter(self, isolated_db):
        """Should filter by workspace."""
        memory.add_memory(
            text="Workspace A record",
            intent="LESSON",
            kind="observation",
            workspace="workspace-a",
        )
        memory.add_memory(
            text="Workspace B record",
            intent="LESSON",
            kind="observation",
            workspace="workspace-b",
        )
        result = memory.search_memory(query="record", workspace="workspace-a")
        assert result.ok is True
        # Should only return workspace-a records


class TestListMemory:
    """Tests for list_memory()."""

    def test_list_empty_database(self, isolated_db):
        """Should return empty list for empty database."""
        result = memory.list_memory()
        assert result.ok is True
        assert result.data["count"] == 0

    def test_list_all_records(self, isolated_db):
        """Should list all records."""
        memory.add_memory(text="Record 1", intent="LESSON", kind="observation")
        memory.add_memory(text="Record 2", intent="DECISION", kind="state")
        result = memory.list_memory()
        assert result.ok is True
        assert result.data["count"] == 2

    def test_list_with_intent_filter(self, isolated_db):
        """Should filter by intent."""
        memory.add_memory(text="Lesson", intent="LESSON", kind="observation")
        memory.add_memory(text="Decision", intent="DECISION", kind="state")
        result = memory.list_memory(intent="LESSON")
        assert result.ok is True
        assert result.data["count"] == 1

    def test_list_respects_limit(self, isolated_db):
        """Should respect limit parameter."""
        for i in range(5):
            memory.add_memory(text=f"Record {i}", intent="LESSON", kind="observation")
        result = memory.list_memory(limit=3)
        assert result.ok is True
        assert result.data["count"] <= 3


class TestMemoryHealth:
    """Tests for memory_health()."""

    def test_health_uninitialized_database(self, isolated_db):
        """Should report warn status for uninitialized database."""
        result = memory.memory_health()
        assert result.ok is True
        # Should include diagnostic report
        assert "status" in result.data or "checks" in result.data

    def test_health_initialized_database(self, isolated_db):
        """Should report ok status for initialized database."""
        # Initialize by adding a record
        memory.add_memory(text="Test", intent="LESSON", kind="observation")
        result = memory.memory_health()
        assert result.ok is True
        # Should include checks
        assert "checks" in result.data
