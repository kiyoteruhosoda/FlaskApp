"""ローカルインポートの重複処理でメタデータが再適用されることのテスト"""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from webapp import create_app
from core.tasks import local_import
from core.tasks.local_import import import_single_file
from core.models.photo_models import Media, MediaItem, MediaPlayback, PhotoMetadata, Exif
from webapp.extensions import db
from features.photonest.domain.local_import.entities import ImportFile
from features.photonest.domain.local_import.media_file import MediaFileAnalysis


@pytest.fixture
def app_context():
    app = create_app()
    with app.app_context():
        db.create_all()
        try:
            yield
        finally:
            db.session.remove()
            db.drop_all()


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


def test_duplicate_import_updates_relative_path(monkeypatch, tmp_path, app_context):
    """重複取り込み時に撮影日時の更新へ追従して保存先ディレクトリを調整する。"""

    import_dir = tmp_path / "import"
    originals_dir = tmp_path / "originals"
    playback_dir = tmp_path / "playback"
    import_dir.mkdir()
    originals_dir.mkdir()
    monkeypatch.setenv("MEDIA_PLAYBACK_DIRECTORY", str(playback_dir))
    monkeypatch.setattr(local_import, "_playback_storage_root", lambda: playback_dir)

    payload = b"dummy-video-payload"
    file_path = import_dir / "sample.mov"

    class DummyAnalyzer:
        def __init__(self) -> None:
            self.mode = "old"
            self.old_relative_path = "2024/01/02/20240102_local_dummy.mov"
            self.new_relative_path = "2018/01/28/20180128_local_dummy.mov"

        def analyze(self, path: str) -> MediaFileAnalysis:
            file_hash = local_import.calculate_file_hash(path)
            size = Path(path).stat().st_size
            if self.mode == "old":
                shot = datetime(2024, 1, 2, 12, 30, tzinfo=timezone.utc)
                rel_path = self.old_relative_path
            else:
                shot = datetime(2018, 1, 28, 1, 39, 22, tzinfo=timezone.utc)
                rel_path = self.new_relative_path

            return MediaFileAnalysis(
                source=ImportFile(path),
                extension=".mov",
                file_size=size,
                file_hash=file_hash,
                mime_type="video/quicktime",
                is_video=True,
                width=1920,
                height=1080,
                duration_ms=1234,
                orientation=None,
                shot_at=shot,
                exif_data={},
                video_metadata={"fps": 30.0},
                destination_filename=Path(rel_path).name,
                relative_path=rel_path,
                perceptual_hash="video-phash",
            )

    analyzer = DummyAnalyzer()
    monkeypatch.setattr(local_import, "_media_analyzer", analyzer)
    monkeypatch.setattr(local_import._file_importer, "_analysis_service", analyzer.analyze)
    monkeypatch.setattr(
        local_import._file_importer,
        "_post_process_service",
        lambda media, *, logger_override, request_context: {"playback": {"ok": True}},
    )
    monkeypatch.setattr(
        local_import._file_importer,
        "_validate_playback",
        lambda *args, **kwargs: None,
    )

    file_path.write_bytes(payload)
    first = import_single_file(str(file_path), str(import_dir), str(originals_dir))
    assert first["success"] is True

    media = Media.query.get(first["media_id"])
    old_relative = analyzer.old_relative_path
    assert media.local_rel_path == old_relative
    old_original = originals_dir / old_relative
    assert old_original.exists()

    # 既存の再生アセットを用意し、パスの更新が行われることを検証
    media.has_playback = True
    db.session.add(media)
    old_playback_rel = Path(old_relative).with_suffix(".mp4").as_posix()
    old_poster_rel = Path(old_playback_rel).with_suffix(".jpg").as_posix()
    playback_path = playback_dir / old_playback_rel
    playback_path.parent.mkdir(parents=True, exist_ok=True)
    playback_path.write_bytes(b"playback-data")
    poster_path = playback_dir / old_poster_rel
    poster_path.parent.mkdir(parents=True, exist_ok=True)
    poster_path.write_bytes(b"poster-data")
    playback_record = MediaPlayback(
        media_id=media.id,
        preset="std1080p",
        rel_path=old_playback_rel,
        poster_rel_path=old_poster_rel,
        status="done",
    )
    db.session.add(playback_record)
    db.session.commit()
    assert playback_path.exists()
    assert poster_path.exists()

    # 再取り込みで creation_time が正しく解析され、新しいディレクトリに移動されることを確認
    analyzer.mode = "new"
    file_path.write_bytes(payload)

    second = import_single_file(str(file_path), str(import_dir), str(originals_dir))
    assert second["success"] is False
    assert second["metadata_refreshed"] is True
    assert second["relative_path"] == analyzer.new_relative_path
    assert second["imported_path"] == str(originals_dir / analyzer.new_relative_path)

    db.session.expire_all()
    refreshed = Media.query.get(first["media_id"])
    assert refreshed.local_rel_path == analyzer.new_relative_path
    assert refreshed.shot_at == datetime(2018, 1, 28, 1, 39, 22)

    assert not old_original.exists()
    new_original = originals_dir / analyzer.new_relative_path
    assert new_original.exists()

    playback_entry = MediaPlayback.query.filter_by(media_id=refreshed.id).one()
    new_parent = Path(analyzer.new_relative_path).parent
    old_base = Path(old_relative).stem
    new_base = Path(analyzer.new_relative_path).stem

    def _expected_name(old_name: str) -> str:
        if old_base and old_name.startswith(old_base):
            return new_base + old_name[len(old_base) :]
        suffix = Path(old_name).suffix
        if suffix:
            return Path(new_base).with_suffix(suffix).name
        return new_base

    expected_playback_name = _expected_name(Path(old_playback_rel).name)
    expected_poster_name = _expected_name(Path(old_poster_rel).name)
    expected_playback_rel = (
        (new_parent / expected_playback_name)
        if str(new_parent) not in {".", ""}
        else Path(expected_playback_name)
    ).as_posix()
    expected_poster_rel = (
        (new_parent / expected_poster_name)
        if str(new_parent) not in {".", ""}
        else Path(expected_poster_name)
    ).as_posix()
    assert playback_entry.rel_path == expected_playback_rel
    assert playback_entry.poster_rel_path == expected_poster_rel
    assert not (playback_dir / old_playback_rel).exists()
    assert not (playback_dir / old_poster_rel).exists()
    assert (playback_dir / expected_playback_rel).exists()
    assert (playback_dir / expected_poster_rel).exists()


