from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import inspect


def _create_session(db):
    from core.models.picker_session import PickerSession

    session = PickerSession(session_id=f"session-{uuid4().hex}", status="pending")
    now = datetime.now(timezone.utc)
    session.created_at = now
    session.updated_at = now
    db.session.add(session)
    db.session.commit()
    return session


def test_media_item_flushed_before_selection_insert(app_context, monkeypatch):
    app = app_context

    from webapp.extensions import db
    from webapp.api.picker_session_service import PickerSessionService
    from core.models.photo_models import MediaItem

    with app.app_context():
        session = _create_session(db)

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

        result = PickerSessionService._save_single_item(session, media_item_payload)

        assert result is not None
        assert result.selection.google_media_id == "GOOGLE_MEDIA_ID"


def test_enqueue_new_items_create_import_tasks(app_context, monkeypatch):
    app = app_context

    from webapp.extensions import db
    from webapp.api.picker_session_service import PickerSessionService
    from core.models.photo_models import PickerSelection
    from core.models.picker_import_task import PickerImportTask

    with app.app_context():
        session = _create_session(db)

        selection = PickerSelection(session_id=session.id, status="pending")
        db.session.add(selection)
        db.session.commit()

        import webapp.api.picker_session as ps_module

        queued = []

        def fake_enqueue(selection_id, session_id):
            queued.append((selection_id, session_id))

        monkeypatch.setattr(ps_module, "enqueue_picker_import_item", fake_enqueue)

        PickerSessionService._enqueue_new_items(session, [selection])

        task = db.session.get(PickerImportTask, selection.id)
        assert task is not None
        assert queued == [(selection.id, session.id)]

        # 2回目の呼び出しでも重複登録せずに処理できること
        PickerSessionService._enqueue_new_items(session, [selection])
        all_tasks = db.session.query(PickerImportTask).all()
        assert [t.id for t in all_tasks] == [selection.id]


def test_existing_pending_selection_reenqueued(app_context, monkeypatch):
    app = app_context

    from webapp.extensions import db
    from webapp.api.picker_session_service import PickerSessionService
    from core.models.photo_models import PickerSelection
    from core.models.picker_import_task import PickerImportTask

    with app.app_context():
        session = _create_session(db)

        selection = PickerSelection(
            session_id=session.id,
            google_media_id="GOOGLE_MEDIA_ID",
            status="pending",
        )
        db.session.add(selection)
        db.session.commit()

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

        saved, dup, new_pmis = PickerSessionService._save_media_items(
            session, [media_item_payload]
        )

        assert saved == 0
        assert dup == 0
        assert [pmi.id for pmi in new_pmis] == [selection.id]

        import webapp.api.picker_session as ps_module

        queued: list[tuple[int | None, int]] = []

        def fake_enqueue(selection_id, session_id):
            queued.append((selection_id, session_id))

        monkeypatch.setattr(ps_module, "enqueue_picker_import_item", fake_enqueue)

        PickerSessionService._enqueue_new_items(session, new_pmis)

        task = db.session.get(PickerImportTask, selection.id)
        assert task is not None
        db.session.refresh(selection)
        assert selection.status == "enqueued"
        assert queued == [(selection.id, session.id)]
