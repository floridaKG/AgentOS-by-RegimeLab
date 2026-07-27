"""Typed result and error models for the Agent OS core."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class OperationResult:
    """Standard result wrapper for core operations."""
    ok: bool
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"ok": self.ok}
        d.update(self.data)
        if self.error:
            d["error"] = self.error
        return d


@dataclass
class MemoryRecord:
    """Simplified memory record for CLI/MCP output."""
    id: str
    summary: str
    content: str
    intent: str
    kind: str
    workspace: str
    agent_id: str
    source_ref: str
    status: str
    created_at: str
    score: float | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if d.get("score") is None:
            d.pop("score", None)
        return d


@dataclass
class DiagnosticItem:
    """Single diagnostic check result."""
    name: str
    status: str  # "ok", "warn", "error"
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


@dataclass
class DiagnosticReport:
    """Collection of diagnostic items."""
    items: list[DiagnosticItem] = field(default_factory=list)
    overall_status: str = "ok"

    def add(self, item: DiagnosticItem) -> None:
        self.items.append(item)
        if item.status == "error" and self.overall_status != "error":
            self.overall_status = "error"
        elif item.status == "warn" and self.overall_status == "ok":
            self.overall_status = "warn"

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.overall_status != "error",
            "status": self.overall_status,
            "checks": [item.to_dict() for item in self.items],
        }
