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
    assert observed[0]["force"] is True

    refreshed = MediaPlayback.query.get(playback.id)
    assert refreshed.rel_path == "2025/10/08/sample_regen.mp4"
    assert refreshed.poster_rel_path == "2025/10/08/sample_regen.jpg"
