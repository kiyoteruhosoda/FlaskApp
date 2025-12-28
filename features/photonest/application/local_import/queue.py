"""ローカルインポートのキュー処理ロジック."""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional

from core.models.photo_models import (
    Media,
    MediaItem,
    PhotoMetadata,
    PickerSelection,
    VideoMetadata,
)
from features.photonest.domain.local_import.logging import file_log_context
from features.photonest.domain.local_import.import_result import ImportTaskResult


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

        if isinstance(result, dict):
            result = ImportTaskResult.from_dict(result)

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
        duplicate_skip_forced = False

        for index, selection in enumerate(selections, 1):
            file_path = selection.local_file_path
            filename = selection.local_filename or (
                os.path.basename(file_path) if file_path else f"selection_{selection.id}"
            )
            file_task_id = str(uuid.uuid4())
            file_context = file_log_context(file_path, filename, file_task_id=file_task_id)
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
                selection.error_msg = None
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

            effective_duplicate_regen = (
                "skip" if duplicate_skip_forced else duplicate_regeneration
            )

            import_callable = getattr(self._importer, "import_file", self._importer)
            file_result = import_callable(
                file_path or "",
                import_dir,
                originals_dir,
                session_id=active_session_id,
                duplicate_regeneration=effective_duplicate_regen,
                file_task_id=file_task_id,
            )

            result_status = file_result.get("status")

            post_process_result = file_result.get("post_process")
            thumbnail_failed = False
            thumbnail_error_message = file_result.get("thumbnail_regen_error")

            if isinstance(post_process_result, dict):
                thumb_result = post_process_result.get("thumbnails")
            else:
                thumb_result = None

            detail_status = "success" if file_result["success"] else result_status or "failed"
            detail = {
                "file": display_file,
                "status": detail_status,
                "reason": file_result["reason"],
                "media_id": file_result.get("media_id"),
            }
            if file_task_id:
                detail["fileTaskId"] = file_task_id
            basename = file_context.get("basename")
            if basename and basename != detail["file"]:
                detail["basename"] = basename

            thumb_detail = None

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

                if thumb_detail["ok"] is False:
                    thumbnail_failed = True
                    if not thumbnail_error_message:
                        thumbnail_error_message = thumb_detail.get("notes")

            if thumbnail_failed:
                detail["status"] = "failed"
                if thumbnail_error_message:
                    regen_message = str(thumbnail_error_message)
                    if regen_message not in str(detail["reason"]):
                        detail["reason"] = f"{detail['reason']} (サムネイル再生成失敗: {regen_message})"

            result.append_detail(detail)

            try:
                if file_result["success"]:
                    selection.status = "imported"
                    selection.finished_at = datetime.now(timezone.utc)
                    media_identifier = file_result.get("media_id")
                    self._assign_google_media_id(
                        selection,
                        file_result.get("media_google_id"),
                        file_context,
                        media_id=media_identifier,
                        resequence_on_conflict=True,
                    )
                    if media_identifier is not None:
                        selection.media_id = media_identifier
                elif (
                    result_status in {"duplicate", "duplicate_refreshed"}
                    and not thumbnail_failed
                ):
                    selection.status = "dup"
                    existing_google_id = file_result.get("media_google_id")
                    if existing_google_id:
                        self._assign_google_media_id(
                            selection,
                            existing_google_id,
                            file_context,
                            media_id=file_result.get("media_id"),
                        )
                    existing_media_id = file_result.get("media_id")
                    if existing_media_id is not None:
                        selection.media_id = existing_media_id
                    if selection.finished_at is None:
                        selection.finished_at = datetime.now(timezone.utc)
                else:
                    selection.status = "failed"
                    selection.error_msg = detail["reason"]
                    selection.finished_at = datetime.now(timezone.utc)
                    existing_google_id = file_result.get("media_google_id")
                    if existing_google_id:
                        self._assign_google_media_id(
                            selection,
                            existing_google_id,
                            file_context,
                            media_id=file_result.get("media_id"),
                        )
                    media_identifier = file_result.get("media_id")
                    if media_identifier is not None:
                        selection.media_id = media_identifier
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
                if (
                    result_status in {"skipped", "duplicate", "duplicate_refreshed"}
                    and not thumbnail_failed
                ):
                    result.increment_skipped()
                else:
                    result.increment_failed()
                    reason = detail.get("reason") or file_result.get("reason")
                    if reason:
                        if detail.get("file"):
                            result.add_error(f"{detail['file']}: {reason}")
                        else:
                            result.add_error(str(reason))

            if result_status in {"duplicate", "duplicate_refreshed"}:
                duplicate_skip_forced = True

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

    def _assign_google_media_id(
        self,
        selection: PickerSelection,
        google_media_id: Optional[str],
        file_context: Optional[Dict[str, Any]] = None,
        *,
        media_id: Optional[int] = None,
        resequence_on_conflict: bool = False,
    ) -> bool:
        """Assign ``google_media_id`` while avoiding unique constraint conflicts."""

        if not google_media_id:
            selection.google_media_id = None
            return True

        if selection.google_media_id == google_media_id:
            return True

        conflict_id = (
            self._db.session.query(PickerSelection.id)
            .filter(
                PickerSelection.session_id == selection.session_id,
                PickerSelection.google_media_id == google_media_id,
                PickerSelection.id != selection.id,
            )
            .scalar()
        )

        if conflict_id is not None:
            if resequence_on_conflict:
                resequenced_id = self._resequence_google_media_id(
                    selection,
                    google_media_id,
                    media_id,
                    file_context,
                )
                if resequenced_id:
                    selection.google_media_id = resequenced_id
                    return True
            context = dict(file_context or {})
            self._logger.warning(
                "local_import.selection.google_id_conflict",
                "Selectionの google_media_id を設定できません（同一セッション内で重複）",
                selection_id=getattr(selection, "id", None),
                google_media_id=google_media_id,
                conflicting_selection_id=conflict_id,
                **context,
            )
            return False

        selection.google_media_id = google_media_id
        return True

    def _resequence_google_media_id(
        self,
        selection: PickerSelection,
        google_media_id: str,
        media_id: Optional[int],
        file_context: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """Generate a new google_media_id and update related records.

        ``google_media_id`` が既存 Selection と衝突した場合でも、新規取り込み結果を
        失わないように再採番を行う。関連する ``Media`` / ``MediaItem`` が存在する場合は
        それらの ID も整合するよう更新する。
        """

        context = dict(file_context or {})
        new_google_id = self._generate_unique_google_media_id(selection, google_media_id)

        # Update Media if the current import created one.
        if media_id is not None:
            media_obj = self._db.session.get(Media, media_id)
            if media_obj and media_obj.google_media_id == google_media_id:
                media_obj.google_media_id = new_google_id
            elif media_obj and media_obj.google_media_id not in {None, google_media_id}:
                self._logger.warning(
                    "local_import.selection.resequence_media_mismatch",
                    "Media の google_media_id が取り込み結果と一致しないため再採番をスキップ",
                    selection_id=getattr(selection, "id", None),
                    media_id=media_id,
                    current_media_google_id=media_obj.google_media_id,
                    expected_google_media_id=google_media_id,
                    candidate_google_media_id=new_google_id,
                    **context,
                )
                return None

        # Clone MediaItem metadata when available to keep PickerSelection joins working.
        if not self._ensure_media_item_resequenced(
            original_google_id=google_media_id,
            new_google_id=new_google_id,
            selection=selection,
            context=context,
        ):
            return None

        self._logger.info(
            "local_import.selection.google_id_resequenced",
            "google_media_id を再採番して更新しました",
            selection_id=getattr(selection, "id", None),
            original_google_media_id=google_media_id,
            resequenced_google_media_id=new_google_id,
            media_id=media_id,
            **context,
        )
        return new_google_id

    def _generate_unique_google_media_id(
        self, selection: PickerSelection, base_id: str
    ) -> str:
        suffix = uuid.uuid4().hex[:12]
        # 255 文字制限を超えないようにベースを切り詰める
        max_base_length = 255 - len(suffix) - 1
        truncated_base = base_id[:max_base_length] if len(base_id) > max_base_length else base_id
        candidate = f"{truncated_base}-{suffix}"

        while (
            self._db.session.query(PickerSelection.id)
            .filter(
                PickerSelection.session_id == selection.session_id,
                PickerSelection.google_media_id == candidate,
            )
            .first()
            is not None
            or self._db.session.get(MediaItem, candidate) is not None
        ):
            suffix = uuid.uuid4().hex[:12]
            candidate = f"{truncated_base}-{suffix}"
        return candidate

    def _ensure_media_item_resequenced(
        self,
        *,
        original_google_id: str,
        new_google_id: str,
        selection: PickerSelection,
        context: Dict[str, Any],
    ) -> bool:
        media_item = self._db.session.get(MediaItem, original_google_id)
        if media_item is None:
            # MediaItem が存在しない場合は特に更新不要
            return True

        if media_item.picker_selections:
            # 他のSelectionが既に参照している場合は複製して再採番する
            cloned_item = self._clone_media_item(media_item, new_google_id)
            if cloned_item is None:
                self._logger.error(
                    "local_import.selection.media_item_clone_failed",
                    "MediaItem の複製に失敗したため再採番できません",
                    original_google_media_id=original_google_id,
                    resequenced_google_media_id=new_google_id,
                    **context,
                )
                return False
            selection.media_item = cloned_item
            return True

        # 他のSelectionから参照されていない場合はそのままIDを差し替える
        media_item.id = new_google_id
        selection.media_item = media_item
        return True

    def _clone_media_item(
        self,
        media_item: MediaItem,
        new_google_id: str,
    ) -> Optional[MediaItem]:
        """Clone a ``MediaItem`` with its metadata for resequencing."""

        cloned_item = MediaItem(
            id=new_google_id,
            type=media_item.type,
            mime_type=media_item.mime_type,
            filename=media_item.filename,
            width=media_item.width,
            height=media_item.height,
            camera_make=media_item.camera_make,
            camera_model=media_item.camera_model,
        )

        if media_item.photo_metadata is not None:
            photo = PhotoMetadata(
                focal_length=media_item.photo_metadata.focal_length,
                aperture_f_number=media_item.photo_metadata.aperture_f_number,
                iso_equivalent=media_item.photo_metadata.iso_equivalent,
                exposure_time=media_item.photo_metadata.exposure_time,
            )
            cloned_item.photo_metadata = photo
            self._db.session.add(photo)

        if media_item.video_metadata is not None:
            video = VideoMetadata(
                fps=media_item.video_metadata.fps,
                processing_status=media_item.video_metadata.processing_status,
            )
            cloned_item.video_metadata = video
            self._db.session.add(video)

        self._db.session.add(cloned_item)
        return cloned_item
