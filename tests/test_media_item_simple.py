#!/usr/bin/env python3
"""ローカルインポートのMediaItem作成機能のテスト（データベース確認版）"""

import os
import tempfile
import shutil
from pathlib import Path
from datetime import datetime, timezone

from webapp import create_app
from core.tasks.local_import import import_single_file
from core.models.photo_models import Media, MediaItem, PhotoMetadata, VideoMetadata, Exif
from webapp.extensions import db


def create_test_image(path: Path) -> None:
    """テスト用画像ファイルを作成"""
    path.parent.mkdir(parents=True, exist_ok=True)
    # 簡易的なJPEGファイルヘッダを作成（最小限）
    jpeg_header = b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb\x00C\x00'
    jpeg_footer = b'\xff\xd9'
    with open(path, 'wb') as f:
        f.write(jpeg_header)
        f.write(b'\x00' * 1000)  # ダミーデータ
        f.write(jpeg_footer)


def test_local_import_with_media_item():
    """ローカルインポートでMediaItemとメタデータが作成されることをテスト"""
    app = create_app()
    
    with app.app_context():
        # 既存データの確認
        print("=== 既存データの確認 ===")
        print(f"Media数: {Media.query.count()}")
        print(f"MediaItem数: {MediaItem.query.count()}")
        print(f"PhotoMetadata数: {PhotoMetadata.query.count()}")
        print(f"VideoMetadata数: {VideoMetadata.query.count()}")
        print(f"Exif数: {Exif.query.count()}")
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            import_dir = Path(tmp_dir) / "import"
            originals_dir = Path(tmp_dir) / "originals"
            
            # テストファイルを作成
            test_image = import_dir / "test_image.jpg"
            create_test_image(test_image)
            
            print(f"\nテストファイル作成:")
            print(f"  画像: {test_image}")
            
            # 画像インポートのテスト
            print("\n=== 画像インポートのテスト ===")
            result_image = import_single_file(str(test_image), str(import_dir), str(originals_dir))
            print(f"結果: {result_image}")
            
            if result_image["success"]:
                media_id = result_image["media_id"]
                media = Media.query.get(media_id)
                print(f"作成されたMedia: ID={media.id}, google_media_id={media.google_media_id}")
                print(f"  - mime_type: {media.mime_type}")
                print(f"  - is_video: {media.is_video}")
                print(f"  - width: {media.width}, height: {media.height}")
                
                # MediaItemが作成されているかチェック
                if media.google_media_id:
                    media_item = MediaItem.query.get(media.google_media_id)
                    if media_item:
                        print(f"作成されたMediaItem: ID={media_item.id}, type={media_item.type}")
                        print(f"  - filename: {media_item.filename}")
                        print(f"  - photo_metadata_id: {media_item.photo_metadata_id}")
                        print(f"  - video_metadata_id: {media_item.video_metadata_id}")
                        
                        # PhotoMetadataがあるかチェック
                        if media_item.photo_metadata_id:
                            photo_meta = PhotoMetadata.query.get(media_item.photo_metadata_id)
                            print(f"作成されたPhotoMetadata: ID={photo_meta.id}")
                            print(f"  - focal_length: {photo_meta.focal_length}")
                            print(f"  - aperture_f_number: {photo_meta.aperture_f_number}")
                            print(f"  - iso_equivalent: {photo_meta.iso_equivalent}")
                            print(f"  - exposure_time: {photo_meta.exposure_time}")
                        else:
                            print("PhotoMetadata: 作成されていません")
                    else:
                        print("MediaItem: 見つかりません")
                else:
                    print("MediaItem: google_media_idがNULL")
            else:
                print(f"インポート失敗: {result_image['reason']}")
            
            # 統計情報を表示
            print(f"\n=== 更新後の統計情報 ===")
            print(f"Media数: {Media.query.count()}")
            print(f"MediaItem数: {MediaItem.query.count()}")
            print(f"PhotoMetadata数: {PhotoMetadata.query.count()}")
            print(f"VideoMetadata数: {VideoMetadata.query.count()}")
            print(f"Exif数: {Exif.query.count()}")


if __name__ == "__main__":
    test_local_import_with_media_item()
