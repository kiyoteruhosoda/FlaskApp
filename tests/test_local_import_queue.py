import pytest
from unittest.mock import MagicMock

from features.photonest.application.local_import.queue import LocalImportQueueProcessor
from core.models.photo_models import Media, MediaItem, PickerSelection
from core.models.picker_session import PickerSession


@pytest.fixture
def db_session(app_context):
    from webapp.extensions import db

    return db.session


@pytest.mark.usefixtures("app_context")
def test_assign_google_media_id_skips_conflict(db_session):
    from webapp.extensions import db

    processor = LocalImportQueueProcessor(
        db=db,
        logger=MagicMock(),
        importer=None,
        cancel_requested=lambda *args, **kwargs: False,
    )

    picker_session = PickerSession(status="pending")
    db_session.add(picker_session)
    db_session.commit()

    existing = PickerSelection(
        session_id=picker_session.id,
        google_media_id="local_existing",
        local_file_path="/import/file1.jpg",
        local_filename="file1.jpg",
        status="dup",
    )
    target = PickerSelection(
        session_id=picker_session.id,
        local_file_path="/import/file2.jpg",
        local_filename="file2.jpg",
        status="running",
    )
    db_session.add_all([existing, target])
    db_session.commit()

    logger = processor._logger

    assigned = processor._assign_google_media_id(
        target,
        "local_existing",
        {"file": "file2.jpg"},
    )

    assert assigned is False
    assert target.google_media_id is None
    logger.warning.assert_called_once()

    logger.warning.reset_mock()

    assigned = processor._assign_google_media_id(
        target,
        "local_unique",
        {"file": "file2.jpg"},
    )

    assert assigned is True
    assert target.google_media_id == "local_unique"
    logger.warning.assert_not_called()

    db_session.commit()


@pytest.mark.usefixtures("app_context")
def test_assign_google_media_id_resequences_on_conflict(db_session):
    from webapp.extensions import db

    processor = LocalImportQueueProcessor(
        db=db,
        logger=MagicMock(),
        importer=None,
        cancel_requested=lambda *args, **kwargs: False,
    )

    picker_session = PickerSession(status="pending")
    db_session.add(picker_session)

    media_item = MediaItem(
        id="local_existing",
        type="PHOTO",
        filename="file1.jpg",
    )
    media = Media(google_media_id="local_existing", filename="file1.jpg")
    db_session.add_all([media_item, media])
    db_session.flush()

    existing = PickerSelection(
        session_id=picker_session.id,
        google_media_id="local_existing",
        local_file_path="/import/file1.jpg",
        local_filename="file1.jpg",
        status="imported",
    )
    existing.media_item = media_item
    target = PickerSelection(
        session_id=picker_session.id,
        local_file_path="/import/file2.jpg",
        local_filename="file2.jpg",
        status="running",
    )

    db_session.add_all([existing, target])
    db_session.commit()

    assigned = processor._assign_google_media_id(
        target,
        "local_existing",
        {"file": "file2.jpg"},
        media_id=media.id,
        resequence_on_conflict=True,
    )

    assert assigned is True
    assert target.google_media_id != "local_existing"
    assert media.google_media_id == target.google_media_id
    assert target.media_item is not None
    assert target.media_item.id == target.google_media_id
    db_session.flush()
    assert db_session.get(MediaItem, target.google_media_id) is not None
    assert db_session.get(MediaItem, "local_existing") is not None
    # 既存 Selection 側は元の ID を保持する
    refreshed_existing = db_session.get(PickerSelection, existing.id)
    assert refreshed_existing.google_media_id == "local_existing"
