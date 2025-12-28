#!/usr/bin/env python
"""
ローカルインポート機能のテスト用スクリプト
"""

import os
import sys
import tempfile
import shutil
from pathlib import Path

# プロジェクトルートを追加
sys.path.insert(0, '/home/kyon/myproject')

from webapp import create_app
from core.tasks.local_import import local_import_task, scan_import_directory
from core.models.picker_session import PickerSession
from core.models.photo_models import PickerSelection
from webapp.config import BaseApplicationSettings
from core.tasks.local_import import local_import_task, scan_import_directory

def create_test_files(import_dir: str) -> list:
    """テスト用のファイルを作成"""
    test_files = []
    
    # テスト画像ファイル（簡単なバイナリデータ）
    test_image_data = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xdb\x00\x00\x00\x00IEND\xaeB`\x82'
    
    # ファイル作成
    files_to_create = [
        ('20240815_143052.jpg', test_image_data),
        ('IMG_20240816_120000.jpg', test_image_data),
        ('VID_20240817_150000.mp4', b'dummy video data'),
        ('test_file.txt', b'not supported file'),  # サポート外拡張子
    ]
    
    for filename, data in files_to_create:
        file_path = os.path.join(import_dir, filename)
        with open(file_path, 'wb') as f:
            f.write(data)
        test_files.append(file_path)
        print(f"作成: {file_path}")
    
    return test_files

def test_scan_directory():
    """ディレクトリスキャンのテスト"""
    print("\n=== ディレクトリスキャンのテスト ===")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        test_files = create_test_files(temp_dir)
        
        # スキャン実行
        scanned_files = scan_import_directory(temp_dir)
        
        print(f"スキャン結果: {len(scanned_files)}件")
        for file in scanned_files:
            print(f"  - {os.path.basename(file)}")
        
        # サポート外ファイルが除外されていることを確認
        txt_files = [f for f in scanned_files if f.endswith('.txt')]
        assert len(txt_files) == 0, "txt ファイルは除外されるべき"
        
        print("✓ ディレクトリスキャンのテスト完了")

def test_local_import_task_with_session(app, db_session, temp_dir):
    """ローカルインポートタスクでPickerSessionとPickerSelectionが作成されることをテスト"""
    
    # テスト用ディレクトリ設定
    import_dir = temp_dir / "import"
    originals_dir = temp_dir / "originals"
    import_dir.mkdir()
    originals_dir.mkdir()
    
    # Flaskアプリの設定を更新
    app.config['MEDIA_LOCAL_IMPORT_DIRECTORY'] = str(import_dir)
    app.config['MEDIA_ORIGINALS_DIRECTORY'] = str(originals_dir)
    
    # テスト用ファイルを作成
    test_video = import_dir / "test_video.mp4"
    test_image = import_dir / "test_image.jpg"
    
    # 簡単なテストファイルを作成
    test_video.write_text("dummy video content")
    
    # 簡単なJPEGファイルを作成（最小限のヘッダー）
    with open(test_image, 'wb') as f:
        f.write(b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb\x00C\x00')
    
    print(f"Found files: {list(import_dir.glob('*'))}")
    
    # Flaskアプリケーションコンテキスト内でタスクを実行
    with app.app_context():
        result = local_import_task()
        
    print(f"Import result: {result}")
    
    # セッションが作成されていることを確認
    assert result["session_id"] is not None
    
    session = PickerSession.query.filter_by(session_id=result["session_id"]).first()
    assert session is not None
    assert session.status in ["processing", "completed"]
    
    # PickerSelectionレコードが作成されていることを確認
    selections = PickerSelection.query.filter_by(session_id=session.id).all()
    print(f"Created selections: {len(selections)}")
    
    # 少なくとも1つのファイルが処理されていることを確認
    assert len(selections) > 0
    
    # ローカルファイル情報が正しく設定されていることを確認
    for selection in selections:
        assert selection.local_filename is not None
        assert selection.local_file_path is not None
        assert selection.google_media_id is None  # ローカルインポートの場合はNone

if __name__ == "__main__":
    print("ローカルインポート機能のテスト")
    print("=" * 50)
    
    test_scan_directory()
    
    print("\n" + "=" * 50)
    print("すべてのテストが完了しました！")
    print("\n使用方法:")
    print("1. 環境変数 MEDIA_LOCAL_IMPORT_DIRECTORY に取り込み元ディレクトリを設定")
    print("2. 環境変数 MEDIA_ORIGINALS_DIRECTORY に保存先ディレクトリを設定")
    print("3. Web管理画面 (/photo-view/settings) からインポート実行")
    print("4. または Celery タスクから実行: local_import_task_celery.delay()")
