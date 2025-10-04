"""ローカルインポートの重複処理でメタデータが再適用されることのテスト"""

from pathlib import Path

import pytest

from webapp import create_app
from core.tasks import local_import
from core.tasks.local_import import import_single_file
from core.models.photo_models import Media, MediaItem, PhotoMetadata, Exif
from webapp.extensions import db


@pytest.fixture
def app_context():
    app = create_app()
    with app.app_context():
        yield


def _write_dummy_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"dummy-data-for-refresh-test")


def test_duplicate_import_refreshes_metadata(monkeypatch, tmp_path, app_context):
    """重複ファイルの再取り込みでメタデータが更新されることを確認"""

    import_dir = tmp_path / "import"
    originals_dir = tmp_path / "originals"
    file_path = import_dir / "sample.jpg"

    state = {"mode": "old"}

    old_exif = {
        "Make": "BugCam",
        "Model": "BugCam-1",
        "FNumber": 2.8,
        "FocalLength": 35,
        "ISOSpeedRatings": 100,
        "ExposureTime": "1/60",
    }

    new_exif = {
        "Make": "FixedCam",
        "Model": "FixedCam-X",
        "FNumber": 4.0,
        "FocalLength": 50,
        "ISOSpeedRatings": 200,
        "ExposureTime": "1/125",
    }

    dims = {
        "old": (640, 480, 1),
        "new": (1280, 720, 6),
    }

    def fake_get_image_dimensions(_path: str):
        return dims[state["mode"]]

    def fake_extract_exif_data(_path: str):
        return dict(old_exif if state["mode"] == "old" else new_exif)

    monkeypatch.setattr(local_import, "get_image_dimensions", fake_get_image_dimensions)
    monkeypatch.setattr(local_import, "extract_exif_data", fake_extract_exif_data)

    _write_dummy_file(file_path)

    first = import_single_file(str(file_path), str(import_dir), str(originals_dir))
    assert first["success"] is True

    media = Media.query.get(first["media_id"])
    assert media.width == 640
    assert media.height == 480
    assert media.orientation == 1

    exif = Exif.query.get(media.id)
    assert exif.camera_make == "BugCam"
    assert exif.camera_model == "BugCam-1"
    assert exif.iso == 100

    media_item = MediaItem.query.get(media.google_media_id)
    assert media_item.photo_metadata is not None
    photo_meta = PhotoMetadata.query.get(media_item.photo_metadata_id)
    assert photo_meta.iso_equivalent == 100
    assert photo_meta.aperture_f_number == 2.8

    # 再取り込み用に同じファイルを再作成し、メタデータを変更
    state["mode"] = "new"
    _write_dummy_file(file_path)

    second = import_single_file(str(file_path), str(import_dir), str(originals_dir))
    assert second["success"] is False
    assert second["metadata_refreshed"] is True
    assert "メタデータ更新" in second["reason"]
    assert second["media_id"] == first["media_id"]
    assert not file_path.exists()

    db.session.expire_all()

    media = Media.query.get(first["media_id"])
    assert media.width == 1280
    assert media.height == 720
    assert media.orientation == 6
    stored_original = originals_dir / media.local_rel_path
    assert second["imported_path"] == str(stored_original)
    assert second["relative_path"] == media.local_rel_path
    assert second["imported_filename"] == media.filename
    assert stored_original.exists()
    assert media.hash_sha256 == local_import.calculate_file_hash(str(stored_original))
    assert media.bytes == stored_original.stat().st_size

    exif = Exif.query.get(media.id)
    assert exif.camera_make == "FixedCam"
    assert exif.camera_model == "FixedCam-X"
    assert exif.iso == 200
    assert exif.shutter == "1/125"

    media_item = MediaItem.query.get(media.google_media_id)
    assert media_item.width == 1280
    assert media_item.height == 720
    assert media_item.photo_metadata is not None
    photo_meta = PhotoMetadata.query.get(media_item.photo_metadata_id)
    assert photo_meta.iso_equivalent == 200
    assert photo_meta.aperture_f_number == 4.0
    assert photo_meta.exposure_time == "1/125"

