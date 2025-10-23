from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
import zipfile

import pytest

from core.storage_service import LocalFilesystemStorageService
from features.photonest.application.local_import.file_importer import LocalImportFileImporter, PlaybackFailurePolicy
from features.photonest.application.local_import.scanner import ImportDirectoryScanner
from features.photonest.application.local_import.use_case import LocalImportUseCase
from features.photonest.application.local_import.logger import LocalImportTaskLogger
from features.photonest.application.local_import.queue import LocalImportQueueProcessor
from features.photonest.application.local_import import logger as logger_module
from features.photonest.domain.local_import.import_result import ImportTaskResult
from features.photonest.domain.local_import.zip_archive import ZipArchiveService


class DummyAnalysis:
    def __init__(self, file_hash: str, file_size: int, *, is_video: bool = False):
        self.file_hash = file_hash
        self.file_size = file_size
        self.is_video = is_video
        self.destination_filename = "sample.jpg"
        self.relative_path = "sample/sample.jpg"


class DummyMedia:
    def __init__(self):
        self.id = 1
        self.google_media_id = 2
        self.local_rel_path = "existing/sample.jpg"
        self.filename = "sample.jpg"
        self.is_video = False


def _build_importer(tmp_path, logger=None):
    db = SimpleNamespace(session=MagicMock())
    duplicate_checker = MagicMock(return_value=None)
    metadata_refresher = MagicMock()
    post_process_service = MagicMock(return_value={})
    directory_resolver = MagicMock(return_value=str(tmp_path))
    analysis_service = MagicMock(side_effect=lambda path: DummyAnalysis("hash", 10))
    thumbnail_regenerator = MagicMock(return_value=(True, None))
    logger = logger or MagicMock()

    source_storage = LocalFilesystemStorageService()
    destination_storage = LocalFilesystemStorageService()

    importer = LocalImportFileImporter(
        db=db,
        logger=logger,
        duplicate_checker=duplicate_checker,
        metadata_refresher=metadata_refresher,
        post_process_service=post_process_service,
        post_process_logger=MagicMock(),
        directory_resolver=directory_resolver,
        analysis_service=analysis_service,
        thumbnail_regenerator=thumbnail_regenerator,
        supported_extensions={".jpg"},
        source_storage=source_storage,
        destination_storage=destination_storage,
        playback_policy=PlaybackFailurePolicy(()),
    )
    return (
        importer,
        db,
        duplicate_checker,
        metadata_refresher,
        post_process_service,
        directory_resolver,
        analysis_service,
        thumbnail_regenerator,
    )


def test_file_importer_missing_file_returns_missing(tmp_path):
    importer, db, duplicate_checker, *_ = _build_importer(tmp_path)

    result = importer.import_file(
        file_path=str(tmp_path / "missing.jpg"),
        import_dir=str(tmp_path),
        originals_dir=str(tmp_path),
    )

    assert result["status"] == "missing"
    duplicate_checker.assert_not_called()
    db.session.commit.assert_not_called()


def test_file_importer_duplicate_refreshes_metadata(tmp_path):
    importer, db, duplicate_checker, metadata_refresher, *_ = _build_importer(tmp_path)

    existing_media = DummyMedia()
    duplicate_checker.return_value = existing_media
    metadata_refresher.return_value = True

    source = tmp_path / "source.jpg"
    source.write_bytes(b"data")

    result = importer.import_file(
        file_path=str(source),
        import_dir=str(tmp_path),
        originals_dir=str(tmp_path),
    )

    assert result["status"] == "duplicate_refreshed"
    metadata_refresher.assert_called_once()
    assert not source.exists()


def test_validate_playback_recoverable_without_session(tmp_path):
    class DummySession:
        def refresh(self, obj):
            return None

    db = SimpleNamespace(session=DummySession())
    importer = LocalImportFileImporter(
        db=db,
        logger=MagicMock(),
        duplicate_checker=MagicMock(),
        metadata_refresher=MagicMock(),
        post_process_service=MagicMock(),
        post_process_logger=MagicMock(),
        directory_resolver=MagicMock(return_value=str(tmp_path)),
        analysis_service=MagicMock(),
        thumbnail_regenerator=MagicMock(return_value=(True, None)),
        supported_extensions={".mp4"},
        source_storage=LocalFilesystemStorageService(),
        destination_storage=LocalFilesystemStorageService(),
    )

    importer._logger = MagicMock()

    media = SimpleNamespace(id=99, has_playback=False)
    post_process_result = {
        "playback": {
            "ok": False,
            "note": "ffmpeg_error",
            "error": "width not divisible by 2 (809x1080)",
        }
    }
    outcome = SimpleNamespace(details={})
    file_context = {"basename": "video.mp4"}

    importer._validate_playback(media, post_process_result, outcome, file_context, None)

    importer._logger.warning.assert_called_once()
    warnings = outcome.details.get("warnings", [])
    assert "playback_skipped:ffmpeg_error" in warnings
    assert any(w.startswith("playback_error:") for w in warnings)
    assert outcome.details["playback_error"].startswith("width not divisible")
    assert outcome.details["playback_note"] == "ffmpeg_error"


