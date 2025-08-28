"""Session recovery tasks for cleaning up stale processing sessions."""

from datetime import datetime, timedelta
from core.models.picker_session import PickerSession
from core.db import db
import logging

logger = logging.getLogger(__name__)


def cleanup_stale_sessions():
    """
    古い処理中セッションをエラー状態にクリーンアップする定期タスク。
    
    30分以上前に作成されて、まだprocessing状態のセッションを
    エラー状態に変更する。
    
    Returns:
        dict: {"ok": bool, "updated_count": int, "message": str}
    """
    try:
        # 30分以上前に作成された処理中セッションを検索
        cutoff_time = datetime.now() - timedelta(minutes=30)
        
        stale_sessions = PickerSession.query.filter(
            PickerSession.status == 'processing',
            PickerSession.created_at < cutoff_time
        ).all()
        
        updated_count = 0
        for session in stale_sessions:
            logger.info(f"Cleaning up stale session {session.id} (created: {session.created_at})")
            session.status = 'error'
            session.error_message = (
                'セッションがタイムアウトしました。'
                'Celeryワーカーの再起動またはシステム負荷により処理が中断された可能性があります。'
                f' (自動リカバリ実行時刻: {datetime.now()})'
            )
            session.updated_at = datetime.now()
            updated_count += 1
        
        if updated_count > 0:
            db.session.commit()
            logger.info(f"Session recovery: Updated {updated_count} stale sessions to error state")
            return {
                "ok": True,
                "updated_count": updated_count,
                "message": f"{updated_count}個の古いセッションをエラー状態に更新しました"
            }
        else:
            logger.debug("Session recovery: No stale sessions found")
            return {
                "ok": True,
                "updated_count": 0,
                "message": "クリーンアップが必要なセッションはありませんでした"
            }
            
    except Exception as e:
        logger.error(f"Session recovery failed: {e}")
        db.session.rollback()
        return {
            "ok": False,
            "updated_count": 0,
            "message": f"セッションリカバリでエラーが発生しました: {str(e)}"
        }


def force_cleanup_all_processing_sessions():
    """
    全ての処理中セッションを強制的にエラー状態にする（緊急時用）。
    
    Returns:
        dict: {"ok": bool, "updated_count": int, "message": str}
    """
    try:
        processing_sessions = PickerSession.query.filter(
            PickerSession.status == 'processing'
        ).all()
        
        updated_count = 0
        for session in processing_sessions:
            logger.warning(f"Force cleaning session {session.id}")
            session.status = 'error'
            session.error_message = (
                '強制クリーンアップによりセッションが終了されました。'
                f' (実行時刻: {datetime.now()})'
            )
            session.updated_at = datetime.now()
            updated_count += 1
        
        if updated_count > 0:
            db.session.commit()
            logger.warning(f"Force cleanup: Updated {updated_count} sessions to error state")
        
        return {
            "ok": True,
            "updated_count": updated_count,
            "message": f"{updated_count}個のセッションを強制的にクリーンアップしました"
        }
        
    except Exception as e:
        logger.error(f"Force cleanup failed: {e}")
        db.session.rollback()
        return {
            "ok": False,
            "updated_count": 0,
            "message": f"強制クリーンアップでエラーが発生しました: {str(e)}"
        }
