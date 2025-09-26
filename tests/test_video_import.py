"""ローカルインポートの動画ファイルテスト"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from core.models.photo_models import Media, MediaItem, VideoMetadata
from core.tasks import local_import as local_import_module
from core.tasks.local_import import import_single_file


def create_test_video(path: Path) -> None:
    """最小限のMP4ヘッダのみを持つテスト用動画ファイルを生成する。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    mp4_header = b"\x00\x00\x00\x20ftypisom\x00\x00\x02\x00isomiso2mp41"
    path.write_bytes(mp4_header + (b"\x00" * 2000))


def _import_video(import_path: Path, import_dir: Path, originals_dir: Path) -> tuple[Media, MediaItem, VideoMetadata]:
    """ローカルインポートを実行し、生成されたモデルを返す。"""

    result = import_single_file(str(import_path), str(import_dir), str(originals_dir))
    assert result["success"], result

    media = Media.query.get(result["media_id"])
    assert media is not None
    assert media.google_media_id == result["media_google_id"]

    media_item = MediaItem.query.get(media.google_media_id)
    assert media_item is not None
    assert media_item.type == "VIDEO"

    video_meta = VideoMetadata.query.get(media_item.video_metadata_id)
    assert video_meta is not None
    assert video_meta.processing_status == "UNSPECIFIED"

    destination = originals_dir / media.local_rel_path
    assert destination.exists()
    assert not import_path.exists()

    return media, media_item, video_meta


@pytest.mark.usefixtures("app_context")
def test_local_import_mp4_video(tmp_path: Path) -> None:
    """MP4ファイルがローカルインポート経由で正しく登録されることを検証する。"""

    import_dir = tmp_path / "import"
    originals_dir = tmp_path / "originals"
    import_dir.mkdir()
    originals_dir.mkdir()

    test_video = import_dir / "test_video.mp4"
    create_test_video(test_video)

    media, media_item, _ = _import_video(test_video, import_dir, originals_dir)

    assert media.is_video is True
    assert media.mime_type == "video/mp4"
    assert media.filename == "test_video.mp4"
    assert media.local_rel_path.endswith(".mp4")
    assert media_item.filename == "test_video.mp4"


@pytest.mark.usefixtures("app_context")
def test_local_import_mov_video(tmp_path: Path) -> None:
    """QuickTime(MOV)ファイルもローカルインポートで処理できることを確認する。"""

    import_dir = tmp_path / "import"
    originals_dir = tmp_path / "originals"
    import_dir.mkdir()
    originals_dir.mkdir()

    test_video = import_dir / "TestClip.MOV"
    create_test_video(test_video)

    media, media_item, _ = _import_video(test_video, import_dir, originals_dir)

    assert media.is_video is True
    assert media.mime_type == "video/quicktime"
    assert media.filename == "TestClip.MOV"
    assert media.local_rel_path.endswith(".mov")
    assert media_item.filename == "TestClip.MOV"


@pytest.mark.usefixtures("app_context")
def test_video_shot_at_from_metadata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """動画メタデータから shot_at が設定されることを確認する。"""

    import_dir = tmp_path / "import"
    originals_dir = tmp_path / "originals"
    import_dir.mkdir()
    originals_dir.mkdir()

    test_video = import_dir / "ShotAtSample.mp4"
    create_test_video(test_video)

    expected_shot_at = datetime(2024, 5, 1, 12, 34, 56, tzinfo=timezone.utc)

    def fake_extract(path: str) -> dict:
        assert path == str(test_video)
        return {
            "width": 1920,
            "height": 1080,
            "duration_ms": 1234,
            "shot_at": expected_shot_at,
        }

    monkeypatch.setattr(local_import_module, "extract_video_metadata", fake_extract)

    media, _, _ = _import_video(test_video, import_dir, originals_dir)

    assert media.shot_at == expected_shot_at.replace(tzinfo=None)
