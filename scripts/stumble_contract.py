"""Shared stumble-system state and decision contracts."""

from __future__ import annotations

ACTIVE_STUMBLE_STATUS = "active"
VALID_DECISIONS = ("fix", "guardrail", "document", "ignore", "resolve")
VALID_DECISIONS_SQL = ", ".join(f"'{decision}'" for decision in VALID_DECISIONS)

DECISION_STATUS = {
    "document": "resolved",
    "fix": "resolved",
    "guardrail": "resolved",
    "ignore": "discarded",
    "resolve": "resolved",
}


def classify_frequency(count: int, age_days: int) -> str:
    if count == 1:
        return "first-occurrence"
    if age_days <= 7 and count <= 3:
        return "repeat"
    if age_days <= 7 and count > 3:
        return "systemic"
    if count <= 3:
        return "stale-repeat"
    return "systemic"
