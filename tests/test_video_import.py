"""ローカルインポートの動画ファイルテスト"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from core.db import db
from core.models.photo_models import Media, MediaItem, MediaPlayback, VideoMetadata
from core.tasks import local_import as local_import_module
from core.tasks import media_post_processing
from core.tasks.local_import import import_single_file


def create_test_video(path: Path) -> None:
    """最小限のMP4ヘッダのみを持つテスト用動画ファイルを生成する。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    mp4_header = b"\x00\x00\x00\x20ftypisom\x00\x00\x02\x00isomiso2mp41"
    path.write_bytes(mp4_header + (b"\x00" * 2000))


def _stub_playback_success(monkeypatch: pytest.MonkeyPatch, playback_dir: Path) -> None:
    """動画再生生成処理をスタブ化し、ダミーファイルを作成する。"""

    def fake_enqueue(
        media_id: int,
        *,
        logger_override=None,
        operation_id=None,
        request_context=None,
    ) -> dict:
        media = Media.query.get(media_id)
        if media:
            media.has_playback = True
        playback = MediaPlayback.query.filter_by(media_id=media_id, preset="std1080p").first()
        if not playback:
            rel_path = "2024/01/01/test.mp4"
            playback = MediaPlayback(
                media_id=media_id,
                preset="std1080p",
                rel_path=rel_path,
                status="done",
            )
            db.session.add(playback)
        else:
            playback.status = "done"
            playback.rel_path = playback.rel_path or "2024/01/01/test.mp4"

        playback.poster_rel_path = playback.poster_rel_path or "2024/01/01/test.jpg"
        playback.updated_at = datetime.now(timezone.utc)
        db.session.commit()

        dest = playback_dir / playback.rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"stub playback")

        poster = playback_dir / (playback.poster_rel_path or "2024/01/01/test.jpg")
        poster.parent.mkdir(parents=True, exist_ok=True)
        poster.write_bytes(b"stub poster")

        return {
            "ok": True,
            "note": "stub",
            "output_path": str(dest),
            "poster_path": str(poster),
        }

    monkeypatch.setattr(media_post_processing, "enqueue_media_playback", fake_enqueue)


def _stub_playback_failure(monkeypatch: pytest.MonkeyPatch, note: str = "stub_failure") -> None:
    """動画再生生成処理を失敗させるスタブを設定する。"""

    def fake_enqueue(
        media_id: int,
        *,
        logger_override=None,
        operation_id=None,
        request_context=None,
    ) -> dict:
        return {"ok": False, "note": note}

    monkeypatch.setattr(media_post_processing, "enqueue_media_playback", fake_enqueue)


def _stub_video_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    """動画メタデータ取得を安定化させるスタブを設定する。"""

    def fake_extract(path: str) -> dict:
        return {
            "width": 1920,
            "height": 1080,
            "duration_ms": 1200,
            "shot_at": datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc),
        }

    monkeypatch.setattr(local_import_module, "extract_video_metadata", fake_extract)


def _import_video(
    import_path: Path,
    import_dir: Path,
    originals_dir: Path,
) -> tuple[Media, MediaItem, VideoMetadata]:
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


@pytest.fixture
def playback_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """テスト用の再生ファイルディレクトリを用意する。"""

    play_dir = tmp_path / "playback"
    play_dir.mkdir()
    monkeypatch.setenv("FPV_NAS_PLAY_DIR", str(play_dir))
    return play_dir


@pytest.mark.usefixtures("app_context")
def test_local_import_mp4_video(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, playback_dir: Path
) -> None:
    """MP4ファイルがローカルインポート経由で正しく登録されることを検証する。"""

    import_dir = tmp_path / "import"
    originals_dir = tmp_path / "originals"
    import_dir.mkdir()
    originals_dir.mkdir()

    test_video = import_dir / "test_video.mp4"
    create_test_video(test_video)

    _stub_playback_success(monkeypatch, playback_dir)
    media, media_item, _ = _import_video(test_video, import_dir, originals_dir)

    assert media.is_video is True
    assert media.mime_type == "video/mp4"
    assert media.filename == "test_video.mp4"
    assert media.local_rel_path.endswith(".mp4")
    assert media_item.filename == "test_video.mp4"


@pytest.mark.usefixtures("app_context")
def test_local_import_mov_video(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, playback_dir: Path
) -> None:
    """QuickTime(MOV)ファイルもローカルインポートで処理できることを確認する。"""

    import_dir = tmp_path / "import"
    originals_dir = tmp_path / "originals"
    import_dir.mkdir()
    originals_dir.mkdir()

    test_video = import_dir / "TestClip.MOV"
    create_test_video(test_video)

    _stub_playback_success(monkeypatch, playback_dir)
    media, media_item, _ = _import_video(test_video, import_dir, originals_dir)

    assert media.is_video is True
    assert media.mime_type == "video/quicktime"
    assert media.filename == "TestClip.MOV"
    assert media.local_rel_path.endswith(".mov")
    assert media_item.filename == "TestClip.MOV"


@pytest.mark.usefixtures("app_context")
def test_video_shot_at_from_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    playback_dir: Path,
) -> None:
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
    _stub_playback_success(monkeypatch, playback_dir)

    media, _, _ = _import_video(test_video, import_dir, originals_dir)

    assert media.shot_at == expected_shot_at.replace(tzinfo=None)


@pytest.mark.usefixtures("app_context")
def test_local_import_video_playback_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, playback_dir: Path
) -> None:
    """再生ファイル生成に失敗した場合にエラーになることを検証する。"""

    import_dir = tmp_path / "import"
    originals_dir = tmp_path / "originals"
    import_dir.mkdir()
    originals_dir.mkdir()

    test_video = import_dir / "FailVideo.mp4"
    create_test_video(test_video)

    _stub_playback_failure(monkeypatch, note="ffmpeg_missing")

    result = import_single_file(str(test_video), str(import_dir), str(originals_dir))

    assert result["success"] is False
    assert "ffmpeg_missing" in result["reason"]
    # 元ファイルは削除されず残っていることを確認
    assert test_video.exists()


@pytest.mark.usefixtures("app_context")
def test_duplicate_video_regenerates_thumbnails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, playback_dir: Path
) -> None:
    """重複動画の再取り込み時にサムネイルが再生成されることを検証する。"""

    import_dir = tmp_path / "import"
    originals_dir = tmp_path / "originals"
    import_dir.mkdir()
    originals_dir.mkdir()

    test_video = import_dir / "DupThumb.mp4"
    create_test_video(test_video)

    _stub_playback_success(monkeypatch, playback_dir)
    _stub_video_metadata(monkeypatch)

    thumb_calls: list[tuple[int, bool]] = []

    def fake_thumbs_generate(*, media_id: int, force: bool = False) -> dict:
        thumb_calls.append((media_id, force))
        return {"ok": True, "generated": [256], "skipped": [], "notes": None}

    monkeypatch.setattr(local_import_module, "thumbs_generate", fake_thumbs_generate)

    first = import_single_file(str(test_video), str(import_dir), str(originals_dir))
    assert first["success"] is True
    assert not thumb_calls

    # 重複検出用に同じファイルを再生成
    create_test_video(test_video)

    second = import_single_file(str(test_video), str(import_dir), str(originals_dir))
    assert second["success"] is False
    assert "重複ファイル" in second["reason"]

    assert len(thumb_calls) == 1
    assert thumb_calls[0] == (first["media_id"], True)
