import logging
import shutil
from datetime import datetime, timezone
from typing import Dict, Any

import pytest

from application.media_processing.logger import StructuredMediaTaskLogger
from application.media_processing.playback_service import MediaPlaybackService
from core.models.photo_models import Media, MediaPlayback
from webapp.extensions import db


@pytest.mark.usefixtures("app_context")
def test_force_regenerate_resets_mp4_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    """MP4 の再生アセットでも強制再生成時にパスが初期化される。"""

    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/ffmpeg")

    media = Media(
        source_type="local",
        local_rel_path="2025/10/08/sample.mp4",
        filename="sample.mp4",
        mime_type="video/mp4",
        is_video=True,
        has_playback=True,
    )
    db.session.add(media)
    db.session.commit()

    playback = MediaPlayback(
        media_id=media.id,
        preset="std1080p",
        rel_path="2025/10/08/sample.mp4",
        poster_rel_path="2025/10/08/sample.jpg",
        status="done",
    )
    db.session.add(playback)
    db.session.commit()

    observed: list[Dict[str, Any]] = []

    def _fake_worker(*, media_playback_id: int, force: bool = False) -> Dict[str, Any]:
        pb = MediaPlayback.query.get(media_playback_id)
        observed.append(
            {
                "rel_path": pb.rel_path,
                "poster_rel_path": pb.poster_rel_path,
                "status": pb.status,
                "force": force,
            }
        )
        pb.rel_path = "2025/10/08/sample_regen.mp4"
        pb.poster_rel_path = "2025/10/08/sample_regen.jpg"
        pb.status = "done"
        pb.updated_at = datetime.now(timezone.utc)
        db.session.commit()
        return {"ok": True, "note": "regenerated"}

    logger = StructuredMediaTaskLogger(logging.getLogger("test.playback"))
    service = MediaPlaybackService(
        worker=_fake_worker,
        thumbnail_generator=None,
        logger=logger,
    )

    result = service.prepare(media_id=media.id, force_regenerate=True, operation_id="test-op")

    assert result["ok"] is True
    assert observed
    assert observed[0]["rel_path"] is None
    assert observed[0]["poster_rel_path"] is None
    assert observed[0]["status"] == "pending"
    assert observed[0]["force"] is True

    refreshed = MediaPlayback.query.get(playback.id)
    assert refreshed.rel_path == "2025/10/08/sample_regen.mp4"
    assert refreshed.poster_rel_path == "2025/10/08/sample_regen.jpg"


@pytest.mark.usefixtures("app_context")
def test_prepare_forces_regeneration_when_rel_path_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """rel_path 欄が欠落した完了済み再生アセットは自動的に再生成される。"""

    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/ffmpeg")

    media = Media(
        source_type="local",
        local_rel_path="2025/08/18/sample.mov",
        filename="sample.mov",
        mime_type="video/quicktime",
        is_video=True,
        has_playback=False,
    )
    db.session.add(media)
    db.session.commit()

    playback = MediaPlayback(
        media_id=media.id,
        preset="std1080p",
        rel_path=None,
        poster_rel_path="2025/08/18/sample.jpg",
        status="done",
    )
    db.session.add(playback)
    db.session.commit()

    observed: Dict[str, Any] = {}

    def _fake_worker(*, media_playback_id: int, force: bool = False) -> Dict[str, Any]:
        pb = MediaPlayback.query.get(media_playback_id)
        observed["status"] = pb.status
        observed["force"] = force
        observed["rel_path"] = pb.rel_path
        observed["poster_rel_path"] = pb.poster_rel_path
        pb.rel_path = "2025/08/18/sample.mp4"
        pb.poster_rel_path = "2025/08/18/sample_regen.jpg"
        pb.status = "done"
        pb.updated_at = datetime.now(timezone.utc)
        db.session.commit()
        return {"ok": True, "note": "transcoded", "width": 0, "height": 0, "duration_ms": 0}

    logger = StructuredMediaTaskLogger(logging.getLogger("test.playback"))
    service = MediaPlaybackService(
        worker=_fake_worker,
        thumbnail_generator=None,
        logger=logger,
    )

    result = service.prepare(media_id=media.id, operation_id="recover-test")

    assert result["ok"] is True
    assert observed["force"] is True
    assert observed["status"] == "pending"
    assert observed["rel_path"] is None
    assert observed["poster_rel_path"] is None

    refreshed = MediaPlayback.query.get(playback.id)
    assert refreshed.rel_path == "2025/08/18/sample.mp4"
    assert refreshed.poster_rel_path == "2025/08/18/sample_regen.jpg"


@pytest.mark.usefixtures("app_context")
def test_prepare_does_not_restart_processing_playback_without_rel_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """進行中の再生アセットは rel_path 欄が無くても再生成されない。"""

    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/ffmpeg")

    media = Media(
        source_type="local",
        local_rel_path="2025/11/01/sample.mov",
        filename="sample.mov",
        mime_type="video/quicktime",
        is_video=True,
        has_playback=False,
    )
    db.session.add(media)
    db.session.commit()

    playback = MediaPlayback(
        media_id=media.id,
        preset="std1080p",
        rel_path=None,
        poster_rel_path=None,
        status="processing",
    )
    db.session.add(playback)
    db.session.commit()

    invoked: list[Dict[str, Any]] = []

    def _fake_worker(*, media_playback_id: int, force: bool = False) -> Dict[str, Any]:
        invoked.append({"media_playback_id": media_playback_id, "force": force})
        return {"ok": True}

    logger = StructuredMediaTaskLogger(logging.getLogger("test.playback"))
    service = MediaPlaybackService(
        worker=_fake_worker,
        thumbnail_generator=None,
        logger=logger,
    )

    result = service.prepare(media_id=media.id, operation_id="processing-no-rel-path")

    assert result == {
        "ok": False,
        "note": "already_processing",
        "playback_status": "processing",
    }
    assert invoked == []
