"""ローカルインポート Celery タスクのアプリケーション層実装."""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from core.models.picker_session import PickerSession
from core.models.photo_models import PickerSelection

from features.photonest.domain.local_import.import_result import ImportTaskResult
from .results import build_thumbnail_task_snapshot

# Phase 2: 状態管理ログ統合
from features.photonest.infrastructure.local_import.logging_integration import (
    init_audit_logger,
    log_with_audit,
    log_performance,
)


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
        # Phase 2: 処理開始ログ
        import time
        start_time = time.perf_counter()
        
        log_with_audit(
            "ローカルインポートタスク開始",
            session_id=session_id,
            celery_task_id=celery_task_id,
        )
        
        result = ImportTaskResult(
            session_id=session_id,
            celery_task_id=celery_task_id,
        )

        session = self._load_or_create_session(session_id, result, celery_task_id)
        if session is None and not result.ok:
            return result.to_dict()

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
                return result.to_dict()

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
                return result.to_dict()

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
                return result.to_dict()

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

            duplicate_regeneration = "regenerate"
            if session:
                stats = session.stats() if hasattr(session, "stats") else {}
                if isinstance(stats, dict):
                    options = stats.get("options")
                    if isinstance(options, dict):
                        requested = options.get("duplicateRegeneration") or options.get(
                            "duplicate_regeneration"
                        )
                        if isinstance(requested, str):
                            requested_normalized = requested.lower()
                            if requested_normalized in {"regenerate", "skip"}:
                                duplicate_regeneration = requested_normalized

            self._queue_processor.process(
                session,
                import_dir=import_dir,
                originals_dir=originals_dir,
                result=result,
                active_session_id=active_session_id,
                celery_task_id=celery_task_id,
                task_instance=task_instance,
                duplicate_regeneration=duplicate_regeneration,
            )
        except Exception as exc:
            result.add_error(
                f"取り込み処理でエラーが発生しました: {exc}",
            )
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

        summary_payload = result.to_dict()

        # Phase 2: 処理完了ログとパフォーマンス記録
        duration_ms = (time.perf_counter() - start_time) * 1000
        
        # エラーサマリーを作成（大量データ対策）
        error_summary = self._create_error_summary(result)
        
        log_performance(
            "local_import_task",
            duration_ms,
            session_id=result.session_id,
            celery_task_id=celery_task_id,
            total_files=result.processed,
            success_count=result.success,
            failed_count=result.failed,
            error_summary=error_summary,
        )
        
        log_with_audit(
            f"ローカルインポートタスク完了: {result.success}成功, {result.failed}失敗",
            session_id=result.session_id,
            celery_task_id=celery_task_id,
            error_count=error_summary.get("total_errors", 0),
        )

        self._logger.info(
            "local_import.task.summary",
            "ローカルインポートタスクが完了",
            ok=result.ok,
            processed=result.processed,
            success=result.success,
            skipped=result.skipped,
            failed=result.failed,
            canceled=result.canceled,
            errors=result.failure_reasons or result.errors,
            session_id=result.session_id,
            celery_task_id=celery_task_id,
            status="completed" if result.ok else "error",
        )

        return summary_payload

    # internal helpers
    def _load_or_create_session(
        self,
        session_id: Optional[str],
        result: ImportTaskResult,
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
                result.add_error(f"セッション取得エラー: {exc}")
                return None

            if not session:
                self._logger.error(
                    "local_import.session.missing",
                    "指定されたセッションIDのレコードが見つかりません",
                    session_id=session_id,
                )
                result.add_error(f"セッションが見つかりません: {session_id}")
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
            result.add_error(f"セッション作成エラー: {exc}")
            self._logger.error(
                "local_import.session.create_failed",
                "ローカルインポート用セッションの作成に失敗",
                session_id=generated_session_id,
                celery_task_id=celery_task_id,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
            return None

        result.set_session_id(session.session_id)
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
        result: ImportTaskResult,
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

        result.mark_failed()
        details = log_details or {}
        self._logger.error(
            log_event,
            log_message,
            session_id=active_session_id,
            celery_task_id=celery_task_id,
            **details,
        )
        result.add_error(error_message(directory), mark_failed=False)
        return False

    def _handle_no_files(
        self,
        result: ImportTaskResult,
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
        result.add_error(f"取り込み対象ファイルが見つかりません: {import_dir}")

    def _finalize_session(
        self,
        session,
        result: ImportTaskResult,
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

            result.success = imported_count
            result.skipped = dup_count + skipped_count
            result.failed = failed_count
            result.set_duplicates(duplicates=dup_count, manually_skipped=skipped_count)
            result.processed = (
                imported_count + dup_count + skipped_count + failed_count
            )

            only_skipped = (
                result.success == 0
                and result.failed == 0
                and skipped_count > 0
                and dup_count == 0
            )

            only_duplicates = (
                result.success == 0
                and result.failed == 0
                and dup_count > 0
                and skipped_count == 0
            )

            cancel_requested = bool(result.canceled) or self._session_service.cancel_requested(session)

            recorded_thumbnails = result.thumbnail_records
            thumbnail_snapshot = build_thumbnail_task_snapshot(
                self._db, session, recorded_thumbnails
            )
            result.set_thumbnail_snapshot(thumbnail_snapshot)
            thumbnail_status = (
                thumbnail_snapshot.get("status")
                if isinstance(thumbnail_snapshot, dict)
                else None
            )

            thumbnails_pending = thumbnail_status == "progress"
            thumbnails_failed = thumbnail_status == "error"

            if cancel_requested:
                final_status = "canceled"
                result.mark_canceled()
            elif (not result.ok) or result.failed > 0:
                final_status = "error"
            elif pending_remaining > 0 or thumbnails_pending:
                final_status = "processing"
            else:
                if thumbnails_failed:
                    final_status = "imported"
                elif only_duplicates:
                    final_status = "imported"
                elif only_skipped:
                    final_status = "pending"
                elif result.success > 0:
                    final_status = "imported"
                elif result.processed > 0:
                    final_status = "pending"
                else:
                    final_status = "ready"

            session.selected_count = imported_count

            failure_reasons = result.collect_failure_reasons()
            result.set_failure_reasons(failure_reasons)

            stats = {
                "total": result.processed,
                "success": result.success,
                "skipped": result.skipped,
                "failed": result.failed,
                "pending": pending_remaining,
                "celery_task_id": celery_task_id,
            }

            if failure_reasons:
                stats["failure_reasons"] = failure_reasons

            import_task_status = "canceled" if cancel_requested else None
            if import_task_status is None:
                if result.failed > 0 or not result.ok:
                    import_task_status = "error"
                elif pending_remaining > 0 or thumbnails_pending:
                    import_task_status = "progress"
                elif result.success > 0 or only_duplicates:
                    import_task_status = "completed"
                elif only_skipped or result.processed > 0:
                    import_task_status = "pending"
                else:
                    import_task_status = "idle"

            tasks_payload = [
                {
                    "key": "import",
                    "label": "File Import",
                    "status": import_task_status,
                    "counts": {
                        "total": result.processed,
                        "success": result.success,
                        "skipped": result.skipped,
                        "failed": result.failed,
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
                if result.failed > 0 or not result.ok:
                    stage_value = "error"
                elif thumbnails_failed:
                    stage_value = "error"
                elif pending_remaining > 0 or thumbnails_pending or only_skipped:
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
                errors=failure_reasons or None,
            )
        except Exception as exc:
            result.add_error(f"セッション更新エラー: {exc}")
            self._logger.error(
                "local_import.session.update_failed",
                "セッション更新時にエラーが発生",
                session_id=session.session_id if session else None,
                error_type=type(exc).__name__,
                error_message=str(exc),
                celery_task_id=celery_task_id,
            )    
    def _create_error_summary(self, result: ImportTaskResult) -> dict:
        """エラーサマリーを作成（大量データ対策）
        
        Args:
            result: インポート結果
            
        Returns:
            dict: エラーサマリー（件数と代表例のみ）
        """
        from collections import Counter
        
        errors = result.failure_reasons if hasattr(result, 'failure_reasons') and result.failure_reasons else (
            result.errors if hasattr(result, 'errors') and result.errors else []
        )
        
        if not errors:
            return {"total_errors": 0}
        
        # エラータイプを抽出して集計
        error_types = []
        for error in errors:
            if isinstance(error, dict) and "type" in error:
                error_types.append(error["type"])
            elif isinstance(error, Exception):
                error_types.append(type(error).__name__)
            elif isinstance(error, str):
                # 文字列の場合は先頭の単語を使用
                error_types.append(error.split(":")[0] if ":" in error else "Unknown")
            else:
                error_types.append("Unknown")
        
        # 件数集計
        error_type_counts = dict(Counter(error_types))
        
        # 代表的なエラーを最大5件まで保存
        sample_errors = []
        for error in errors[:5]:
            if isinstance(error, dict):
                sample_errors.append(error)
            elif isinstance(error, Exception):
                sample_errors.append({
                    "type": type(error).__name__,
                    "message": str(error),
                })
            else:
                sample_errors.append({"message": str(error)})
        
        return {
            "total_errors": len(errors),
            "error_types": error_type_counts,
            "sample_errors": sample_errors,
            "_note": f"全{len(errors)}件中、代表例{len(sample_errors)}件のみ表示",
        }