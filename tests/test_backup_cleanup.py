"""バックアップクリーンアップタスクのテスト"""

import pytest
import tempfile
import os
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import patch

from core.tasks.backup_cleanup import cleanup_old_backups, get_backup_status


class TestBackupCleanup:
    """バックアップクリーンアップのテスト"""

    def test_cleanup_old_backups_empty_directory(self):
        """空のディレクトリでのクリーンアップテスト"""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = cleanup_old_backups(backup_dir=tmpdir)
            
            assert result["ok"] is True
            assert result["deleted_files"] == []
            assert result["deleted_files_count"] == 0
            assert "backup_dir" in result

    def test_cleanup_old_backups_with_old_files(self):
        """古いファイルが存在する場合のクリーンアップテスト"""
        with tempfile.TemporaryDirectory() as tmpdir:
            backup_path = Path(tmpdir)
            
            # 古いファイルを作成
            old_sql_file = backup_path / "old_backup_20240101_120000.sql"
            old_tar_file = backup_path / "old_media_20240101_120000.tar.gz"
            old_backup_file = backup_path / "old_env_20240101_120000.backup"
            
            old_sql_file.write_text("dummy sql content")
            old_tar_file.write_text("dummy tar content")
            old_backup_file.write_text("dummy backup content")
            
            # ファイルの修正時刻を古く設定（35日前）
            old_time = (datetime.now() - timedelta(days=35)).timestamp()
            os.utime(old_sql_file, (old_time, old_time))
            os.utime(old_tar_file, (old_time, old_time))
            os.utime(old_backup_file, (old_time, old_time))
            
            # 新しいファイルも作成
            new_sql_file = backup_path / "new_backup_20240820_120000.sql"
            new_sql_file.write_text("dummy new sql content")
            
            result = cleanup_old_backups(backup_dir=tmpdir, retention_days=30)
            
            assert result["ok"] is True
            assert result["deleted_files_count"] == 3
            assert len(result["deleted_files"]) == 3
            
            # 古いファイルが削除されていることを確認
            assert not old_sql_file.exists()
            assert not old_tar_file.exists()
            assert not old_backup_file.exists()
            
            # 新しいファイルは残っていることを確認
            assert new_sql_file.exists()

    def test_cleanup_old_backups_with_env_var(self):
        """環境変数SYSTEM_BACKUP_DIRECTORYを使用するテスト"""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {'SYSTEM_BACKUP_DIRECTORY': tmpdir}):
                result = cleanup_old_backups()

                assert result["ok"] is True
                assert result["backup_dir"] == tmpdir
 
    def test_cleanup_old_backups_with_legacy_env_var(self):
        """旧環境変数MEDIA_BACKUP_DIRECTORYも利用できる"""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {'MEDIA_BACKUP_DIRECTORY': tmpdir}):
                result = cleanup_old_backups()

                assert result["ok"] is True
                assert result["backup_dir"] == tmpdir

    def test_get_backup_status_empty_directory(self):
        """空のディレクトリでの状況確認テスト"""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = get_backup_status(backup_dir=tmpdir)
            
            assert result["ok"] is True
            assert result["exists"] is True
            assert result["total_files"] == 0
            assert result["total_size"] == 0

    def test_get_backup_status_with_files(self):
        """ファイルが存在する場合の状況確認テスト"""
        with tempfile.TemporaryDirectory() as tmpdir:
            backup_path = Path(tmpdir)
            
            # テストファイルを作成
            sql_file = backup_path / "test_backup.sql"
            tar_file = backup_path / "test_media.tar.gz"
            backup_file = backup_path / "test_env.backup"
            
            sql_file.write_text("dummy sql content")
            tar_file.write_text("dummy tar content")
            backup_file.write_text("dummy backup content")
            
            result = get_backup_status(backup_dir=tmpdir)
            
            assert result["ok"] is True
            assert result["exists"] is True
            assert result["total_files"] == 3
            assert result["sql_files"] == 1
            assert result["archive_files"] == 1
            assert result["config_backup_files"] == 1
            assert result["total_size"] > 0

    def test_get_backup_status_nonexistent_directory(self):
        """存在しないディレクトリでの状況確認テスト"""
        nonexistent_dir = "/tmp/nonexistent_backup_dir_12345"
        result = get_backup_status(backup_dir=nonexistent_dir)
        
        assert result["ok"] is True
        assert result["exists"] is False
        assert "message" in result

    def test_cleanup_old_backups_permission_error(self):
        """権限エラーの場合のテスト"""
        with tempfile.TemporaryDirectory() as tmpdir:
            backup_path = Path(tmpdir)
            
            # ファイルを作成
            test_file = backup_path / "test.sql"
            test_file.write_text("dummy content")
            
            # ディレクトリを読み取り専用に設定
            os.chmod(tmpdir, 0o444)
            
            try:
                result = cleanup_old_backups(backup_dir=tmpdir)
                # 権限エラーが発生した場合はok=Falseになる
                if not result["ok"]:
                    assert "error" in result
            finally:
                # 権限を戻してクリーンアップできるようにする
                os.chmod(tmpdir, 0o755)

    def test_cleanup_with_custom_retention_days(self):
        """カスタム保持期間でのテスト"""
        with tempfile.TemporaryDirectory() as tmpdir:
            backup_path = Path(tmpdir)
            
            # 10日前のファイルを作成
            old_file = backup_path / "old_backup.sql"
            old_file.write_text("dummy content")
            
            old_time = (datetime.now() - timedelta(days=10)).timestamp()
            os.utime(old_file, (old_time, old_time))
            
            # 保持期間7日でクリーンアップ実行
            result = cleanup_old_backups(backup_dir=tmpdir, retention_days=7)
            
            assert result["ok"] is True
            assert result["deleted_files_count"] == 1
            assert len(result["deleted_files"]) == 1
            assert not old_file.exists()
