"""
バージョンファイル生成スクリプトのテスト
"""
import os
import json
import tempfile
import subprocess
import pytest
from unittest.mock import patch, MagicMock


class TestVersionScript:
    """バージョンファイル生成スクリプトのテスト"""
    
    @pytest.fixture
    def temp_dir(self):
        """テスト用一時ディレクトリ"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # core/ディレクトリを作成
            core_dir = os.path.join(temp_dir, 'core')
            os.makedirs(core_dir)
            
            # scripts/ディレクトリを作成してスクリプトをコピー
            scripts_dir = os.path.join(temp_dir, 'scripts')
            os.makedirs(scripts_dir)
            
            # 元のスクリプトをコピー
            original_script = "/home/kyon/myproject/scripts/generate_version.sh"
            temp_script = os.path.join(scripts_dir, 'generate_version.sh')
            
            if os.path.exists(original_script):
                with open(original_script, 'r') as src:
                    script_content = src.read()
                with open(temp_script, 'w') as dst:
                    dst.write(script_content)
                os.chmod(temp_script, 0o755)
            
            yield temp_dir
    
    def test_version_script_with_git(self, temp_dir):
        """Gitが利用可能な場合のバージョンスクリプトテスト"""
        # .gitディレクトリを作成（Gitリポジトリをシミュレート）
        git_dir = os.path.join(temp_dir, '.git')
        os.makedirs(git_dir)
        
        # モックのGitコマンド出力
        mock_git_outputs = {
            'git rev-parse --short HEAD': 'abc1234',
            'git rev-parse HEAD': 'abc1234567890abcdef1234567890abcdef12',
            'git rev-parse --abbrev-ref HEAD': 'main',
            'git log -1 --format=%ci': '2025-09-07 15:30:16 +0900'
        }
        
        def mock_subprocess_run(cmd, **kwargs):
            cmd_str = ' '.join(cmd)
            if cmd_str in mock_git_outputs:
                result = MagicMock()
                result.returncode = 0
                result.stdout = mock_git_outputs[cmd_str]
                return result
            else:
                # デフォルトの動作
                return subprocess.run(cmd, **kwargs)
        
        script_path = os.path.join(temp_dir, 'scripts', 'generate_version.sh')
        
        if os.path.exists(script_path):
            with patch('subprocess.run', side_effect=mock_subprocess_run):
                # スクリプトを実行
                result = subprocess.run(
                    [script_path],
                    cwd=temp_dir,
                    capture_output=True,
                    text=True
                )
            
            # 実行が成功することを確認
            assert result.returncode == 0
            
            # バージョンファイルが生成されることを確認
            version_file = os.path.join(temp_dir, 'core', 'version.json')
            assert os.path.exists(version_file)
            
            # バージョンファイルの内容を確認
            with open(version_file, 'r') as f:
                version_data = json.load(f)
            
            assert version_data['version'] == 'vabc1234'
            assert version_data['commit_hash'] == 'abc1234'
            assert version_data['commit_hash_full'] == 'abc1234567890abcdef1234567890abcdef12'
            assert version_data['branch'] == 'main'
            assert version_data['commit_date'] == '2025-09-07 15:30:16 +0900'
            assert 'build_date' in version_data
    
    def test_version_script_without_git(self, temp_dir):
        """Gitが利用できない場合のバージョンスクリプトテスト"""
        script_path = os.path.join(temp_dir, 'scripts', 'generate_version.sh')
        
        if os.path.exists(script_path):
            # gitコマンドが見つからない状況をシミュレート
            with patch.dict(os.environ, {'PATH': '/nonexistent'}):
                result = subprocess.run(
                    [script_path],
                    cwd=temp_dir,
                    capture_output=True,
                    text=True
                )
            
            # スクリプトは警告を出しつつも成功するべき
            assert result.returncode == 0
            assert "Warning: Git not available" in result.stdout
            
            # バージョンファイルが生成されることを確認
            version_file = os.path.join(temp_dir, 'core', 'version.json')
            assert os.path.exists(version_file)
            
            # バージョンファイルの内容を確認
            with open(version_file, 'r') as f:
                version_data = json.load(f)
            
            assert version_data['version'] == 'dev'
            assert version_data['commit_hash'] == 'unknown'
            assert version_data['branch'] == 'unknown'
            assert version_data['commit_date'] == 'unknown'
            assert 'build_date' in version_data
    
    def test_version_script_feature_branch(self, temp_dir):
        """フィーチャーブランチでのバージョンスクリプトテスト"""
        # .gitディレクトリを作成
        git_dir = os.path.join(temp_dir, '.git')
        os.makedirs(git_dir)
        
        # フィーチャーブランチのモック
        mock_git_outputs = {
            'git rev-parse --short HEAD': 'xyz5678',
            'git rev-parse HEAD': 'xyz5678901234abcdef5678901234abcdef56',
            'git rev-parse --abbrev-ref HEAD': 'feature-test',
            'git log -1 --format=%ci': '2025-09-07 16:00:00 +0900'
        }
        
        def mock_subprocess_run(cmd, **kwargs):
            cmd_str = ' '.join(cmd)
            if cmd_str in mock_git_outputs:
                result = MagicMock()
                result.returncode = 0
                result.stdout = mock_git_outputs[cmd_str]
                return result
            else:
                return subprocess.run(cmd, **kwargs)
        
        script_path = os.path.join(temp_dir, 'scripts', 'generate_version.sh')
        
        if os.path.exists(script_path):
            with patch('subprocess.run', side_effect=mock_subprocess_run):
                result = subprocess.run(
                    [script_path],
                    cwd=temp_dir,
                    capture_output=True,
                    text=True
                )
            
            assert result.returncode == 0
            
            # バージョンファイルの内容を確認
            version_file = os.path.join(temp_dir, 'core', 'version.json')
            with open(version_file, 'r') as f:
                version_data = json.load(f)
            
            # フィーチャーブランチの場合はブランチ名が含まれる
            assert version_data['version'] == 'vxyz5678-feature-test'
            assert version_data['branch'] == 'feature-test'
    
    def test_version_script_output_format(self, temp_dir):
        """バージョンスクリプトの出力形式テスト"""
        script_path = os.path.join(temp_dir, 'scripts', 'generate_version.sh')
        
        if os.path.exists(script_path):
            result = subprocess.run(
                [script_path],
                cwd=temp_dir,
                capture_output=True,
                text=True
            )
            
            # 出力メッセージの確認
            assert "バージョンファイルを生成しています..." in result.stdout
            assert "バージョンファイルが生成されました:" in result.stdout
            assert "バージョン:" in result.stdout
            assert "コミット:" in result.stdout
            assert "ビルド日時:" in result.stdout


class TestVersionScriptIntegration:
    """バージョンファイル生成スクリプトの統合テスト"""
    
    def test_real_script_execution(self):
        """実際のスクリプト実行テスト（プロジェクトルートで）"""
        script_path = "/home/kyon/myproject/scripts/generate_version.sh"
        project_root = "/home/kyon/myproject"
        
        if os.path.exists(script_path):
            # 既存のバージョンファイルをバックアップ
            version_file = os.path.join(project_root, 'core', 'version.json')
            backup_data = None
            if os.path.exists(version_file):
                with open(version_file, 'r') as f:
                    backup_data = f.read()
            
            try:
                # スクリプトを実行
                result = subprocess.run(
                    [script_path],
                    cwd=project_root,
                    capture_output=True,
                    text=True
                )
                
                # スクリプトが成功することを確認
                assert result.returncode == 0
                
                # バージョンファイルが生成されることを確認
                assert os.path.exists(version_file)
                
                # バージョンファイルが有効なJSONであることを確認
                with open(version_file, 'r') as f:
                    version_data = json.load(f)
                
                # 必須フィールドの存在確認
                required_fields = ['version', 'commit_hash', 'branch', 'commit_date', 'build_date']
                for field in required_fields:
                    assert field in version_data
                
                # バージョン文字列の形式確認
                version = version_data['version']
                assert version.startswith('v') or version == 'dev'
                
            finally:
                # バックアップを復元
                if backup_data:
                    with open(version_file, 'w') as f:
                        f.write(backup_data)


if __name__ == "__main__":
    pytest.main([__file__])
