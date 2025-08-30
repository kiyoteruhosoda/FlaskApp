#!/usr/bin/env python3
"""ローカルインポートの動画ファイルテスト"""

import os
import tempfile
import shutil
from pathlib import Path
from datetime import datetime, timezone

from webapp import create_app
from core.tasks.local_import import import_single_file
from core.models.photo_models import Media, MediaItem, PhotoMetadata, VideoMetadata, Exif
from webapp.extensions import db


def create_test_video(path: Path) -> None:
    """テスト用動画ファイルを作成"""
    path.parent.mkdir(parents=True, exist_ok=True)
    # MP4ファイルの最小限のヘッダ
    mp4_header = b'\x00\x00\x00\x20ftypisom\x00\x00\x02\x00isomiso2mp41'
    with open(path, 'wb') as f:
        f.write(mp4_header)
        f.write(b'\x00' * 2000)  # ダミーデータ


def test_local_import_video():
    """ローカルインポートで動画ファイルのMediaItemとメタデータが作成されることをテスト"""
    app = create_app()
    
    with app.app_context():
        with tempfile.TemporaryDirectory() as tmp_dir:
            import_dir = Path(tmp_dir) / "import"
            originals_dir = Path(tmp_dir) / "originals"
            
            # テストファイルを作成
            test_video = import_dir / "test_video.mp4"
            create_test_video(test_video)
            
            print(f"テストファイル作成:")
            print(f"  動画: {test_video}")
            
            # 動画インポートのテスト
            print("\n=== 動画インポートのテスト ===")
            result_video = import_single_file(str(test_video), str(import_dir), str(originals_dir))
            print(f"結果: {result_video}")
            
            if result_video["success"]:
                media_id = result_video["media_id"]
                media = Media.query.get(media_id)
                print(f"作成されたMedia: ID={media.id}, google_media_id={media.google_media_id}")
                print(f"  - mime_type: {media.mime_type}")
                print(f"  - is_video: {media.is_video}")
                print(f"  - width: {media.width}, height: {media.height}")
                print(f"  - duration_ms: {media.duration_ms}")
                
                # MediaItemが作成されているかチェック
                if media.google_media_id:
                    media_item = MediaItem.query.get(media.google_media_id)
                    if media_item:
                        print(f"作成されたMediaItem: ID={media_item.id}, type={media_item.type}")
                        print(f"  - filename: {media_item.filename}")
                        print(f"  - photo_metadata_id: {media_item.photo_metadata_id}")
                        print(f"  - video_metadata_id: {media_item.video_metadata_id}")
                        
                        # VideoMetadataがあるかチェック
                        if media_item.video_metadata_id:
                            video_meta = VideoMetadata.query.get(media_item.video_metadata_id)
                            print(f"作成されたVideoMetadata: ID={video_meta.id}")
                            print(f"  - fps: {video_meta.fps}")
                            print(f"  - processing_status: {video_meta.processing_status}")
                        else:
                            print("VideoMetadata: 作成されていません")
                    else:
                        print("MediaItem: 見つかりません")
                else:
                    print("MediaItem: google_media_idがNULL")
            else:
                print(f"インポート失敗: {result_video['reason']}")
            
            print(f"\n=== 統計情報 ===")
            print(f"Media数: {Media.query.count()}")
            print(f"MediaItem数: {MediaItem.query.count()}")
            print(f"PhotoMetadata数: {PhotoMetadata.query.count()}")
            print(f"VideoMetadata数: {VideoMetadata.query.count()}")
            print(f"Exif数: {Exif.query.count()}")


if __name__ == "__main__":
    test_local_import_video()
