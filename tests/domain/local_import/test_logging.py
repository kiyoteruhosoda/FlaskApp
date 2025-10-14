"""domain.local_import.logging のテスト."""

from __future__ import annotations

from typing import Mapping

from domain.local_import.logging import LogEntry


def test_log_entry_compose_uses_default_status_when_not_provided() -> None:
    entry = LogEntry(message="processed", details={"item": "abc"}, session_id="session")

    composed, payload, status = entry.compose("info")

    assert status == "info"
    assert payload == {"item": "abc", "session_id": "session"}
    assert "processed" in composed
    assert "abc" in composed


def test_log_entry_compose_preserves_explicit_status() -> None:
    entry = LogEntry(message="processed", details={}, status="custom")

    _, _, status = entry.compose("info")

    assert status == "custom"


def test_log_entry_does_not_mutate_original_details() -> None:
    original: Mapping[str, str] = {"key": "value"}
    entry = LogEntry(message="message", details=original)

    _, payload, _ = entry.compose("info")

    assert dict(original) == {"key": "value"}
    assert payload is not original