def test_directory_scanner_collects_supported_files_and_zip(tmp_path):
    logger = MagicMock()
    zip_service = MagicMock()
    zip_service.extract.return_value = [str(tmp_path / "from_zip.jpg")]
    scanner = ImportDirectoryScanner(
        logger=logger,
        zip_service=zip_service,
        supported_extensions={".jpg"},
        storage_service=LocalFilesystemStorageService(),
    )

    supported = tmp_path / "image.jpg"
    supported.write_bytes(b"data")
    zip_file = tmp_path / "archive.zip"
    zip_file.write_bytes(b"zip")

    result = scanner.scan(str(tmp_path), session_id="S1")

    assert str(supported) in result
    assert str(tmp_path / "from_zip.jpg") in result
    zip_service.extract.assert_called_once_with(str(zip_file), session_id="S1")


def test_zip_archive_service_extracts_and_cleans(tmp_path):
    storage = LocalFilesystemStorageService()
    storage.set_defaults("LOCAL_IMPORT_DIR", (str(tmp_path / "import_base"),))

    def _info(*args, **kwargs):
        return None

    def _warning(*args, **kwargs):
        return None

    def _error(*args, **kwargs):
        return None

    service = ZipArchiveService(
        _info,
        _warning,
        _error,
        supported_extensions={".jpg"},
        storage_service=storage,
    )

    zip_file = tmp_path / "source.zip"
    with zipfile.ZipFile(zip_file, "w") as archive:
        archive.writestr("nested/photo.jpg", b"data")

    extracted = service.extract(str(zip_file))

    assert extracted
    extracted_path = Path(extracted[0])
    assert extracted_path.exists()
    assert extracted_path.suffix == ".jpg"
    assert str(extracted_path).startswith(
        str(tmp_path / "import_base" / "_zip")
    )
    assert not zip_file.exists()

    service.cleanup()
    assert not extracted_path.parent.exists()


def test_local_import_use_case_handles_missing_directory(tmp_path):
    class DummySession:
        def __init__(self):
            self.add = MagicMock()
            self.commit = MagicMock()
            self.rollback = MagicMock()

    db = SimpleNamespace(session=DummySession())
    logger = MagicMock()
    session_service = MagicMock()
    session_service.set_progress = MagicMock()
    session_service.cancel_requested.return_value = False
    scanner = MagicMock()
    queue_processor = MagicMock()
    use_case = LocalImportUseCase(
        db=db,
        logger=logger,
        session_service=session_service,
        scanner=scanner,
        queue_processor=queue_processor,
    )

    result = use_case.execute(
        session_id=None,
        import_dir=str(tmp_path / "missing"),
        originals_dir=str(tmp_path / "originals"),
        celery_task_id="ctid",
    )

    assert result["ok"] is False
    assert any("取り込みディレクトリが存在しません" in err for err in result["errors"])
    scanner.scan.assert_not_called()
    session_service.set_progress.assert_called()


def test_task_logger_error_logs_to_celery_and_task_logger(monkeypatch):
    task_logger = MagicMock()
    celery_logger = MagicMock()
    recorded = {}

    def fake_compose(message, payload, status):
        recorded["composed"] = (message, payload, status)
        return f"{message}|{status}"

    def fake_log_task_error(logger, message, **kwargs):
        recorded["log_task_error"] = (logger, message, kwargs)

    monkeypatch.setattr(logger_module, "compose_message", fake_compose)
    monkeypatch.setattr(logger_module, "log_task_error", fake_log_task_error)

    task_logger_instance = LocalImportTaskLogger(task_logger, celery_logger)

    task_logger_instance.error(
        "event.id",
        "エラー発生",
        session_id="S1",
        exc_info=True,
        status="custom",
        detail="x",
    )

    assert recorded["composed"] == ("エラー発生", {"detail": "x", "session_id": "S1"}, "custom")
    assert recorded["log_task_error"][0] is task_logger
    assert recorded["log_task_error"][1] == "エラー発生|custom"
    assert recorded["log_task_error"][2]["event"] == "event.id"
    celery_logger.error.assert_called_once()
    assert celery_logger.error.call_args.kwargs["extra"]["session_id"] == "S1"
    assert celery_logger.error.call_args.kwargs["exc_info"] is True


