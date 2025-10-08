"""ローカルインポートのキュー処理ロジック."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional

from core.models.photo_models import PickerSelection
from domain.local_import.logging import file_log_context
from domain.local_import.import_result import ImportTaskResult


class LocalImportQueueProcessor:
    """Selection キューを処理するアプリケーションサービス."""

    def __init__(
        self,
        *,
        db,
        logger,
        importer,
        cancel_requested,
    ) -> None:
        self._db = db
        self._logger = logger
        self._importer = importer
        self._cancel_requested = cancel_requested

    def enqueue(
        self,
        session,
        file_paths: Iterable[str],
        *,
        active_session_id: Optional[str],
        celery_task_id: Optional[str],
    ) -> int:
        if not session or not file_paths:
            return 0

        now = datetime.now(timezone.utc)
        paths = list(file_paths)
        existing: Dict[str, PickerSelection] = {}
        selections = (
            PickerSelection.query.filter(
                PickerSelection.session_id == session.id,
                PickerSelection.local_file_path.in_(paths),
            ).all()
        )
        for sel in selections:
            if sel.local_file_path:
                existing[sel.local_file_path] = sel

        enqueued = 0
        for file_path in paths:
            filename = os.path.basename(file_path)
            file_context = file_log_context(file_path, filename)
            selection = existing.get(file_path)
            if selection is None:
                selection = PickerSelection(
                    session_id=session.id,
                    google_media_id=None,
                    local_file_path=file_path,
                    local_filename=filename,
                    status="enqueued",
                    attempts=0,
                    enqueued_at=now,
                )
                self._db.session.add(selection)
                self._db.session.flush()
                enqueued += 1
                self._logger.info(
                    "local_import.selection.created",
                    "取り込み対象ファイルのSelectionを作成",
                    session_db_id=session.id,
                    **file_context,
                    selection_id=selection.id,
                    session_id=active_session_id,
                    celery_task_id=celery_task_id,
                )
            else:
                if selection.status in ("imported", "dup"):
                    continue
                selection.status = "enqueued"
                selection.enqueued_at = now
                selection.local_filename = filename
                selection.local_file_path = file_path
                enqueued += 1
                self._logger.info(
                    "local_import.selection.requeued",
                    "既存Selectionを再キュー",
                    session_db_id=session.id,
                    **file_context,
                    selection_id=selection.id,
                    session_id=active_session_id,
                    celery_task_id=celery_task_id,
                )

        self._logger.commit_with_error_logging(
            self._db,
            "local_import.selection.commit_failed",
            "Selectionの状態保存に失敗",
            session_id=active_session_id,
            celery_task_id=celery_task_id,
            session_db_id=getattr(session, "id", None),
            enqueued=enqueued,
        )
        return enqueued

    def pending_query(self, session):
        pending_statuses = ("pending", "enqueued", "running")
        return (
            PickerSelection.query.filter(
                PickerSelection.session_id == session.id,
                PickerSelection.status.in_(pending_statuses),
            )
            .order_by(PickerSelection.id)
        )

    def process(
        self,
        session,
        *,
        import_dir: str,
        originals_dir: str,
        result: ImportTaskResult,
        active_session_id: Optional[str],
        celery_task_id: Optional[str],
        task_instance=None,
        duplicate_regeneration: str = "regenerate",
    ) -> int:
        if not session:
            return 0

        selections = list(self.pending_query(session).all())
        total_files = len(selections)

        if self._cancel_requested(session, task_instance=task_instance):
            self._logger.info(
                "local_import.cancel.detected",
                "キャンセル要求を検知したため処理を中断",
                session_id=active_session_id,
                celery_task_id=celery_task_id,
            )
            result.mark_canceled()
            return 0

        if task_instance and total_files:
            task_instance.update_state(
                state="PROGRESS",
                meta={
                    "status": f"{total_files}個のファイルの取り込みを開始します",
                    "progress": 0,
                    "current": 0,
                    "total": total_files,
                    "message": "取り込み開始",
                },
            )

        canceled = False

        for index, selection in enumerate(selections, 1):
            file_path = selection.local_file_path
            filename = selection.local_filename or (
                os.path.basename(file_path) if file_path else f"selection_{selection.id}"
            )
            file_context = file_log_context(file_path, filename)
            display_file = file_context.get("file") or filename

            if self._cancel_requested(session, task_instance=task_instance):
                self._logger.info(
                    "local_import.cancel.pending_break",
                    "キャンセル要求のため残りの処理をスキップ",
                    session_id=active_session_id,
                    celery_task_id=celery_task_id,
                    processed=index - 1,
                    remaining=total_files - (index - 1),
                )
                canceled = True
                if task_instance and total_files:
                    task_instance.update_state(
                        state="PROGRESS",
                        meta={
                            "status": "キャンセル要求を受信しました",
                            "progress": int(((index - 1) / total_files) * 100)
                            if total_files
                            else 0,
                            "current": index - 1,
                            "total": total_files,
                            "message": "キャンセル処理中",
                        },
                    )
                break

            result.increment_processed()

            try:
                selection.status = "running"
                selection.started_at = datetime.now(timezone.utc)
                selection.error = None
                self._db.session.commit()
                self._logger.info(
                    "local_import.selection.running",
                    "Selectionを処理中に更新",
                    selection_id=selection.id,
                    **file_context,
                    session_id=active_session_id,
                    celery_task_id=celery_task_id,
                )
            except Exception as exc:
                self._db.session.rollback()
                self._logger.error(
                    "local_import.selection.running_update_failed",
                    "Selectionを処理中に更新できませんでした",
                    selection_id=getattr(selection, "id", None),
                    **file_context,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                    session_id=active_session_id,
                    celery_task_id=celery_task_id,
                )

            file_result = self._importer.import_file(
                file_path or "",
                import_dir,
                originals_dir,
                session_id=active_session_id,
                duplicate_regeneration=duplicate_regeneration,
            )

            result_status = file_result.get("status")
            detail_status = "success" if file_result["success"] else result_status or "failed"
            detail = {
                "file": display_file,
                "status": detail_status,
                "reason": file_result["reason"],
                "media_id": file_result.get("media_id"),
            }
            basename = file_context.get("basename")
            if basename and basename != detail["file"]:
                detail["basename"] = basename
            result.append_detail(detail)

            post_process_result = file_result.get("post_process")
            if isinstance(post_process_result, dict):
                thumb_result = post_process_result.get("thumbnails")
                if isinstance(thumb_result, dict):
                    thumb_detail = {
                        "ok": thumb_result.get("ok"),
                        "status": "error"
                        if thumb_result.get("ok") is False
                        else (
                            "progress"
                            if thumb_result.get("retry_scheduled")
                            else "completed"
                        ),
                        "generated": thumb_result.get("generated"),
                        "skipped": thumb_result.get("skipped"),
                        "retryScheduled": bool(thumb_result.get("retry_scheduled")),
                        "notes": thumb_result.get("notes"),
                    }
                    retry_details = thumb_result.get("retry_details")
                    if isinstance(retry_details, dict):
                        thumb_detail["retryDetails"] = retry_details
                    detail["thumbnail"] = thumb_detail
                    self._record_thumbnail_result(
                        result,
                        media_id=file_result.get("media_id"),
                        thumb_result=thumb_result,
                    )

            try:
                if file_result["success"]:
                    selection.status = "imported"
                    selection.completed_at = datetime.now(timezone.utc)
                    selection.google_media_id = file_result.get("media_google_id")
                    selection.media_id = file_result.get("media_id")
                elif result_status in {"duplicate", "duplicate_refreshed"}:
                    selection.status = "dup"
                    existing_google_id = file_result.get("media_google_id")
                    if existing_google_id:
                        selection.google_media_id = existing_google_id
                else:
                    selection.status = "failed"
                    selection.error = file_result.get("reason")
                self._db.session.commit()
            except Exception as exc:
                self._db.session.rollback()
                self._logger.error(
                    "local_import.selection.finalize_failed",
                    "Selection結果の保存に失敗",
                    selection_id=getattr(selection, "id", None),
                    **file_context,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                    session_id=active_session_id,
                    celery_task_id=celery_task_id,
                )

            if file_result["success"]:
                result.increment_success()
            else:
                if result_status in {"skipped", "duplicate", "duplicate_refreshed"}:
                    result.increment_skipped()
                else:
                    result.increment_failed()
                    reason = detail.get("reason") or file_result.get("reason")
                    if reason:
                        if detail.get("file"):
                            result.add_error(f"{detail['file']}: {reason}")
                        else:
                            result.add_error(str(reason))

            if task_instance and total_files:
                task_instance.update_state(
                    state="PROGRESS",
                    meta={
                        "status": f"{index}/{total_files} ファイルを処理済み",
                        "progress": int((index / total_files) * 100),
                        "current": index,
                        "total": total_files,
                        "message": "取り込み中",
                    },
                )

        if canceled:
            result.mark_canceled()

        return total_files

    def _record_thumbnail_result(
        self,
        aggregate: ImportTaskResult,
        *,
        media_id: Optional[int],
        thumb_result: Dict[str, Any],
    ) -> None:
        if media_id is None or not isinstance(thumb_result, dict):
            return

        entry: Dict[str, Any] = {
            "mediaId": media_id,
            "media_id": media_id,
            "ok": thumb_result.get("ok"),
            "notes": thumb_result.get("notes"),
            "generated": thumb_result.get("generated"),
            "skipped": thumb_result.get("skipped"),
            "retry_scheduled": bool(thumb_result.get("retry_scheduled")),
        }

        retry_details = thumb_result.get("retry_details")
        if isinstance(retry_details, dict):
            entry["retry_details"] = retry_details

        ok_flag = thumb_result.get("ok")
        if ok_flag is False:
            entry["status"] = "error"
        elif entry["retry_scheduled"]:
            entry["status"] = "progress"
        else:
            entry["status"] = "completed"

        aggregate.add_thumbnail_record(entry)
