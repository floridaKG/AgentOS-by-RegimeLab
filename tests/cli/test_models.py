"""Tests for agent_os.models module."""

import pytest

from agent_os.models import OperationResult, MemoryRecord


class TestOperationResult:
    """Tests for OperationResult dataclass."""

    def test_success_result(self):
        """Should create a successful result."""
        result = OperationResult(ok=True, data={"count": 5})
        assert result.ok is True
        assert result.data == {"count": 5}
        assert result.error is None

    def test_error_result(self):
        """Should create an error result."""
        result = OperationResult(ok=False, error="Database not found")
        assert result.ok is False
        assert result.error == "Database not found"

    def test_to_dict(self):
        """Should convert to dictionary."""
        result = OperationResult(ok=True, data={"id": "test123"})
        d = result.to_dict()
        assert d["ok"] is True
        assert d["id"] == "test123"

    def test_to_dict_with_error(self):
        """Should include error in dictionary."""
        result = OperationResult(ok=False, error="Failed")
        d = result.to_dict()
        assert d["ok"] is False
        assert d["error"] == "Failed"


class TestMemoryRecord:
    """Tests for MemoryRecord dataclass."""

    def test_basic_record(self):
        """Should create a basic memory record."""
        record = MemoryRecord(
            id="test_001",
            summary="Test summary",
            content="Test content",
            intent="LESSON",
            kind="observation",
            workspace="default",
            agent_id="test-agent",
            source_ref="cli:test",
            status="active",
            created_at="2026-01-01T00:00:00Z",
        )
        assert record.id == "test_001"
        assert record.summary == "Test summary"
        assert record.intent == "LESSON"

    def test_record_with_score(self):
        """Should include search score when present."""
        record = MemoryRecord(
            id="test_002",
            summary="Matched",
            content="Content",
            intent="DECISION",
            kind="state",
            workspace="default",
            agent_id="agent",
            source_ref="test",
            status="active",
            created_at="2026-01-01T00:00:00Z",
            score=0.85,
        )
        assert record.score == 0.85

    def test_to_dict(self):
        """Should convert to dictionary."""
        record = MemoryRecord(
            id="test_003",
            summary="Summary",
            content="Content",
            intent="STUMBLE",
            kind="stumble",
            workspace="default",
            agent_id="agent",
            source_ref="test",
            status="active",
            created_at="2026-01-01T00:00:00Z",
        )
        d = record.to_dict()
        assert d["id"] == "test_003"
        assert d["intent"] == "STUMBLE"
        assert d["kind"] == "stumble"

    def test_to_dict_excludes_none_score(self):
        """Should exclude None score from dictionary."""
        record = MemoryRecord(
            id="test_004",
            summary="No score",
            content="Content",
            intent="LESSON",
            kind="observation",
            workspace="default",
            agent_id="agent",
            source_ref="test",
            status="active",
            created_at="2026-01-01T00:00:00Z",
            score=None,
        )
        d = record.to_dict()
        assert "score" not in d
