"""
Google Photos Picker Import Session Log のテスト

Issue: SessionDetailでGoogle Photos PickerのImportログが表示されない問題のテスト
"""
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from webapp import create_app
from webapp.extensions import db
from core.models.picker_session import PickerSession
from core.models.google_account import GoogleAccount
from core.models.worker_log import WorkerLog
from core.models.photo_models import MediaItem, PickerSelection
from webapp.api.picker_session import _collect_local_import_logs


@pytest.fixture
def app():
    """テスト用のFlaskアプリケーションを作成"""
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "test.db"
        
        test_config = {
            'TESTING': True,
            'SECRET_KEY': 'test-secret-key',
            'DATABASE_URI': f'sqlite:///{db_path}',
            'SQLALCHEMY_ENGINE_OPTIONS': {},
            'BABEL_DEFAULT_LOCALE': 'en',
        }
        
        app = create_app()
        app.config.update(test_config)
        
        with app.app_context():
            db.create_all()
            yield app


def test_collect_logs_includes_google_picker_import_logs(app):
    """Google Photos PickerのImportログが収集されることをテスト"""
    
    with app.app_context():
        # Create a Google account
        account = GoogleAccount(
            email="test@example.com",
            oauth_token_json="encrypted_token",
            status="active",
            scopes="https://www.googleapis.com/auth/photoslibrary.readonly"
        )
        db.session.add(account)
        db.session.flush()
        
        # Create a picker session (Google Photos Picker session)
        ps = PickerSession(
            session_id="picker_sessions/test-uuid-123",
            account_id=account.id,
            status="importing",
            selected_count=1
        )
        db.session.add(ps)
        db.session.flush()
        
        # Create worker logs that simulate picker import logs
        # These logs use events like "import.picker.xxx"
        test_logs = [
            {
                "event": "import.picker.session.start",
                "level": "INFO",
                "message": json.dumps({
                    "message": "Google Photos インポート開始",
                    "_extra": {
                        "session_id": ps.session_id,
                        "session_db_id": ps.id,
                        "picker_session_id": ps.id,
                    }
                }),
                "extra_json": {
                    "session_id": ps.session_id,
                    "session_db_id": ps.id,
                    "picker_session_id": ps.id,
                },
                "status": "started"
            },
            {
                "event": "import.picker.item.claim",
                "level": "INFO",
                "message": json.dumps({
                    "message": "アイテム処理開始",
                    "_extra": {
                        "session_id": ps.session_id,
                        "session_db_id": ps.id,
                        "selection_id": 1,
                    }
                }),
                "extra_json": {
                    "session_id": ps.session_id,
                    "session_db_id": ps.id,
                    "selection_id": 1,
                },
                "status": "processing"
            },
            {
                "event": "import.picker.file.saved",
                "level": "INFO",
                "message": json.dumps({
                    "message": "ファイル保存成功",
                    "_extra": {
                        "session_id": ps.session_id,
                        "session_db_id": ps.id,
                        "file_path": "/path/to/file.jpg",
                    }
                }),
                "extra_json": {
                    "session_id": ps.session_id,
                    "session_db_id": ps.id,
                    "file_path": "/path/to/file.jpg",
                },
                "status": "saved"
            },
            {
                "event": "import.picker.session.complete",
                "level": "INFO",
                "message": json.dumps({
                    "message": "Google Photos インポート完了",
                    "_extra": {
                        "session_id": ps.session_id,
                        "session_db_id": ps.id,
                        "imported": 1,
                    }
                }),
                "extra_json": {
                    "session_id": ps.session_id,
                    "session_db_id": ps.id,
                    "imported": 1,
                },
                "status": "completed"
            }
        ]
        
        for log_data in test_logs:
            log = WorkerLog(
                event=log_data["event"],
                level=log_data["level"],
                message=log_data["message"],
                status=log_data.get("status"),
                extra_json=log_data.get("extra_json"),
                created_at=datetime.now(timezone.utc)
            )
            db.session.add(log)
        
        db.session.commit()
        
        # Collect logs for this picker session
        logs = _collect_local_import_logs(ps, limit=None)
        
        # Verify that Google Photos Picker import logs are collected
        assert len(logs) > 0, "Google Photos Pickerのログが収集されていない"
        assert len(logs) == 4, f"Expected 4 logs, got {len(logs)}"
        
        # Verify log details
        events = [log["event"] for log in logs]
        assert "import.picker.session.start" in events
        assert "import.picker.item.claim" in events
        assert "import.picker.file.saved" in events
        assert "import.picker.session.complete" in events
        
        # Verify status is included
        for log in logs:
            assert "status" in log
            assert log["status"] is not None