def test_queue_processor_handles_cancel_request(monkeypatch):
    db = SimpleNamespace(session=MagicMock())
    logger = MagicMock()
    importer = MagicMock()
    cancel_calls = iter([False, True])

    def cancel_requested(session, task_instance=None):
        return next(cancel_calls, True)

    session = SimpleNamespace(id=1)
    selection = SimpleNamespace(
        id=2,
        local_file_path="/tmp/file.jpg",
        local_filename="file.jpg",
        status="enqueued",
        attempts=0,
        started_at=None,
        error=None,
        google_media_id=None,
        media_id=None,
        completed_at=None,
    )

    class DummyQuery:
        def all(self):
            return [selection]

    processor = LocalImportQueueProcessor(
        db=db,
        logger=logger,
        importer=importer,
        cancel_requested=cancel_requested,
    )

    monkeypatch.setattr(processor, "pending_query", lambda _session: DummyQuery())

    result = ImportTaskResult()

    processor.process(
        session,
        import_dir="/import",
        originals_dir="/orig",
        result=result,
        active_session_id="S1",
        celery_task_id="C1",
    )

    importer.import_file.assert_not_called()
    assert result.processed == 0
    assert result.canceled is True


def test_queue_processor_logs_commit_error(monkeypatch):
    db_session = MagicMock()
    db = SimpleNamespace(session=db_session)
    logger = MagicMock()
    importer = MagicMock(
        import_file=MagicMock(
            return_value={
                "success": True,
                "reason": "",
                "media_id": 10,
                "media_google_id": 11,
            }
        )
    )

    cancel_requested = MagicMock(return_value=False)

    session = SimpleNamespace(id=1)
    selection = SimpleNamespace(
        id=3,
        local_file_path="/tmp/file.jpg",
        local_filename="file.jpg",
        status="enqueued",
        attempts=0,
        started_at=None,
        error=None,
        google_media_id=None,
        media_id=None,
        completed_at=None,
    )

    class DummyQuery:
        def all(self):
            return [selection]

    db_session.commit.side_effect = [None, RuntimeError("boom")]

    processor = LocalImportQueueProcessor(
        db=db,
        logger=logger,
        importer=importer,
        cancel_requested=cancel_requested,
    )
    monkeypatch.setattr(processor, "pending_query", lambda _session: DummyQuery())

    result = ImportTaskResult()

    processor.process(
        session,
        import_dir="/import",
        originals_dir="/orig",
        result=result,
        active_session_id="S1",
        celery_task_id="C1",
    )

    assert result.success == 1
    assert result.processed == 1
    db_session.rollback.assert_called_once()
    logger.error.assert_any_call(
        "local_import.selection.finalize_failed",
        "Selection結果の保存に失敗",
        selection_id=selection.id,
        file="/tmp/file.jpg",
        file_path="/tmp/file.jpg",
        basename="file.jpg",
        session_id="S1",
        celery_task_id="C1",
        error_type="RuntimeError",
        error_message="boom",
    )


def test_queue_processor_marks_failure_on_thumbnail_regen_error(monkeypatch):
    db_session = MagicMock()
    db_session.commit.return_value = None
    db = SimpleNamespace(session=db_session)
    logger = MagicMock()

    importer_result = {
        "success": False,
        "status": "duplicate",
        "reason": "重複ファイル (既存ID: 101)",
        "media_id": 101,
        "media_google_id": "google-media",
        "thumbnail_regen_error": "Error opening output files: Invalid argument",
        "post_process": {
            "thumbnails": {
                "ok": False,
                "generated": [],
                "skipped": [],
                "retry_scheduled": False,
                "notes": "Error opening output files: Invalid argument",
            }
        },
    }

    importer = MagicMock(import_file=MagicMock(return_value=importer_result))
    cancel_requested = MagicMock(return_value=False)

    session = SimpleNamespace(id=1)
    selection = SimpleNamespace(
        id=99,
        local_file_path="/tmp/video.mp4",
        local_filename="video.mp4",
        status="enqueued",
        attempts=0,
        started_at=None,
        error=None,
        google_media_id=None,
        media_id=None,
        completed_at=None,
    )

    class DummyQuery:
        def all(self):
            return [selection]

    processor = LocalImportQueueProcessor(
        db=db,
        logger=logger,
        importer=importer,
        cancel_requested=cancel_requested,
    )

    monkeypatch.setattr(processor, "pending_query", lambda _session: DummyQuery())

    result = ImportTaskResult()

    processor.process(
        session,
        import_dir="/import",
        originals_dir="/orig",
        result=result,
        active_session_id="session-1",
        celery_task_id="celery-1",
    )

    assert selection.status == "failed"
    assert selection.error and "サムネイル再生成失敗" in selection.error
    assert selection.google_media_id == "google-media"
    assert selection.media_id == 101

    assert result.failed == 1
    assert result.skipped == 0
    assert result.ok is False
    assert result.details, "詳細結果が記録されていません"
    detail = result.details[0]
    assert detail["status"] == "failed"
    assert "サムネイル再生成失敗" in detail["reason"]
    assert detail.get("thumbnail", {}).get("status") == "error"
