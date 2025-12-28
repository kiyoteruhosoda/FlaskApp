#!/usr/bin/env python3
"""ffprobeを使った動画メタデータ取得のテスト"""

import os
import tempfile
import subprocess
from pathlib import Path

from webapp import create_app
from core.tasks.local_import import import_single_file, extract_video_metadata
from core.models.photo_models import Media, MediaItem, VideoMetadata
from webapp.extensions import db


def create_real_test_video(path: Path) -> bool:
    """ffmpegを使って本物のテスト動画を作成"""
    path.parent.mkdir(parents=True, exist_ok=True)
    
    cmd = [
        "ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=size=640x480:rate=24",
        "-f", "lavfi", "-i", "sine=frequency=1000:sample_rate=48000",
        "-t", "2", "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", str(path)
    ]
    
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def test_ffprobe_metadata_extraction():
    """ffprobeを使った動画メタデータ取得のテスト"""
    app = create_app()
    
    with app.app_context():
        with tempfile.TemporaryDirectory() as tmp_dir:
            import_dir = Path(tmp_dir) / "import"
            originals_dir = Path(tmp_dir) / "originals"
            
            # リアルなテスト動画を作成
            test_video = import_dir / "test_video_with_metadata.mp4"
            success = create_real_test_video(test_video)
            
            if not success:
                print("ffmpegでの動画作成に失敗しました。簡易版でテストします。")
                # 簡易版のMP4ファイルを作成
                mp4_header = b'\x00\x00\x00\x20ftypisom\x00\x00\x02\x00isomiso2mp41'
                with open(test_video, 'wb') as f:
                    f.write(mp4_header)
                    f.write(b'\x00' * 2000)
            else:
                print(f"リアルなテスト動画を作成しました: {test_video}")
            
            # ffprobeで直接メタデータを取得してテスト
            print("\n=== ffprobeによる動画メタデータ取得テスト ===")
            video_meta = extract_video_metadata(str(test_video))
            print(f"取得されたメタデータ: {video_meta}")
            
            # 動画インポートのテスト
            print("\n=== 動画インポートテスト ===")
            result_video = import_single_file(str(test_video), str(import_dir), str(originals_dir))
            print(f"インポート結果: {result_video}")
            
            if result_video["success"]:
                media_id = result_video["media_id"]
                media = Media.query.get(media_id)
                print(f"作成されたMedia: ID={media.id}")
                print(f"  - mime_type: {media.mime_type}")
                print(f"  - is_video: {media.is_video}")
                print(f"  - width: {media.width}, height: {media.height}")
                print(f"  - duration_ms: {media.duration_ms}")
                
                # MediaItemの確認
                if media.google_media_id:
                    media_item = MediaItem.query.get(media.google_media_id)
                    if media_item:
                        print(f"MediaItem: ID={media_item.id}, type={media_item.type}")
                        
                        if media_item.video_metadata_id:
                            video_metadata = VideoMetadata.query.get(media_item.video_metadata_id)
                            print(f"VideoMetadata: ID={video_metadata.id}")
                            print(f"  - fps: {video_metadata.fps}")
                            print(f"  - processing_status: {video_metadata.processing_status}")
                        else:
                            print("VideoMetadata: 作成されていません")
                    else:
                        print("MediaItem: 見つかりません")


if __name__ == "__main__":
    test_ffprobe_metadata_extraction()
