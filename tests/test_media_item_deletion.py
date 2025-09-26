"""MediaItem削除時のPhotoMetadataの削除をテスト"""

from core.models.photo_models import MediaItem, PhotoMetadata
from webapp.extensions import db


def test_photo_metadata_deleted_with_media_item(app_context):
    """MediaItemを削除した際に関連PhotoMetadataも削除されることを確認"""
    photo_metadata = PhotoMetadata(
        focal_length=50.0,
        aperture_f_number=1.8,
        iso_equivalent=100,
        exposure_time="1/125",
    )
    media_item = MediaItem(
        id="test-media",
        type="PHOTO",
        mime_type="image/jpeg",
        filename="test.jpg",
        width=1920,
        height=1080,
        photo_metadata=photo_metadata,
    )

    db.session.add(media_item)
    db.session.commit()

    metadata_id = photo_metadata.id
    assert PhotoMetadata.query.get(metadata_id) is not None

    db.session.delete(media_item)
    db.session.commit()

    assert PhotoMetadata.query.get(metadata_id) is None
