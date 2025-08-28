#!/usr/bin/env python3
"""Test script for automatic video transcoding during import."""

import os
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime, timezone

from webapp import create_app
from core.tasks.picker_import import enqueue_media_playback
from core.models.photo_models import Media, MediaPlayback
from webapp.extensions import db


def create_test_video(path: Path) -> None:
    """Create a test video file using ffmpeg."""
    path.parent.mkdir(parents=True, exist_ok=True)
    
    # Create a simple test video using ffmpeg (if available)
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
        # Fallback: create a fake video file for basic testing
        with open(path, 'wb') as f:
            f.write(b'fake_video_data_for_testing')
        return False


def test_video_transcoding():
    """Test automatic video transcoding during import."""
    app = create_app()
    
    with app.app_context():
        # Create test video file
        orig_dir = Path(os.environ["FPV_NAS_ORIG_DIR"])
        test_file = orig_dir / "2025/08/28/test_video.mp4"
        
        has_ffmpeg = create_test_video(test_file)
        print(f"Created test video: {test_file} (ffmpeg available: {has_ffmpeg})")
        
        try:
            # Create Media record for video
            media = Media(
                google_media_id="test_video_123",
                account_id=1,
                local_rel_path="2025/08/28/test_video.mp4",
                hash_sha256="test_video_hash",
                bytes=54321,
                mime_type="video/mp4",
                width=640,
                height=480,
                duration_ms=2000,
                is_video=True,
            )
            db.session.add(media)
            db.session.commit()
            
            print(f"Created video media with ID: {media.id}")
            
            # Test video transcoding
            print("Starting video transcoding...")
            enqueue_media_playback(media.id)
            
            # Check results
            pb = MediaPlayback.query.filter_by(media_id=media.id).first()
            if pb:
                print(f"MediaPlayback created: ID={pb.id}, Status={pb.status}")
                if pb.status == "done":
                    play_dir = Path(os.environ["FPV_NAS_PLAY_DIR"])
                    play_path = play_dir / pb.rel_path
                    if play_path.exists():
                        print(f"✓ Playback file created: {play_path}")
                    else:
                        print(f"✗ Playback file NOT found: {play_path}")
                elif pb.status == "error":
                    print(f"✗ Transcoding failed: {pb.error_msg}")
                else:
                    print(f"Transcoding status: {pb.status}")
            else:
                print("✗ No MediaPlayback record created")
                
        finally:
            # Cleanup
            test_file.unlink(missing_ok=True)
            if pb and pb.rel_path:
                play_path = Path(os.environ["FPV_NAS_PLAY_DIR"]) / pb.rel_path
                play_path.unlink(missing_ok=True)
                
                # Clean up directories
                try:
                    play_path.parent.rmdir()
                    play_path.parent.parent.rmdir() 
                    play_path.parent.parent.parent.rmdir()
                except OSError:
                    pass
            
            print("Cleanup completed")


if __name__ == "__main__":
    test_video_transcoding()
