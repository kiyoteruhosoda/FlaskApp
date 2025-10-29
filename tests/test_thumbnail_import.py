#!/usr/bin/env python3
"""Test script for thumbnail generation during import."""

import os
import tempfile
from pathlib import Path
from PIL import Image

from webapp import create_app
from core.tasks.picker_import import enqueue_thumbs_generate
from core.models.photo_models import Media
from webapp.extensions import db


def test_thumbnail_generation():
    """Test that thumbnails are generated automatically during import."""
    app = create_app()
    
    with app.app_context():
        # Create a test image file
        orig_dir = Path(os.environ["MEDIA_ORIGINALS_DIRECTORY"])
        test_file = orig_dir / "2025/08/28/test_import.jpg"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Create a test image
        img = Image.new("RGB", (2000, 1500), color=(255, 0, 0))
        img.save(test_file)
        
        try:
            # Create a Media record
            media = Media(
                google_media_id="test_import_123",
                account_id=1,
                local_rel_path="2025/08/28/test_import.jpg",
                hash_sha256="test_hash_123",
                bytes=12345,
                mime_type="image/jpeg",
                width=2000,
                height=1500,
                is_video=False,
            )
            db.session.add(media)
            db.session.commit()
            
            print(f"Created media with ID: {media.id}")
            
            # Test thumbnail generation
            print("Generating thumbnails...")
            enqueue_thumbs_generate(media.id)
            
            # Check that thumbnails were created
            thumbs_dir = Path(os.environ["MEDIA_THUMBNAILS_DIRECTORY"])
            sizes = [256, 512, 1024, 2048]
            
            for size in sizes:
                thumb_path = thumbs_dir / str(size) / "2025/08/28/test_import.jpg"
                if thumb_path.exists():
                    print(f"✓ Thumbnail {size}px created: {thumb_path}")
                else:
                    print(f"✗ Thumbnail {size}px NOT created: {thumb_path}")
                    
        finally:
            # Cleanup
            test_file.unlink(missing_ok=True)
            for size in [256, 512, 1024, 2048]:
                thumb_path = thumbs_dir / str(size) / "2025/08/28/test_import.jpg"
                thumb_path.unlink(missing_ok=True)

            # Remove empty directories
            for size in [256, 512, 1024, 2048]:
                try:
                    (thumbs_dir / str(size) / "2025/08/28").rmdir()
                    (thumbs_dir / str(size) / "2025/08").rmdir()
                    (thumbs_dir / str(size) / "2025").rmdir()
                except OSError:
                    pass


if __name__ == "__main__":
    test_thumbnail_generation()