def test_collect_logs_includes_local_import_logs(app):
    """ローカルインポートのログが収集されることをテスト (既存機能の確認)"""
    
    with app.app_context():
        # Create a local import session (no account_id)
        ps = PickerSession(
            session_id="local_import_test-123",
            account_id=None,  # Local import has no account
            status="importing",
            selected_count=1
        )
        db.session.add(ps)
        db.session.flush()
        
        # Create worker logs for local import (using new import.local.* event names)
        test_logs = [
            {
                "event": "import.local.scan.start",
                "level": "INFO",
                "message": json.dumps({
                    "message": "ローカルインポート開始",
                    "_extra": {
                        "session_id": ps.session_id,
                        "session_db_id": ps.id,
                    }
                }),
                "extra_json": {
                    "session_id": ps.session_id,
                    "session_db_id": ps.id,
                },
                "status": "started"
            },
            {
                "event": "import.local.file.processed_success",
                "level": "INFO",
                "message": json.dumps({
                    "message": "ファイル処理成功",
                    "_extra": {
                        "session_id": ps.session_id,
                        "session_db_id": ps.id,
                        "file": "/import/test.jpg",
                    }
                }),
                "extra_json": {
                    "session_id": ps.session_id,
                    "session_db_id": ps.id,
                    "file": "/import/test.jpg",
                },
                "status": "imported"
            }
        ]
        
        for log_data in test_logs:
            log = WorkerLog(
                event=log_data["event"],
                level=log_data["level"],
                message=log_data["message"],
                status=log_data.get("status"),
                extra_json=log_data.get("extra_json"),
                created_at=datetime.now(timezone.utc)
            )
            db.session.add(log)
        
        db.session.commit()
        
        # Collect logs for this local import session
        logs = _collect_local_import_logs(ps, limit=None)
        
        # Verify that local import logs are collected
        assert len(logs) > 0, "ローカルインポートのログが収集されていない"
        assert len(logs) == 2, f"Expected 2 logs, got {len(logs)}"


def test_collect_logs_filters_by_session(app):
    """異なるセッションのログが混在しないことをテスト"""
    
    with app.app_context():
        # Create two picker sessions
        ps1 = PickerSession(
            session_id="session_1",
            account_id=None,
            status="importing"
        )
        ps2 = PickerSession(
            session_id="session_2",
            account_id=None,
            status="importing"
        )
        db.session.add_all([ps1, ps2])
        db.session.flush()
        
        # Add logs for session 1
        log1 = WorkerLog(
            event="import.picker.test",
            level="INFO",
            message=json.dumps({
                "message": "Session 1 log",
                "_extra": {"session_id": ps1.session_id, "session_db_id": ps1.id}
            }),
            extra_json={"session_id": ps1.session_id, "session_db_id": ps1.id},
            created_at=datetime.now(timezone.utc)
        )
        
        # Add logs for session 2
        log2 = WorkerLog(
            event="import.picker.test",
            level="INFO",
            message=json.dumps({
                "message": "Session 2 log",
                "_extra": {"session_id": ps2.session_id, "session_db_id": ps2.id}
            }),
            extra_json={"session_id": ps2.session_id, "session_db_id": ps2.id},
            created_at=datetime.now(timezone.utc)
        )
        
        db.session.add_all([log1, log2])
        db.session.commit()
        
        # Collect logs for session 1
        logs1 = _collect_local_import_logs(ps1, limit=None)
        assert len(logs1) == 1
        assert "Session 1 log" in logs1[0]["message"]
        
        # Collect logs for session 2
        logs2 = _collect_local_import_logs(ps2, limit=None)
        assert len(logs2) == 1
        assert "Session 2 log" in logs2[0]["message"]


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
