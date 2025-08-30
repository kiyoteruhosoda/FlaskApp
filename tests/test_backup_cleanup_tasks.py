"""バックアップクリーンアップCeleryタスクのテスト"""

import pytest
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import patch

from cli.src.celery.tasks import backup_cleanup_task, backup_status_task


class TestBackupCleanupTasks:
    """バックアップクリーンアップCeleryタスクのテスト"""

    def test_backup_cleanup_task(self):
        """バックアップクリーンアップタスクのテスト"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # テスト用の古いファイルを作成
            backup_path = Path(tmpdir)
            old_file = backup_path / "old_backup.sql"
            old_file.write_text("dummy content")
            
            # 35日前に設定
            old_time = (datetime.now() - timedelta(days=35)).timestamp()
            old_file.touch()
            old_file.stat()
            
            with patch.dict('os.environ', {'BACKUP_DIR': tmpdir}):
                # タスク実行（self引数をモック）
                class MockSelf:
                    pass
                
                result = backup_cleanup_task(MockSelf(), retention_days=30)
                
                assert result["ok"] is True
                assert "backup_dir" in result

    def test_backup_status_task(self):
        """バックアップ状況確認タスクのテスト"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # テスト用ファイルを作成
            backup_path = Path(tmpdir)
            test_file = backup_path / "test_backup.sql"
            test_file.write_text("dummy content")
            
            with patch.dict('os.environ', {'BACKUP_DIR': tmpdir}):
                # タスク実行（self引数をモック）
                class MockSelf:
                    pass
                
                result = backup_status_task(MockSelf())
                
                assert result["ok"] is True
                assert result["exists"] is True
                assert result["total_files"] >= 1

    def test_backup_cleanup_task_with_default_retention(self):
        """デフォルト保持期間でのバックアップクリーンアップタスクテスト"""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict('os.environ', {'BACKUP_DIR': tmpdir}):
                class MockSelf:
                    pass
                
                # デフォルト値（30日）でタスク実行
                result = backup_cleanup_task(MockSelf())
                
                assert result["ok"] is True
                assert "retention_days" in result
                # デフォルト値が30日であることを確認
                assert result.get("retention_days") == 30
