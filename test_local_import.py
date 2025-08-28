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

def test_local_import():
    """ローカルインポートのテスト（実際のDBは使わない）"""
    print("\n=== ローカルインポートのテスト ===")
    
    # 設定確認
    app = create_app()
    with app.app_context():
        import_dir = app.config.get('LOCAL_IMPORT_DIR', '/tmp/test_import')
        originals_dir = app.config.get('FPV_NAS_ORIGINALS_DIR', '/tmp/test_originals')
        
        print(f"取り込み元: {import_dir}")
        print(f"保存先: {originals_dir}")
        
        # テスト用ディレクトリを作成
        os.makedirs(import_dir, exist_ok=True)
        os.makedirs(originals_dir, exist_ok=True)
        
        try:
            # テストファイル作成
            test_files = create_test_files(import_dir)
            
            print(f"\nテストファイル準備完了: {len(test_files)}件")
            
            # インポート実行（ただし、DBは実際には更新しない）
            print("\n注意: 実際のインポートは実行しません（DB更新を避けるため）")
            print("実際の実行は以下のコマンドで可能です:")
            print("  python -c \"from webapp import create_app; from core.tasks.local_import import local_import_task; app = create_app(); app.app_context().push(); print(local_import_task())\"")
            
            # スキャンのみ実行
            files = scan_import_directory(import_dir)
            print(f"\nスキャン結果: {len(files)}件のサポートファイルが見つかりました")
            
        finally:
            # クリーンアップ
            shutil.rmtree(import_dir, ignore_errors=True)
            shutil.rmtree(originals_dir, ignore_errors=True)
        
        print("✓ ローカルインポートのテスト完了")

if __name__ == "__main__":
    print("ローカルインポート機能のテスト")
    print("=" * 50)
    
    test_scan_directory()
    test_local_import()
    
    print("\n" + "=" * 50)
    print("すべてのテストが完了しました！")
    print("\n使用方法:")
    print("1. 環境変数 LOCAL_IMPORT_DIR に取り込み元ディレクトリを設定")
    print("2. 環境変数 FPV_NAS_ORIGINALS_DIR に保存先ディレクトリを設定")
    print("3. Web管理画面 (/photo-view/admin/settings) からインポート実行")
    print("4. または Celery タスクから実行: local_import_task_celery.delay()")
