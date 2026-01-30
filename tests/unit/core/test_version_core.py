"""
バージョン情報機能のテスト
"""
import os
import json
import tempfile
import pytest
from unittest.mock import patch, mock_open
from datetime import datetime

from core.version import (
    load_version_from_file,
    get_default_version_info,
    get_version_info,
    get_version_string,
    VERSION_FILE_PATH
)


class TestVersionCore:
    """バージョン情報のコア機能テスト"""
    
    def test_load_version_from_file_success(self):
        """バージョンファイルの正常読み込みテスト"""
        mock_version_data = {
            "version": "v1a2b3c4",
            "commit_hash": "1a2b3c4",
            "commit_hash_full": "1a2b3c4567890abcdef",
            "branch": "main",
            "commit_date": "2025-09-07 15:30:16 +0900",
            "build_date": "2025-09-07T17:18:32+09:00"
        }
        
        with patch("builtins.open", mock_open(read_data=json.dumps(mock_version_data))):
            with patch("os.path.exists", return_value=True):
                result = load_version_from_file()
                
        assert result == mock_version_data
    
    def test_load_version_from_file_not_exists(self):
        """バージョンファイルが存在しない場合のテスト"""
        with patch("os.path.exists", return_value=False):
            result = load_version_from_file()
            
        assert result is None
    
    def test_load_version_from_file_invalid_json(self):
        """無効なJSONファイルの場合のテスト"""
        with patch("builtins.open", mock_open(read_data="invalid json")):
            with patch("os.path.exists", return_value=True):
                result = load_version_from_file()
                
        assert result is None
    
    def test_load_version_from_file_read_error(self):
        """ファイル読み込みエラーのテスト"""
        with patch("builtins.open", side_effect=IOError("Permission denied")):
            with patch("os.path.exists", return_value=True):
                result = load_version_from_file()
                
        assert result is None
    
    def test_get_default_version_info(self):
        """デフォルトバージョン情報のテスト"""
        result = get_default_version_info()
        
        assert result["version"] == "dev"
        assert result["commit_hash"] == "unknown"
        assert result["branch"] == "unknown"
        assert result["commit_date"] == "unknown"
        assert "build_date" in result
        # ビルド日時が現在時刻に近いことを確認
        build_date = datetime.fromisoformat(result["build_date"])
        assert (datetime.now() - build_date).total_seconds() < 1
    
    def test_get_version_info_with_file(self):
        """バージョンファイルがある場合のテスト"""
        mock_version_data = {
            "version": "v1a2b3c4",
            "commit_hash": "1a2b3c4",
            "branch": "main",
            "build_date": "2025-09-07T17:18:32+09:00"
        }
        
        with patch("core.version.load_version_from_file", return_value=mock_version_data):
            result = get_version_info()
            
        assert result["version"] == "v1a2b3c4"
        assert result["commit_hash"] == "1a2b3c4"
        assert result["branch"] == "main"
        assert "app_start_date" in result  # 起動時刻が追加されることを確認
    
    def test_get_version_info_without_file(self):
        """バージョンファイルがない場合のテスト"""
        with patch("core.version.load_version_from_file", return_value=None):
            result = get_version_info()
            
        assert result["version"] == "dev"
        assert result["commit_hash"] == "unknown"
        assert result["branch"] == "unknown"
    
    def test_get_version_string_with_file(self):
        """バージョン文字列取得テスト（ファイルあり）"""
        mock_version_data = {"version": "v1a2b3c4"}
        
        with patch("core.version.load_version_from_file", return_value=mock_version_data):
            result = get_version_string()
            
        assert result == "v1a2b3c4"
    
    def test_get_version_string_without_file(self):
        """バージョン文字列取得テスト（ファイルなし）"""
        with patch("core.version.load_version_from_file", return_value=None):
            result = get_version_string()
            
        assert result == "dev"


class TestVersionIntegration:
    """バージョン情報の統合テスト"""
    
    def test_real_version_file_creation_and_reading(self):
        """実際のバージョンファイル作成と読み込みテスト"""
        # 一時ファイルでテスト
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as temp_file:
            version_data = {
                "version": "vtest123",
                "commit_hash": "test123",
                "commit_hash_full": "test123456789abcdef",
                "branch": "test-branch",
                "commit_date": "2025-09-07 15:30:16 +0900",
                "build_date": "2025-09-07T17:18:32+09:00"
            }
            json.dump(version_data, temp_file)
            temp_path = temp_file.name
        
        try:
            # VERSION_FILE_PATHを一時ファイルパスに変更
            with patch("core.version.VERSION_FILE_PATH", temp_path):
                result = load_version_from_file()
                
            assert result == version_data
            
        finally:
            # クリーンアップ
            os.unlink(temp_path)
    
    def test_version_file_path_exists(self):
        """バージョンファイルパスが正しく設定されているかテスト"""
        # VERSION_FILE_PATHが正しいパスを指していることを確認
        assert VERSION_FILE_PATH.endswith("core/version.json")
        assert "core/version.py" not in VERSION_FILE_PATH  # version.pyではなくversion.json


if __name__ == "__main__":
    pytest.main([__file__])
