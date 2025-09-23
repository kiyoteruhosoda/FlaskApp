"""Tests for session recovery functionality."""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta, timezone
from core.tasks.session_recovery import (
    cleanup_stale_sessions, 
    force_cleanup_all_processing_sessions,
    get_session_status_report
)
from core.models.picker_session import PickerSession
from core.db import db


class TestSessionRecovery:
    """厳密なセッションリカバリ機能のテスト"""

    def test_cleanup_stale_sessions_no_stale_sessions(self, app_context):
        """古いセッションがない場合のテスト"""
        with patch('cli.src.celery.celery_app.celery') as mock_celery:
            # Celeryの active tasks をモック
            mock_inspect = MagicMock()
            mock_inspect.active.return_value = {}
            mock_celery.control.inspect.return_value = mock_inspect
            
            result = cleanup_stale_sessions()
            
            assert result["ok"] is True
            assert result["updated_count"] == 0
            assert "クリーンアップが必要なセッション" in result["message"]

    def test_cleanup_respects_session_type_timeouts(self, app_context):
        """セッションタイプに応じたタイムアウト時間のテスト"""
        with patch('cli.src.celery.celery_app.celery') as mock_celery:
            mock_inspect = MagicMock()
            mock_inspect.active.return_value = {}
            mock_celery.control.inspect.return_value = mock_inspect
            
            now = datetime.now(timezone.utc)
            
            # ローカルインポート: 1.5時間前（2時間タイムアウトなのでまだOK）
            local_session = PickerSession(
                session_id="local-import-test",
                status="processing",
                created_at=now - timedelta(hours=1.5),
                updated_at=now - timedelta(hours=1.5)
            )
            
            # Picker インポート: 1.5時間前（1時間タイムアウトなのでアウト）
            picker_session = PickerSession(
                session_id="picker-test",
                status="processing", 
                created_at=now - timedelta(hours=1.5),
                updated_at=now - timedelta(hours=1.5)
            )
            
            db.session.add_all([local_session, picker_session])
            db.session.commit()
            
            result = cleanup_stale_sessions()
            
            assert result["ok"] is True
            assert result["updated_count"] == 1  # picker のみクリーンアップ
            
            # ローカルインポートは保護されている
            updated_local = PickerSession.query.filter_by(session_id="local-import-test").first()
            assert updated_local.status == "processing"
            
            # Picker インポートはクリーンアップされた
            updated_picker = PickerSession.query.filter_by(session_id="picker-test").first()
            assert updated_picker.status == "error"
            assert "picker_import" in updated_picker.error_message
            assert "Z" in updated_picker.error_message

            assert result["details"][0]["last_updated"].endswith("Z")

    def test_cleanup_protects_active_celery_tasks(self, app_context):
        """Celeryで実行中のタスクが保護されることのテスト"""
        with patch('cli.src.celery.celery_app.celery') as mock_celery:
            # 実行中タスクをモック
            mock_inspect = MagicMock()
            mock_inspect.active.return_value = {
                'worker1': [
                    {
                        'name': 'local_import.run',
                        'id': 'task-123',
                        'args': ['active-session-id']
                    }
                ]
            }
            mock_celery.control.inspect.return_value = mock_inspect
            
            now = datetime.now(timezone.utc)
            
            # 3時間前の古いセッション（Celeryで実行中）
            active_session = PickerSession(
                session_id="active-session-id",
                status="processing",
                created_at=now - timedelta(hours=3),
                updated_at=now - timedelta(hours=3)
            )
            
            # 3時間前の古いセッション（Celeryで実行されていない）
            inactive_session = PickerSession(
                session_id="inactive-session-id", 
                status="processing",
                created_at=now - timedelta(hours=3),
                updated_at=now - timedelta(hours=3)
            )
            
            db.session.add_all([active_session, inactive_session])
            db.session.commit()
            
            result = cleanup_stale_sessions()
            
            assert result["ok"] is True
            assert result["updated_count"] == 1  # inactive のみクリーンアップ
            
            # 実行中セッションは保護された
            active = PickerSession.query.filter_by(session_id="active-session-id").first()
            assert active.status == "processing"
            
            # 非実行中セッションはクリーンアップされた
            inactive = PickerSession.query.filter_by(session_id="inactive-session-id").first()
            assert inactive.status == "error"
            assert "Z" in inactive.error_message

    def test_get_session_status_report(self, app_context):
        """セッション状況レポート生成のテスト"""
        with patch('cli.src.celery.celery_app.celery') as mock_celery:
            mock_inspect = MagicMock()
            mock_inspect.active.return_value = {
                'worker1': [
                    {
                        'name': 'local_import.run',
                        'id': 'task-123',
                        'args': ['test-session']
                    }
                ]
            }
            mock_inspect.scheduled.return_value = {}
            mock_celery.control.inspect.return_value = mock_inspect
            
            # テストセッション作成
            timestamp = datetime.now(timezone.utc)
            session = PickerSession(
                session_id="test-session",
                status="processing",
                created_at=timestamp - timedelta(minutes=30),
                updated_at=timestamp - timedelta(minutes=30)
            )
            db.session.add(session)
            db.session.commit()
            
            report = get_session_status_report()

            assert 'timestamp' in report
            assert report['timestamp'].endswith('Z')
            assert 'celery_workers_count' in report
            assert 'active_tasks_count' in report
            assert 'processing_sessions_count' in report
            assert 'session_analysis' in report
            assert len(report['session_analysis']) == 1
            
            session_info = report['session_analysis'][0]
            assert session_info['session_id'] == "test-session"
            assert session_info['is_active_in_celery'] is True
            assert session_info['type'] == 'other'  # test-session は other タイプ
            assert session_info['created_at'].endswith('Z')
            assert session_info['updated_at'].endswith('Z')

    def test_cleanup_uses_updated_at_not_created_at(self, app_context):
        """updated_at を基準にタイムアウト判定することのテスト"""
        with patch('cli.src.celery.celery_app.celery') as mock_celery:
            mock_inspect = MagicMock()
            mock_inspect.active.return_value = {}
            mock_celery.control.inspect.return_value = mock_inspect
            
            now = datetime.now(timezone.utc)
            
            # 作成は古いが、最近更新されたセッション
            recent_update_session = PickerSession(
                session_id="recent-update",
                status="processing",
                created_at=now - timedelta(hours=3),  # 作成は3時間前
                updated_at=now - timedelta(minutes=30)  # 更新は30分前
            )
            
            db.session.add(recent_update_session)
            db.session.commit()
            
            result = cleanup_stale_sessions()
            
            assert result["ok"] is True
            assert result["updated_count"] == 0  # クリーンアップされない
            
            # セッションは保護されている
            session = PickerSession.query.filter_by(session_id="recent-update").first()
            assert session.status == "processing"

    def test_force_cleanup_all_processing_sessions(self, app_context):
        """全処理中セッションの強制クリーンアップテスト"""
        # 複数の処理中セッションを作成
        sessions = []
        for i in range(3):
            session = PickerSession(
                session_id=f"test-force-cleanup-{i}",
                status="processing",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            )
            db.session.add(session)
            sessions.append(session)
        
        # 完了済みセッションも作成（これは変更されないはず）
        completed_session = PickerSession(
            session_id="test-completed",
            status="ready",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        db.session.add(completed_session)
        db.session.commit()
        
        result = force_cleanup_all_processing_sessions()
        
        assert result["ok"] is True
        assert result["updated_count"] == 3
        assert "3個のセッション" in result["message"]
        
        # 全ての処理中セッションがエラー状態になっていることを確認
        for session in sessions:
            db.session.refresh(session)
            assert session.status == "error"
            assert "強制クリーンアップ" in session.error_message
            assert "Z" in session.error_message
        
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
        old_time = datetime.now(timezone.utc) - timedelta(minutes=35)
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
