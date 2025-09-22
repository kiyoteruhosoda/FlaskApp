#!/usr/bin/env python3
"""Test script for automatic thumbnail generation during picker import."""

import os
import json
import tempfile
from pathlib import Path
from PIL import Image
from datetime import datetime, timezone

from webapp import create_app
from core.models.picker_session import PickerSession
from core.models.photo_models import PickerSelection, MediaItem
from webapp.extensions import db


def create_test_import():
    """Test automatic thumbnail generation during picker import."""
    app = create_app()
    
    with app.app_context():
        # Create test picker session
        ps = PickerSession(account_id=1, status="pending")
        db.session.add(ps)
        db.session.flush()
        
        # Create test media item
        mi = MediaItem(
            id="test_media_item_12345",
            mime_type="image/jpeg", 
            filename="test_photo.jpg",
            type="PHOTO",
            width=3000,
            height=2000
        )
        db.session.add(mi)
        db.session.flush()
        
        # Create picker selection
        selection = PickerSelection(
            session_id=ps.id,
            google_media_id="test_media_item_12345",
            status="enqueued",
            create_time=datetime.now(timezone.utc)
        )
        db.session.add(selection)
        db.session.commit()
        
        print(f"Created test session {ps.id} with selection {selection.id}")
        
        # Mock the import process to test thumbnail generation
        from core.tasks.picker_import import picker_import_item
        
        # We'll need to mock external dependencies for this test
        import unittest.mock as mock
        
        # Mock the Google API calls and file download
        with mock.patch('core.tasks.picker_import.requests') as mock_requests:
            # Mock the media item fetch response
            mock_response = mock.Mock()
            mock_response.json.return_value = {
                "id": "test_media_item_12345",
                "baseUrl": "https://example.com/photo",
                "filename": "test_photo.jpg",
                "mimeType": "image/jpeg",
                "mediaMetadata": {
                    "width": "3000",
                    "height": "2000",
                    "creationTime": "2025-08-28T10:00:00Z"
                }
            }
            mock_response.raise_for_status.return_value = None
            mock_requests.get.return_value = mock_response
            
            # Create a test image file to download
            orig_dir = Path(os.environ["FPV_NAS_ORIGINALS_DIR"])
            test_image_data = b"fake_image_data_for_testing"
            
            # Mock the download response
            mock_dl_response = mock.Mock()
            mock_dl_response.content = test_image_data
            mock_dl_response.raise_for_status.return_value = None
            
            # Mock file creation
            with mock.patch('core.tasks.picker_import._download') as mock_download:
                # Create an actual test image file for thumbnail generation
                test_img_path = orig_dir / "2025/08/28/20250828_100000_picker_testhash.jpg"
                test_img_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Create test image
                img = Image.new("RGB", (3000, 2000), color=(0, 255, 0))
                img.save(test_img_path)
                
                # Mock download result
                from core.tasks.picker_import import Downloaded
                mock_download.return_value = Downloaded(
                    path=test_img_path,
                    sha256="testhash12345678",
                    bytes=len(test_image_data)
                )
                
                try:
                    # Execute the import
                    print("Executing picker_import_item...")
                    result = picker_import_item(
                        selection_id=selection.id,
                        session_id=ps.id,
                        locked_by="test"
                    )
                    
                    print(f"Import result: {result}")
                    
                    # Check that thumbnails were generated
                    thumbs_dir = Path(os.environ["FPV_NAS_THUMBS_DIR"])
                    sizes = [256, 512, 1024, 2048]
                    
                    rel_path = "2025/08/28/20250828_100000_picker_testhash.jpg"
                    
                    for size in sizes:
                        thumb_path = thumbs_dir / str(size) / rel_path
                        if thumb_path.exists():
                            print(f"✓ Thumbnail {size}px created: {thumb_path}")
                        else:
                            print(f"✗ Thumbnail {size}px NOT created: {thumb_path}")
                    
                finally:
                    # Cleanup
                    test_img_path.unlink(missing_ok=True)
                    for size in sizes:
                        thumb_path = thumbs_dir / str(size) / rel_path
                        thumb_path.unlink(missing_ok=True)


if __name__ == "__main__":
    create_test_import()
