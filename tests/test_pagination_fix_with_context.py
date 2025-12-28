#!/usr/bin/env python3
"""
Flask アプリケーションコンテキストでページネーション修正をテスト
"""
import os
from datetime import datetime, timezone

from webapp import create_app
from core.db import db
from webapp.api.pagination import PaginationParams
from webapp.api.picker_session_service import PickerSessionService
from core.models.picker_session import PickerSession
from core.models.photo_models import Media, MediaItem, PickerSelection


def _restore_env(key: str, original_value: str | None) -> None:
    if original_value is None:
        os.environ.pop(key, None)
    else:
        os.environ[key] = original_value


def test_pagination_fix(tmp_path):
    """Flask アプリケーションコンテキストでページネーション修正をテスト"""

    db_path = tmp_path / "picker_session.db"
    db_uri_key = "DATABASE_URI"
    original_db_uri = os.environ.get(db_uri_key)
    os.environ[db_uri_key] = f"sqlite:///{db_path}"

    try:
        app = create_app()
        app.config.update(
            TESTING=True,
            SQLALCHEMY_DATABASE_URI=os.environ[db_uri_key],
            SQLALCHEMY_ENGINE_OPTIONS={},
        )

        with app.app_context():
            db.create_all()

            now = datetime.now(timezone.utc)

            session = PickerSession(
                session_id="test-session",
                status="processing",
                selected_count=1,
                media_items_set=True,
            )
            session.last_polled_at = now
            session.last_progress_at = now
            db.session.add(session)
            db.session.commit()

            media_item = MediaItem(
                id="media-1",
                type="PHOTO",
                filename="local-file.jpg",
            )
            media_record = Media(
                google_media_id="media-1",
                filename="local-file.jpg",
                source_type="google_photos",
            )
            db.session.add_all([media_item, media_record])
            db.session.commit()

            picker_selection = PickerSelection(
                session_id=session.id,
                google_media_id="media-1",
                status="imported",
                attempts=1,
                enqueued_at=now,
                started_at=now,
                finished_at=now,
                local_filename="local-file.jpg",
            )
            db.session.add(picker_selection)
            db.session.commit()

            params = PaginationParams(page_size=1, use_cursor=True)

            refreshed_session = db.session.get(PickerSession, session.id)
            details = PickerSessionService.selection_details(refreshed_session, params)

            selections = details["selections"]
            assert len(selections) == 1
            selection_data = selections[0]
            assert selection_data["id"] == picker_selection.id
            assert selection_data["googleMediaId"] == "media-1"
            assert selection_data["filename"] == "local-file.jpg"
            assert selection_data["status"] == "imported"
            assert selection_data["attempts"] == 1
            assert selection_data["mediaId"] == media_record.id

            counts = details["counts"]
            assert counts["imported"] == 1

            pagination = details["pagination"]
            assert pagination["hasNext"] is False
            assert pagination["hasPrev"] is False
    finally:
        _restore_env(db_uri_key, original_db_uri)
