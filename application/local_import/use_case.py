"""ローカルインポート Celery タスクのアプリケーション層実装."""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from core.models.picker_session import PickerSession
from core.models.photo_models import PickerSelection

from .results import build_thumbnail_task_snapshot


class LocalImportUseCase:
    """ローカルインポート処理を調整するユースケース."""

    def __init__(
        self,
        *,
        db,
        logger,
        session_service,
        scanner,
        queue_processor,
    ) -> None:
        self._db = db
        self._logger = logger
        self._session_service = session_service
        self._scanner = scanner
        self._queue_processor = queue_processor

    def execute(
        self,
        *,
        session_id: Optional[str],
        import_dir: str,
        originals_dir: str,
        celery_task_id: Optional[str] = None,
        task_instance=None,
    ) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "ok": True,
            "errors": [],
            "processed": 0,
            "success": 0,
            "skipped": 0,
            "failed": 0,
            "details": [],
            "session_id": session_id,
            "celery_task_id": celery_task_id,
            "canceled": False,
        }

        session = self._load_or_create_session(session_id, result, celery_task_id)
        if session is None and not result["ok"]:
            return result

        active_session_id = session.session_id if session else session_id

        self._set_progress(
            session,
            status="expanding",
            stage="expanding",
            celery_task_id=celery_task_id,
            stats_updates={
                "total": 0,
                "success": 0,
                "skipped": 0,
                "failed": 0,
            },
        )

        self._logger.info(
            "local_import.task.start",
            "ローカルインポートタスクを開始",
            session_id=active_session_id,
            import_dir=import_dir,
            originals_dir=originals_dir,
            celery_task_id=celery_task_id,
            status="running",
        )

        try:
            if not self._ensure_directory_exists(
                import_dir,
                result,
                session,
                active_session_id,
                celery_task_id,
                reason_key="import_dir_missing",
                log_event="local_import.dir.import_missing",
                log_message="取り込み元デレクトリが存在しません",
                error_message=lambda path: f"取り込みディレクトリが存在しません: {path}",
                log_details={"import_dir": import_dir},
            ):
                return result

            if not self._ensure_directory_exists(
                originals_dir,
                result,
                session,
                active_session_id,
                celery_task_id,
                reason_key="destination_dir_missing",
                log_event="local_import.dir.destination_missing",
                log_message="保存先ディレクトリが存在しません",
                error_message=lambda path: f"保存先ディレクトリが存在しません: {path}",
                log_details={"originals_dir": originals_dir},
            ):
                return result

            files = self._scanner.scan(import_dir, session_id=active_session_id)
            self._logger.info(
                "local_import.scan.complete",
                "取り込み対象ファイルのスキャンが完了",
                import_dir=import_dir,
                total=len(files),
                samples=files[:5],
                session_id=active_session_id,
                celery_task_id=celery_task_id,
                status="scanned",
            )

            total_files = len(files)
            if total_files == 0:
                self._handle_no_files(
                    result,
                    session,
                    active_session_id,
                    celery_task_id,
                    import_dir,
                )
                return result

            enqueued_count = self._queue_processor.enqueue(
                session,
                files,
                active_session_id=active_session_id,
                celery_task_id=celery_task_id,
            )

            pending_total = 0
            if session:
                pending_total = self._queue_processor.pending_query(session).count()

            self._set_progress(
                session,
                status="processing",
                stage="progress",
                celery_task_id=celery_task_id,
                stats_updates={
                    "total": pending_total,
                    "success": 0,
                    "skipped": 0,
                    "failed": 0,
                },
            )

            self._logger.info(
                "local_import.queue.prepared",
                "取り込み処理キューを準備",
                enqueued=enqueued_count,
                pending=pending_total,
                session_id=active_session_id,
                celery_task_id=celery_task_id,
                status="queued",
            )

            self._queue_processor.process(
                session,
                import_dir=import_dir,
                originals_dir=originals_dir,
                result=result,
                active_session_id=active_session_id,
                celery_task_id=celery_task_id,
                task_instance=task_instance,
            )
        except Exception as exc:
            result["ok"] = False
            result["errors"].append(f"取り込み処理でエラーが発生しました: {exc}")
            self._logger.error(
                "local_import.task.failed",
                "ローカルインポート処理中に予期しないエラーが発生",
                session_id=active_session_id,
                celery_task_id=celery_task_id,
                error_type=type(exc).__name__,
                error_message=str(exc),
                exc_info=True,
            )
        finally:
            try:
                self._scanner.cleanup()
            except Exception:
                pass

            self._finalize_session(
                session,
                result,
                active_session_id,
                celery_task_id,
            )

        self._logger.info(
            "local_import.task.summary",
            "ローカルインポートタスクが完了",
            ok=result["ok"],
            processed=result["processed"],
            success=result["success"],
            skipped=result["skipped"],
            failed=result["failed"],
            canceled=result.get("canceled", False),
            session_id=result.get("session_id"),
            celery_task_id=celery_task_id,
            status="completed" if result.get("ok") else "error",
        )

        return result

    # internal helpers
    def _load_or_create_session(
        self,
        session_id: Optional[str],
        result: Dict[str, Any],
        celery_task_id: Optional[str],
    ):
        if session_id:
            try:
                session = PickerSession.query.filter_by(session_id=session_id).first()
            except Exception as exc:
                self._logger.error(
                    "local_import.session.load_failed",
                    "セッション取得時にエラーが発生",
                    session_id=session_id,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                )
                result["ok"] = False
                result["errors"].append(f"セッション取得エラー: {exc}")
                return None

            if not session:
                self._logger.error(
                    "local_import.session.missing",
                    "指定されたセッションIDのレコードが見つかりません",
                    session_id=session_id,
                )
                result["ok"] = False
                result["errors"].append(f"セッションが見つかりません: {session_id}")
                return None

            self._logger.info(
                "local_import.session.attach",
                "既存セッションをローカルインポートに紐付け",
                session_id=session_id,
                celery_task_id=celery_task_id,
                status="attached",
            )
            return session

        generated_session_id = f"local_import_{uuid.uuid4().hex}"
        session = PickerSession(
            session_id=generated_session_id,
            status="expanding",
            selected_count=0,
        )
        self._db.session.add(session)
        try:
            self._db.session.commit()
        except Exception as exc:
            self._db.session.rollback()
            result["ok"] = False
            result["errors"].append(f"セッション作成エラー: {exc}")
            self._logger.error(
                "local_import.session.create_failed",
                "ローカルインポート用セッションの作成に失敗",
                session_id=generated_session_id,
                celery_task_id=celery_task_id,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
            return None

        result["session_id"] = session.session_id
        self._logger.info(
            "local_import.session.created",
            "ローカルインポート用セッションを新規作成",
            session_id=session.session_id,
            celery_task_id=celery_task_id,
            status="created",
        )
        return session

    def _set_progress(self, session, **kwargs: Any) -> None:
        self._session_service.set_progress(session, **kwargs)

    def _ensure_directory_exists(
        self,
        directory: str,
        result: Dict[str, Any],
        session,
        active_session_id: Optional[str],
        celery_task_id: Optional[str],
        *,
        reason_key: str,
        log_event: str,
        log_message: str,
        error_message,
        log_details: Optional[Dict[str, Any]] = None,
    ) -> bool:
        if os.path.exists(directory):
            return True

        if session:
            session.selected_count = 0
        self._set_progress(
            session,
            status="error",
            stage=None,
            celery_task_id=celery_task_id,
            stats_updates={
                "total": 0,
                "success": 0,
                "skipped": 0,
                "failed": 0,
                "reason": reason_key,
            },
        )

        result["ok"] = False
        details = log_details or {}
        self._logger.error(
            log_event,
            log_message,
            session_id=active_session_id,
            celery_task_id=celery_task_id,
            **details,
        )
        result["errors"].append(error_message(directory))
        return False

    def _handle_no_files(
        self,
        result: Dict[str, Any],
        session,
        active_session_id: Optional[str],
        celery_task_id: Optional[str],
        import_dir: str,
    ) -> None:
        if session:
            session.selected_count = 0
        self._set_progress(
            session,
            status="error",
            stage=None,
            celery_task_id=celery_task_id,
            stats_updates={
                "total": 0,
                "success": 0,
                "skipped": 0,
                "failed": 0,
                "reason": "no_files_found",
            },
        )

        self._logger.warning(
            "local_import.scan.empty",
            "取り込み対象ファイルが存在しませんでした",
            import_dir=import_dir,
            session_id=active_session_id,
            celery_task_id=celery_task_id,
            status="empty",
        )
        result["ok"] = False
        result["errors"].append(f"取り込み対象ファイルが見つかりません: {import_dir}")

    def _finalize_session(
        self,
        session,
        result: Dict[str, Any],
        active_session_id: Optional[str],
        celery_task_id: Optional[str],
    ) -> None:
        if not session:
            return

        try:
            counts_query = (
                self._db.session.query(
                    PickerSelection.status,
                    self._db.func.count(PickerSelection.id),
                )
                .filter(PickerSelection.session_id == session.id)
                .group_by(PickerSelection.status)
                .all()
            )
            counts_map = {row[0]: row[1] for row in counts_query}

            pending_remaining = sum(
                counts_map.get(status, 0)
                for status in ("pending", "enqueued", "running")
            )
            imported_count = counts_map.get("imported", 0)
            dup_count = counts_map.get("dup", 0)
            skipped_count = counts_map.get("skipped", 0)
            failed_count = counts_map.get("failed", 0)

            result["success"] = imported_count
            result["skipped"] = dup_count + skipped_count
            result["failed"] = failed_count
            result["processed"] = (
                imported_count + dup_count + skipped_count + failed_count
            )

            cancel_requested = bool(result.get("canceled")) or self._session_service.cancel_requested(session)

            recorded_thumbnails = result.get("thumbnail_records")
            thumbnail_snapshot = build_thumbnail_task_snapshot(
                self._db, session, recorded_thumbnails
            )
            result["thumbnail_snapshot"] = thumbnail_snapshot
            thumbnail_status = (
                thumbnail_snapshot.get("status")
                if isinstance(thumbnail_snapshot, dict)
                else None
            )

            thumbnails_pending = thumbnail_status == "progress"
            thumbnails_failed = thumbnail_status == "error"

            if cancel_requested:
                final_status = "canceled"
            elif pending_remaining > 0 or thumbnails_pending:
                final_status = "processing"
            else:
                if (not result["ok"]) or result["failed"] > 0:
                    final_status = "error"
                elif thumbnails_failed:
                    final_status = "imported"
                elif (
                    result["success"] > 0
                    or result["skipped"] > 0
                    or result["processed"] > 0
                ):
                    final_status = "imported"
                else:
                    final_status = "ready"

            session.selected_count = imported_count

            stats = {
                "total": result["processed"],
                "success": result["success"],
                "skipped": result["skipped"],
                "failed": result["failed"],
                "pending": pending_remaining,
                "celery_task_id": celery_task_id,
            }

            import_task_status = "canceled" if cancel_requested else None
            if import_task_status is None:
                if pending_remaining > 0:
                    import_task_status = "progress"
                elif result["failed"] > 0 or not result["ok"]:
                    import_task_status = "error"
                elif result["processed"] > 0:
                    import_task_status = "completed"
                else:
                    import_task_status = "idle"

            tasks_payload = [
                {
                    "key": "import",
                    "label": "File Import",
                    "status": import_task_status,
                    "counts": {
                        "total": result["processed"],
                        "success": result["success"],
                        "skipped": result["skipped"],
                        "failed": result["failed"],
                        "pending": pending_remaining,
                    },
                }
            ]

            if isinstance(thumbnail_snapshot, dict):
                stats["thumbnails"] = thumbnail_snapshot
                if thumbnail_snapshot.get("total") or thumbnail_snapshot.get("status") not in {None, "idle"}:
                    tasks_payload.append(
                        {
                            "key": "thumbnails",
                            "label": "Thumbnail Generation",
                            "status": thumbnail_snapshot.get("status"),
                            "counts": {
                                "total": thumbnail_snapshot.get("total"),
                                "completed": thumbnail_snapshot.get("completed"),
                                "pending": thumbnail_snapshot.get("pending"),
                                "failed": thumbnail_snapshot.get("failed"),
                            },
                            "entries": thumbnail_snapshot.get("entries"),
                        }
                    )

            if tasks_payload:
                stats["tasks"] = tasks_payload

            stage_value = "canceled" if cancel_requested else None
            if stage_value != "canceled":
                if thumbnails_failed:
                    stage_value = "error"
                elif pending_remaining > 0 or thumbnails_pending:
                    stage_value = "progress"
                else:
                    stage_value = "completed"
            if cancel_requested:
                stats.update(
                    {
                        "cancel_requested": False,
                        "canceled_at": datetime.now(timezone.utc)
                        .isoformat()
                        .replace("+00:00", "Z"),
                    }
                )

            self._set_progress(
                session,
                status=final_status,
                stage=stage_value,
                celery_task_id=celery_task_id,
                stats_updates=stats,
            )

            self._logger.info(
                "local_import.session.updated",
                "セッション情報を更新",
                session_id=session.session_id,
                status=final_status,
                stats=stats,
                celery_task_id=celery_task_id,
            )
        except Exception as exc:
            result["errors"].append(f"セッション更新エラー: {exc}")
            self._logger.error(
                "local_import.session.update_failed",
                "セッション更新時にエラーが発生",
                session_id=session.session_id if session else None,
                error_type=type(exc).__name__,
                error_message=str(exc),
                celery_task_id=celery_task_id,
            )
