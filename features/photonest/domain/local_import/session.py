"""ローカルインポートにおけるセッション管理ロジック。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.exc import PendingRollbackError


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
        """セッションの進捗と関連統計情報を更新する。

        LocalImport の Celery タスクは 1 つの SQLAlchemy セッションを共有し、
        途中で発生した DB 例外（整合性エラーや型変換エラーなど）が
        `rollback()` されずに残っていると、その時点でトランザクションが
        "無効" とマークされる。SQLAlchemy はこの状態で `commit()` や
        `refresh()` が呼ばれると `PendingRollbackError` を送出し、
        "Can't reconnect until invalid transaction is rolled back" という
        メッセージで失敗を通知する。

        今回のリカバリ処理は以下の順序で「進捗を確定 → 次のステップへ進む」
        ことを保証する:

        1. 進捗値や統計を `_apply_updates()` でインメモリ更新する。
        2. `commit()` が PendingRollbackError を送出したら、その時点の
           変更はまだ DB に反映されていないため `rollback()` で状態を初期化。
        3. 同じ統計値を再度 `_apply_updates()` し、失われた変更を補完する。
        4. 改めて `commit()` を実行し、ここで成功すればステージや統計が
           DB に反映されるので、ワーカーは最新ステージを読み出して
           次の処理に進める。

        すなわち "ロールバックしてから同じ変更をコミットし直す" だけで、
        セッションを作り直したりジョブを再実行したりしなくても、
        停滞していた進捗更新が継続可能になる。"""

        if not session:
            return

        def _apply_updates() -> None:
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

        def _log_failure(exc: Exception) -> None:
            self._log_error(
                "local_import.session.progress_update_failed",
                "セッション状態の更新中にエラーが発生",
                session_id=getattr(session, "session_id", None),
                session_db_id=getattr(session, "id", None),
                error_type=type(exc).__name__,
                error_message=str(exc),
                exc_info=True,
            )

        _apply_updates()

        try:
            self._db.session.commit()
            return
        except PendingRollbackError as pending_exc:  # pragma: no cover - rare path
            # LocalImport のパイプラインでは、例えばメディアの保存処理で一時的に
            # IntegrityError などが発生すると SQLAlchemy セッションは
            # 「無効なトランザクション状態」を保持したままになる。
            # 以降に呼ばれる set_progress からの commit は、この PendingRollbackError
            # によって拒否されるため、まず rollback で正常化する必要がある。
            # ログ上は「Can't reconnect until invalid transaction is rolled back」という
            # 文言で現れるのが特徴で、進捗更新が原因ではなく直前の DB 操作が
            # 失敗していたことを示している。
            self._db.session.rollback()
            self._log_error(
                "local_import.session.progress_retry",
                "無効なトランザクションをロールバックしてセッション更新を再試行",
                session_id=getattr(session, "session_id", None),
                session_db_id=getattr(session, "id", None),
                error_type=type(pending_exc).__name__,
                error_message=str(pending_exc),
            )
            _apply_updates()
            try:
                self._db.session.commit()
                return
            except Exception as exc:  # pragma: no cover - unexpected path
                self._db.session.rollback()
                _log_failure(exc)
                raise
        except Exception as exc:  # pragma: no cover - unexpected path
            self._db.session.rollback()
            _log_failure(exc)
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

