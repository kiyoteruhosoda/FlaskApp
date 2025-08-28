"""Tests for session recovery functionality."""

import pytest
from datetime import datetime, timedelta
from core.tasks.session_recovery import cleanup_stale_sessions, force_cleanup_all_processing_sessions
from core.models.picker_session import PickerSession
from core.db import db


class TestSessionRecovery:
    """セッションリカバリ機能のテスト"""

    def test_cleanup_stale_sessions_no_stale_sessions(self, app_context):
        """古いセッションがない場合のテスト"""
        result = cleanup_stale_sessions()
        
        assert result["ok"] is True
        assert result["updated_count"] == 0
        assert "クリーンアップが必要なセッション" in result["message"]

    def test_cleanup_stale_sessions_with_stale_sessions(self, app_context):
        """古いセッションがある場合のテスト"""
        # 30分以上前の処理中セッションを作成
        old_time = datetime.now() - timedelta(minutes=35)
        session = PickerSession(
            session_id="test-stale-session",
            status="processing",
            created_at=old_time,
            updated_at=old_time
        )
        db.session.add(session)
        db.session.commit()
        
        result = cleanup_stale_sessions()
        
        assert result["ok"] is True
        assert result["updated_count"] == 1
        assert "1個の古いセッション" in result["message"]
        
        # セッションがエラー状態に更新されていることを確認
        updated_session = PickerSession.query.filter_by(session_id="test-stale-session").first()
        assert updated_session.status == "error"
        assert "タイムアウト" in updated_session.error_message

    def test_cleanup_stale_sessions_ignores_recent_sessions(self, app_context):
        """最近のセッションは無視されることのテスト"""
        # 10分前の処理中セッション（まだ新しい）
        recent_time = datetime.now() - timedelta(minutes=10)
        session = PickerSession(
            session_id="test-recent-session",
            status="processing",
            created_at=recent_time,
            updated_at=recent_time
        )
        db.session.add(session)
        db.session.commit()
        
        result = cleanup_stale_sessions()
        
        assert result["ok"] is True
        assert result["updated_count"] == 0
        
        # セッションが変更されていないことを確認
        unchanged_session = PickerSession.query.filter_by(session_id="test-recent-session").first()
        assert unchanged_session.status == "processing"

    def test_cleanup_stale_sessions_ignores_non_processing_sessions(self, app_context):
        """processing以外のステータスのセッションは無視されることのテスト"""
        # 古いが完了済みのセッション
        old_time = datetime.now() - timedelta(minutes=35)
        session = PickerSession(
            session_id="test-completed-session",
            status="ready",
            created_at=old_time,
            updated_at=old_time
        )
        db.session.add(session)
        db.session.commit()
        
        result = cleanup_stale_sessions()
        
        assert result["ok"] is True
        assert result["updated_count"] == 0
        
        # セッションが変更されていないことを確認
        unchanged_session = PickerSession.query.filter_by(session_id="test-completed-session").first()
        assert unchanged_session.status == "ready"

    def test_force_cleanup_all_processing_sessions(self, app_context):
        """全処理中セッションの強制クリーンアップテスト"""
        # 複数の処理中セッションを作成
        for i in range(3):
            session = PickerSession(
                session_id=f"test-force-cleanup-{i}",
                status="processing",
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
            db.session.add(session)
        
        # 完了済みセッションも作成（これは変更されないはず）
        completed_session = PickerSession(
            session_id="test-completed",
            status="ready",
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        db.session.add(completed_session)
        db.session.commit()
        
        result = force_cleanup_all_processing_sessions()
        
        assert result["ok"] is True
        assert result["updated_count"] == 3
        assert "3個のセッション" in result["message"]
        
        # 全ての処理中セッションがエラー状態になっていることを確認
        for i in range(3):
            session = PickerSession.query.filter_by(session_id=f"test-force-cleanup-{i}").first()
            assert session.status == "error"
            assert "強制クリーンアップ" in session.error_message
        
        # 完了済みセッションは変更されていないことを確認
        completed = PickerSession.query.filter_by(session_id="test-completed").first()
        assert completed.status == "ready"

    def test_cleanup_stale_sessions_database_error_handling(self, app_context, monkeypatch):
        """データベースエラー時のエラーハンドリングテスト"""
        # db.session.commit() でエラーを発生させる
        def mock_commit():
            raise Exception("Database connection error")
        
        monkeypatch.setattr(db.session, "commit", mock_commit)
        
        # 古いセッションを作成
        old_time = datetime.now() - timedelta(minutes=35)
        session = PickerSession(
            session_id="test-error-handling",
            status="processing",
            created_at=old_time,
            updated_at=old_time
        )
        db.session.add(session)
        
        result = cleanup_stale_sessions()
        
        assert result["ok"] is False
        assert result["updated_count"] == 0
        assert "エラーが発生しました" in result["message"]
