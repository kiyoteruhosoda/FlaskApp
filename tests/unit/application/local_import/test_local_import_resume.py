"""ローカルインポートのチェックポイント/再開・リトライ上限の単体テスト。"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from core.db import db

pytestmark = pytest.mark.integration

from bounded_contexts.photonest.application.local_import.queue import (
    LocalImportQueueProcessor,
)
from bounded_contexts.photonest.domain.local_import.import_result import ImportTaskResult
from core.models.photo_models import PickerSelection
from core.models.picker_session import PickerSession


class _RecordingAuditRecorder:
    """audit_recorder の呼び出しを記録するテスト用ダブル。"""

    def __init__(self):
        self.records = []

    def __call__(self, record):
        self.records.append(record)

    def of_kind(self, kind):
        return [r for r in self.records if r.get("kind") == kind]


def _make_session():
    session = PickerSession(status="pending")
    db.session.add(session)
    db.session.commit()
    return session


def _add_selection(session, path, *, status, attempts=0):
    selection = PickerSelection(
        session_id=session.id,
        local_file_path=path,
        local_filename=path.split("/")[-1],
        status=status,
        attempts=attempts,
    )
    db.session.add(selection)
    db.session.commit()
    return selection


@pytest.mark.usefixtures("app_context")
def test_enqueue_skips_exhausted_failed_selection():
    processor = LocalImportQueueProcessor(
        db=db,
        logger=MagicMock(),
        importer=None,
        cancel_requested=lambda *a, **k: False,
        max_attempts=3,
    )
    session = _make_session()
    exhausted = _add_selection(
        session, "/import/poison.jpg", status="failed", attempts=3
    )
    retryable = _add_selection(
        session, "/import/retry.jpg", status="failed", attempts=1
    )

    enqueued = processor.enqueue(
        session,
        ["/import/poison.jpg", "/import/retry.jpg"],
        active_session_id=session.session_id,
        celery_task_id=None,
    )

    db.session.commit()
    assert enqueued == 1
    assert exhausted.status == "failed"  # 上限到達は再キューされない
    assert retryable.status == "enqueued"  # 上限未満は再開対象


@pytest.mark.usefixtures("app_context")
def test_enqueue_unlimited_when_max_attempts_zero():
    processor = LocalImportQueueProcessor(
        db=db,
        logger=MagicMock(),
        importer=None,
        cancel_requested=lambda *a, **k: False,
        max_attempts=0,
    )
    session = _make_session()
    failed = _add_selection(session, "/import/a.jpg", status="failed", attempts=99)

    enqueued = processor.enqueue(
        session,
        ["/import/a.jpg"],
        active_session_id=session.session_id,
        celery_task_id=None,
    )

    db.session.commit()
    assert enqueued == 1
    assert failed.status == "enqueued"


@pytest.mark.usefixtures("app_context")
def test_enqueue_skips_imported_and_dup():
    processor = LocalImportQueueProcessor(
        db=db,
        logger=MagicMock(),
        importer=None,
        cancel_requested=lambda *a, **k: False,
        max_attempts=3,
    )
    session = _make_session()
    imported = _add_selection(session, "/import/done.jpg", status="imported")
    dup = _add_selection(session, "/import/dup.jpg", status="dup")

    enqueued = processor.enqueue(
        session,
        ["/import/done.jpg", "/import/dup.jpg"],
        active_session_id=session.session_id,
        celery_task_id=None,
    )

    db.session.commit()
    assert enqueued == 0
    assert imported.status == "imported"
    assert dup.status == "dup"


@pytest.mark.usefixtures("app_context")
def test_process_increments_attempts_and_records_items():
    def importer(file_path, import_dir, originals_dir, **kwargs):
        return {"success": True, "status": "imported", "reason": None, "media_id": None}

    recorder = _RecordingAuditRecorder()
    processor = LocalImportQueueProcessor(
        db=db,
        logger=MagicMock(),
        importer=importer,
        cancel_requested=lambda *a, **k: False,
        max_attempts=3,
        audit_recorder=recorder,
    )
    session = _make_session()
    sel = _add_selection(session, "/import/a.jpg", status="enqueued", attempts=0)
    result = ImportTaskResult(session_id=session.session_id)

    processor.process(
        session,
        import_dir="/import",
        originals_dir="/orig",
        result=result,
        active_session_id=session.session_id,
        celery_task_id=None,
    )

    db.session.refresh(sel)
    assert sel.status == "imported"
    assert sel.attempts == 1
    assert sel.lock_heartbeat_at is None  # 終端でハートビート解放
    # ファイル単位の監査レコードが記録される
    item_records = recorder.of_kind("item")
    assert len(item_records) == 1
    assert item_records[0]["status"] == "imported"
    assert item_records[0]["item_id"] == str(sel.id)
    assert item_records[0]["from_state"] == "running"
    assert item_records[0]["to_state"] == "imported"


@pytest.mark.usefixtures("app_context")
def test_process_fails_exhausted_running_leftover():
    # 前回クラッシュで running のまま残り、既に上限到達しているケース。
    calls = []

    def importer(file_path, import_dir, originals_dir, **kwargs):
        calls.append(file_path)
        return {"success": True, "status": "imported", "reason": None}

    processor = LocalImportQueueProcessor(
        db=db,
        logger=MagicMock(),
        importer=importer,
        cancel_requested=lambda *a, **k: False,
        max_attempts=3,
    )
    session = _make_session()
    sel = _add_selection(session, "/import/stuck.jpg", status="running", attempts=3)
    result = ImportTaskResult(session_id=session.session_id)

    processor.process(
        session,
        import_dir="/import",
        originals_dir="/orig",
        result=result,
        active_session_id=session.session_id,
        celery_task_id=None,
    )

    db.session.refresh(sel)
    assert sel.status == "failed"
    assert calls == []  # importer は呼ばれない
    assert result.failed == 1
