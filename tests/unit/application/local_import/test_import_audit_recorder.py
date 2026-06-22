"""`import_audit_recorder` のレコード→監査エントリ変換の単体テスト。"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

from bounded_contexts.photonest.infrastructure.local_import.audit_logger import (
    LogCategory,
    LogLevel,
)
from bounded_contexts.photonest.infrastructure.local_import.import_audit_recorder import (
    _build_item_entry,
    _build_resume_entry,
    record_local_import_event,
)


def test_build_item_entry_success_uses_file_operation():
    entry = _build_item_entry(
        {
            "kind": "item",
            "session_id": 1,
            "item_id": "42",
            "file": "a.jpg",
            "filename": "a.jpg",
            "file_path": "/import/a.jpg",
            "status": "imported",
            "success": True,
            "failed": False,
            "from_state": "running",
            "to_state": "imported",
            "attempts": 1,
            "media_id": 7,
        }
    )
    assert entry.level == LogLevel.INFO
    assert entry.category == LogCategory.FILE_OPERATION
    assert entry.item_id == "42"
    assert entry.session_id == 1
    assert entry.from_state == "running"
    assert entry.to_state == "imported"
    assert entry.error_type is None
    assert entry.error_message is None
    assert entry.details["media_id"] == 7
    assert entry.details["attempts"] == 1
    assert "取り込み成功" in entry.message


def test_build_item_entry_failed_populates_error_columns():
    entry = _build_item_entry(
        {
            "kind": "item",
            "session_id": 2,
            "item_id": "99",
            "file": "broken.mov",
            "filename": "broken.mov",
            "status": "failed",
            "failed": True,
            "reason": "ffprobe failed: invalid data",
            "error_type": "MetadataError",
            "from_state": "running",
            "to_state": "failed",
            "attempts": 3,
        }
    )
    assert entry.level == LogLevel.ERROR
    assert entry.category == LogCategory.ERROR
    assert entry.error_type == "MetadataError"
    assert entry.error_message == "ffprobe failed: invalid data"
    assert "broken.mov" in entry.message
    assert "ffprobe failed" in entry.message


def test_build_item_entry_drops_none_details():
    entry = _build_item_entry(
        {
            "kind": "item",
            "session_id": 1,
            "item_id": "1",
            "filename": "a.jpg",
            "status": "imported",
            "media_id": None,
            "reason": None,
        }
    )
    assert "media_id" not in entry.details
    assert "reason" not in entry.details


def test_build_resume_entry_summarizes_counts():
    entry = _build_resume_entry(
        {
            "kind": "resume_summary",
            "session_id": 5,
            "done": 10,
            "pending": 3,
            "interrupted": 1,
            "failed": 2,
            "max_attempts": 3,
        }
    )
    assert entry.category == LogCategory.STATE_TRANSITION
    assert entry.session_id == 5
    assert entry.details["done"] == 10
    assert "完了=10" in entry.message
    assert "残り=3" in entry.message


def test_record_local_import_event_noop_without_logger(monkeypatch):
    # 監査ロガー未初期化なら例外を投げずに戻る。
    monkeypatch.setattr(
        "bounded_contexts.photonest.infrastructure.local_import.import_audit_recorder.get_audit_logger",
        lambda: None,
    )
    record_local_import_event({"kind": "item", "item_id": "1", "status": "imported"})


def test_record_local_import_event_logs_via_audit_logger(monkeypatch):
    logged = []

    class _FakeAuditLogger:
        def log(self, entry):
            logged.append(entry)

    monkeypatch.setattr(
        "bounded_contexts.photonest.infrastructure.local_import.import_audit_recorder.get_audit_logger",
        lambda: _FakeAuditLogger(),
    )
    record_local_import_event(
        {
            "kind": "item",
            "session_id": 1,
            "item_id": "8",
            "filename": "a.jpg",
            "status": "failed",
            "failed": True,
            "reason": "boom",
        }
    )
    assert len(logged) == 1
    assert logged[0].error_message == "boom"
    assert logged[0].level == LogLevel.ERROR
