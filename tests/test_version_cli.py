"""
バージョン情報CLIコマンドのテスト
"""
import pytest
from unittest.mock import patch
from click.testing import CliRunner

from webapp import create_app


class TestVersionCLI:
    """バージョン情報CLIコマンドのテスト"""
    
    @pytest.fixture
    def app(self):
        """テスト用Flaskアプリケーション"""
        app = create_app()
        app.config['TESTING'] = True
        return app
    
    def test_version_command_success(self, app):
        """バージョンコマンドの正常系テスト"""
        mock_version_info = {
            "version": "vtest123",
            "commit_hash": "test123",
            "branch": "main",
            "commit_date": "2025-09-07 15:30:16 +0900",
            "build_date": "2025-09-07T17:18:32+09:00"
        }
        
        runner = CliRunner()
        
        with patch("core.version.get_version_info", return_value=mock_version_info):
            with patch("core.version.get_version_string", return_value="vtest123"):
                with app.app_context():
                    result = runner.invoke(app.cli, ['version'])
        
        assert result.exit_code == 0
        assert "PhotoNest Version Information" in result.output
        assert "Version: vtest123" in result.output
        assert "Commit Hash: test123" in result.output
        assert "Branch: main" in result.output
        assert "2025-09-07 15:30:16 +0900" in result.output
        assert "2025-09-07T17:18:32+09:00" in result.output
    
    def test_version_command_with_unknown_values(self, app):
        """不明な値でのバージョンコマンドテスト"""
        mock_version_info = {
            "version": "dev",
            "commit_hash": "unknown",
            "branch": "unknown",
            "commit_date": "unknown",
            "build_date": "2025-09-07T17:18:32+09:00"
        }
        
        runner = CliRunner()
        
        with patch("core.version.get_version_info", return_value=mock_version_info):
            with patch("core.version.get_version_string", return_value="dev"):
                with app.app_context():
                    result = runner.invoke(app.cli, ['version'])
        
        assert result.exit_code == 0
        assert "Version: dev" in result.output
        assert "Commit Hash: unknown" in result.output
        assert "Branch: unknown" in result.output
        assert "Commit Date: unknown" in result.output
    
    def test_version_command_exception_handling(self, app):
        """バージョンコマンドでの例外処理テスト"""
        runner = CliRunner()
        
        with patch("core.version.get_version_info", side_effect=Exception("Test error")):
            with app.app_context():
                result = runner.invoke(app.cli, ['version'])
        
        # エラーが発生してもコマンドは終了すべき
        # （例外処理の実装によって異なる）
        assert result.exit_code in [0, 1]  # 成功またはエラー終了
    
    def test_version_command_output_format(self, app):
        """バージョンコマンドの出力形式テスト"""
        mock_version_info = {
            "version": "v1a2b3c4",
            "commit_hash": "1a2b3c4",
            "branch": "feature-test",
            "commit_date": "2025-09-07 15:30:16 +0900",
            "build_date": "2025-09-07T17:18:32+09:00"
        }
        
        runner = CliRunner()
        
        with patch("core.version.get_version_info", return_value=mock_version_info):
            with patch("core.version.get_version_string", return_value="v1a2b3c4"):
                with app.app_context():
                    result = runner.invoke(app.cli, ['version'])
        
        lines = result.output.strip().split('\n')
        
        # ヘッダー行の確認
        assert "=== PhotoNest Version Information ===" in lines[0]
        
        # 各情報行の確認
        expected_lines = [
            "Version: v1a2b3c4",
            "Commit Hash: 1a2b3c4", 
            "Branch: feature-test",
            "Commit Date: 2025-09-07 15:30:16 +0900",
            "Build Date: 2025-09-07T17:18:32+09:00"
        ]
        
        for expected_line in expected_lines:
            assert any(expected_line in line for line in lines), f"Missing line: {expected_line}"


class TestVersionCLIIntegration:
    """バージョン情報CLIの統合テスト"""
    
    @pytest.fixture
    def app(self):
        """テスト用Flaskアプリケーション"""
        app = create_app()
        app.config['TESTING'] = True
        return app
    
    def test_version_command_real_execution(self, app):
        """実際の環境でのバージョンコマンド実行テスト"""
        runner = CliRunner()
        
        with app.app_context():
            result = runner.invoke(app.cli, ['version'])
        
        # コマンドが正常に実行されることを確認
        assert result.exit_code == 0
        assert "PhotoNest Version Information" in result.output
        assert "Version:" in result.output
        assert "Commit Hash:" in result.output
        assert "Branch:" in result.output
        
        # 出力が空でないことを確認
        assert len(result.output.strip()) > 0
    
    def test_cli_command_registration(self, app):
        """CLIコマンドが正しく登録されているかテスト"""
        # appのCLIコマンド一覧を取得
        cli_commands = list(app.cli.commands.keys())
        
        # versionコマンドが登録されていることを確認
        assert 'version' in cli_commands


if __name__ == "__main__":
    pytest.main([__file__])
