"""Tests for local import result helpers."""

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.filesystem]

from bounded_contexts.photonest.application.local_import.results import build_thumbnail_task_snapshot
from webapp.extensions import db
from core.models.picker_session import PickerSession
from core.models.photo_models import Media, MediaItem, PickerSelection, MediaPlayback


def _create_basic_session(session_id: str = "local_import_session") -> PickerSession:
    session = PickerSession(
        session_id=session_id,
        account_id=None,
        status="processing",
    )
    db.session.add(session)
    db.session.commit()
    return session


def _create_imported_video(
    session: PickerSession,
    *,
    has_playback: bool,
    playback_status: str | None,
) -> None:
    media_item = MediaItem(id="local-video", type="VIDEO")
    db.session.add(media_item)
    db.session.flush()

    media = Media(
        google_media_id=media_item.id,
        source_type="local",
        local_rel_path="videos/sample.mp4",
        filename="sample.mp4",
        is_video=True,
        has_playback=has_playback,
    )
    db.session.add(media)
    db.session.flush()

    selection = PickerSelection(
        session_id=session.id,
        status="imported",
        google_media_id=media_item.id,
        local_file_path="/import/videos/sample.mp4",
        local_filename="sample.mp4",
    )
    db.session.add(selection)
    db.session.flush()

    if playback_status is not None:
        playback = MediaPlayback(
            media_id=media.id,
            preset="std1080p",
            status=playback_status,
        )
        db.session.add(playback)

    db.session.commit()


def test_snapshot_marks_videos_without_playback_as_completed(app_context):
    session = _create_basic_session()
    _create_imported_video(session, has_playback=False, playback_status=None)

    snapshot = build_thumbnail_task_snapshot(db, session, recorded_entries=None)

    assert snapshot["total"] == 1
    assert snapshot["completed"] == 1
    assert snapshot["pending"] == 0
    assert snapshot["failed"] == 0

    entry = snapshot["entries"][0]
    assert entry["status"] == "completed"
    assert entry["hasPlayback"] is False
    assert entry.get("playbackStatus") is None
    assert entry.get("notes") == "playback_unavailable"


def test_snapshot_keeps_pending_when_playback_processing(app_context):
    session = _create_basic_session("local_import_session_pending")
    _create_imported_video(session, has_playback=True, playback_status="processing")

    snapshot = build_thumbnail_task_snapshot(db, session, recorded_entries=None)

    assert snapshot["total"] == 1
    assert snapshot["pending"] == 1
    entry = snapshot["entries"][0]
    assert entry["status"] == "progress"
    assert entry["playbackStatus"] == "processing"
