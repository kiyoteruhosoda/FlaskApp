from datetime import datetime, timezone

from sqlalchemy import inspect


def test_media_item_flushed_before_selection_insert(app_context, monkeypatch):
    app = app_context

    from webapp.extensions import db
    from webapp.api.picker_session_service import PickerSessionService
    from core.models.picker_session import PickerSession
    from core.models.photo_models import MediaItem

    with app.app_context():
        session = PickerSession(session_id="session-1", status="pending")
        now = datetime.now(timezone.utc)
        session.created_at = now
        session.updated_at = now
        db.session.add(session)
        db.session.commit()

        original_execute = db.session.execute

        def checking_execute(statement, *args, **kwargs):
            pending_media = [
                obj
                for obj in db.session.identity_map.values()
                if isinstance(obj, MediaItem) and inspect(obj).pending
            ]
            assert (
                not pending_media
            ), "MediaItem must be flushed before inserting PickerSelection"
            return original_execute(statement, *args, **kwargs)

        monkeypatch.setattr(db.session, "execute", checking_execute)

        media_item_payload = {
            "id": "GOOGLE_MEDIA_ID",
            "createTime": "2025-11-01T14:49:31.817Z",
            "mediaFile": {
                "baseUrl": "https://example.invalid/base",
                "mimeType": "image/jpeg",
                "filename": "photo.jpg",
                "mediaFileMetadata": {"width": 1600, "height": 900},
            },
        }

        selection = PickerSessionService._save_single_item(session, media_item_payload)

        assert selection is not None
        assert selection.google_media_id == "GOOGLE_MEDIA_ID"
