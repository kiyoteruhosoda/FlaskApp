"""ローカルインポートにおけるセッション管理ロジック。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional


class LocalImportSessionService:
    """セッションの進捗管理やキャンセル判定を担うドメインサービス。"""

    def __init__(self, db, log_error) -> None:  # type: ignore[no-untyped-def]
        self._db = db
        self._log_error = log_error

    def set_progress(
        self,
        session,
        *,
        status: Optional[str] = None,
        stage: Optional[str] = None,
        celery_task_id: Optional[str] = None,
        stats_updates: Optional[dict[str, Any]] = None,
    ) -> None:
        """セッションの進捗と関連統計情報を更新する。"""

        if not session:
            return

        now = datetime.now(timezone.utc)
        if status:
            session.status = status
        session.last_progress_at = now
        session.updated_at = now

        stats = session.stats() if hasattr(session, "stats") else {}
        if not isinstance(stats, dict):
            stats = {}
        if stage is not None:
            stats["stage"] = stage
        if celery_task_id is not None:
            stats["celery_task_id"] = celery_task_id
        if stats_updates:
            stats.update(stats_updates)
        session.set_stats(stats)

        try:
            self._db.session.commit()
        except Exception as exc:  # pragma: no cover - unexpected path
            self._db.session.rollback()
            self._log_error(
                "local_import.session.progress_update_failed",
                "セッション状態の更新中にエラーが発生",
                session_id=getattr(session, "session_id", None),
                session_db_id=getattr(session, "id", None),
                error_type=type(exc).__name__,
                error_message=str(exc),
                exc_info=True,
            )
            raise

    def cancel_requested(self, session, *, task_instance=None) -> bool:  # type: ignore[no-untyped-def]
        """セッションに対してキャンセルが要求されているかを判定。"""

        if not session:
            return False

        if task_instance and hasattr(task_instance, "is_aborted"):
            try:
                if task_instance.is_aborted():
                    return True
            except Exception:
                pass

        try:
            self._db.session.refresh(session)
        except Exception:
            try:
                self._db.session.rollback()
            except Exception:
                pass
            fresh = session.__class__.query.get(session.id)
            if not fresh:
                return True
            session.status = fresh.status
            session.stats_json = fresh.stats_json

        stats = session.stats() if hasattr(session, "stats") else {}
        if isinstance(stats, dict) and stats.get("cancel_requested"):
            return True

        return session.status == "canceled"


__all__ = ["LocalImportSessionService"]