def test_duplicate_refresh_realigns_playback_paths(
    monkeypatch, tmp_path, app_context
):
    """撮影日時が変わらなくても再生アセットのディレクトリを補正する。"""

    import_dir = tmp_path / "import"
    originals_dir = tmp_path / "originals"
    playback_dir = tmp_path / "playback"
    import_dir.mkdir()
    originals_dir.mkdir()
    monkeypatch.setenv("MEDIA_PLAYBACK_DIRECTORY", str(playback_dir))
    monkeypatch.setattr(local_import, "_playback_storage_root", lambda: playback_dir)

    original_update = local_import._update_media_playback_paths
    update_calls = {}

    def _tracking_update(*args, **kwargs):
        update_calls["called"] = True
        update_calls["kwargs"] = kwargs
        return original_update(*args, **kwargs)

    monkeypatch.setattr(local_import, "_update_media_playback_paths", _tracking_update)

    payload = b"dummy-video-payload"
    file_path = import_dir / "sample.mov"

    class DummyAnalyzer:
        def __init__(self) -> None:
            self.mode = "old"
            self.relative_path = "2018/01/28/20180128_local_dummy.mov"

        def analyze(self, path: str) -> MediaFileAnalysis:
            file_hash = local_import.calculate_file_hash(path)
            size = Path(path).stat().st_size
            shot = datetime(2018, 1, 28, 1, 39, 22, tzinfo=timezone.utc)
            width = 1920 if self.mode == "old" else 3840
            return MediaFileAnalysis(
                source=ImportFile(path),
                extension=".mov",
                file_size=size,
                file_hash=file_hash,
                mime_type="video/quicktime",
                is_video=True,
                width=width,
                height=1080,
                duration_ms=1234,
                orientation=None,
                shot_at=shot,
                exif_data={},
                video_metadata={"fps": 30.0},
                destination_filename=Path(self.relative_path).name,
                relative_path=self.relative_path,
                perceptual_hash="video-phash",
            )

    analyzer = DummyAnalyzer()
    monkeypatch.setattr(local_import, "_media_analyzer", analyzer)
    monkeypatch.setattr(local_import._file_importer, "_analysis_service", analyzer.analyze)
    monkeypatch.setattr(
        local_import._file_importer,
        "_post_process_service",
        lambda media, *, logger_override, request_context: {"playback": {"ok": True}},
    )
    monkeypatch.setattr(
        local_import._file_importer,
        "_validate_playback",
        lambda *args, **kwargs: None,
    )

    file_path.write_bytes(payload)
    first = import_single_file(str(file_path), str(import_dir), str(originals_dir))
    assert first["success"] is True

    media = Media.query.get(first["media_id"])
    old_relative = analyzer.relative_path
    assert media.local_rel_path == old_relative

    media.has_playback = True
    db.session.add(media)

    misaligned_rel = "2025/09/26/20250926_local_dummy.mp4"
    misaligned_poster = "2025/09/26/20250926_local_dummy.jpg"
    playback_path = playback_dir / misaligned_rel
    poster_path = playback_dir / misaligned_poster
    playback_path.parent.mkdir(parents=True, exist_ok=True)
    playback_path.write_bytes(b"playback-data")
    poster_path.parent.mkdir(parents=True, exist_ok=True)
    poster_path.write_bytes(b"poster-data")

    playback_record = MediaPlayback(
        media_id=media.id,
        preset="std1080p",
        rel_path=misaligned_rel,
        poster_rel_path=misaligned_poster,
        status="done",
    )
    db.session.add(playback_record)
    db.session.commit()

    assert MediaPlayback.query.filter_by(media_id=media.id).count() == 1

    analyzer.mode = "new"
    file_path.write_bytes(payload)
    second = import_single_file(str(file_path), str(import_dir), str(originals_dir))

    assert second["success"] is False
    assert second["metadata_refreshed"] is True
    assert second["relative_path"] == old_relative

    db.session.expire_all()
    refreshed = Media.query.get(first["media_id"])
    playback_entry = MediaPlayback.query.filter_by(media_id=refreshed.id).one()

    assert update_calls.get("called") is True

    expected_playback_rel = Path(old_relative).with_suffix(".mp4").as_posix()
    expected_poster_rel = Path(old_relative).with_suffix(".jpg").as_posix()

    assert playback_entry.rel_path == expected_playback_rel
    assert playback_entry.poster_rel_path == expected_poster_rel
    assert not (playback_dir / misaligned_rel).exists()
    assert not (playback_dir / misaligned_poster).exists()
    assert (playback_dir / expected_playback_rel).exists()
    assert (playback_dir / expected_poster_rel).exists()


def test_update_media_playback_paths_sets_missing_rel_path(
    monkeypatch, tmp_path, app_context
):
    """既存の再生レコードに rel_path が無い場合でも補完する。"""

    playback_dir = tmp_path / "playback"
    playback_dir.mkdir()
    monkeypatch.setenv("MEDIA_PLAYBACK_DIRECTORY", str(playback_dir))
    monkeypatch.setattr(local_import, "_playback_storage_root", lambda: playback_dir)

    media = Media(
        source_type="local",
        filename="sample.mov",
        local_rel_path="2025/02/03/sample.mov",
        is_video=True,
    )
    db.session.add(media)
    db.session.commit()

    playback = MediaPlayback(
        media_id=media.id,
        preset="std1080p",
        status="pending",
    )
    db.session.add(playback)
    db.session.commit()

    local_import._update_media_playback_paths(
        media,
        old_relative_path=None,
        new_relative_path="2025/02/03/sample.mov",
    )

    db.session.commit()
    db.session.refresh(playback)
    assert playback.rel_path == "2025/02/03/sample.mp4"
