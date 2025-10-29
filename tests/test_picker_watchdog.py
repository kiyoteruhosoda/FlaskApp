import os
import logging
from datetime import datetime, timezone, timedelta

import pytest

from core.tasks.picker_import import picker_import_watchdog, backoff


@pytest.fixture
def app(tmp_path):
    """Create a minimal app with temp dirs/database."""
    db_path = tmp_path / "test.db"
    tmp_dir = tmp_path / "tmp"
    orig_dir = tmp_path / "orig"
    tmp_dir.mkdir()
    orig_dir.mkdir()

    env = {
        "SECRET_KEY": "test",
        "DATABASE_URI": f"sqlite:///{db_path}",
        "MEDIA_TEMP_DIRECTORY": str(tmp_dir),
        "MEDIA_ORIGINALS_DIRECTORY": str(orig_dir),
    }
    prev = {k: os.environ.get(k) for k in env}
    os.environ.update(env)

    import importlib, sys
    import webapp.config as config_module
    importlib.reload(config_module)
    import webapp as webapp_module
    importlib.reload(webapp_module)
    from webapp.config import BaseApplicationSettings
    BaseApplicationSettings.SQLALCHEMY_ENGINE_OPTIONS = {}
    from webapp import create_app
    app = create_app()
    app.config.update(TESTING=True)
    from webapp.extensions import db
    from core.models.google_account import GoogleAccount
    with app.app_context():
        db.create_all()
        acc = GoogleAccount(email="acc@example.com", scopes="", oauth_token_json="{}")
        db.session.add(acc)
        db.session.commit()

    yield app
    del sys.modules["webapp.config"]
    del sys.modules["webapp"]
    for k, v in prev.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def _setup_item(app):
    from webapp.extensions import db
    from core.models.photo_models import MediaItem, PickerSelection
    from core.models.picker_session import PickerSession

    with app.app_context():
        ps = PickerSession(account_id=1, status="pending")
        db.session.add(ps)
        mi = MediaItem(id="m1", mime_type="image/jpeg", filename="a.jpg", type="PHOTO")
        db.session.add(mi)
        db.session.flush()
        pmi = PickerSelection(session_id=ps.id, google_media_id="m1", status="enqueued")
        db.session.add(pmi)
        db.session.commit()
        return ps.id, pmi.id


def test_watchdog_handles_stale_running(app):
    ps_id, sel1 = _setup_item(app)

    from webapp.extensions import db
    from core.models.photo_models import PickerSelection, MediaItem

    with app.app_context():
        # create second selection with different media item
        mi = MediaItem(id="m2", mime_type="image/jpeg", filename="b.jpg", type="PHOTO")
        db.session.add(mi)
        db.session.flush()
        sel2_obj = PickerSelection(session_id=ps_id, google_media_id="m2", status="enqueued")
        db.session.add(sel2_obj)
        db.session.commit()
        sel2 = sel2_obj.id

        now = datetime.now(timezone.utc)
        s1 = PickerSelection.query.get(sel1)
        s1.status = "running"
        s1.locked_by = "w1"
        s1.lock_heartbeat_at = now - timedelta(seconds=121)
        s1.started_at = now - timedelta(seconds=121)
        s1.attempts = 1

        s2 = PickerSelection.query.get(sel2)
        s2.status = "running"
        s2.locked_by = "w2"
        s2.lock_heartbeat_at = now - timedelta(seconds=121)
        s2.started_at = now - timedelta(seconds=121)
        s2.attempts = 3
        db.session.commit()

        picker_import_watchdog()

        s1 = PickerSelection.query.get(sel1)
        s2 = PickerSelection.query.get(sel2)
        assert s1.status == "enqueued"
        assert s1.locked_by is None
        assert s1.lock_heartbeat_at is None
        assert s2.status == "failed"
        assert s2.finished_at is not None


def test_watchdog_retries_failed_after_backoff(app):
    ps_id, sel_id = _setup_item(app)

    from webapp.extensions import db
    from core.models.photo_models import PickerSelection

    with app.app_context():
        sel = PickerSelection.query.get(sel_id)
        sel.status = "failed"
        sel.attempts = 2
        sel.last_transition_at = datetime.now(timezone.utc) - backoff(2) - timedelta(seconds=1)
        sel.finished_at = datetime.now(timezone.utc)
        db.session.commit()

        picker_import_watchdog()

        sel = PickerSelection.query.get(sel_id)
        assert sel.status == "enqueued"
        assert sel.finished_at is None


def test_watchdog_republishes_stalled_enqueued(monkeypatch, app, caplog):
    ps_id, sel_id = _setup_item(app)
    import importlib
    mod = importlib.import_module("core.tasks.picker_import")

    called: list[int] = []
    monkeypatch.setattr(
        mod, "enqueue_picker_import_item", lambda sid, sess: called.append(sid)
    )

    from webapp.extensions import db
    from core.models.photo_models import PickerSelection

    with app.app_context():
        sel = PickerSelection.query.get(sel_id)
        sel.enqueued_at = datetime.now(timezone.utc) - timedelta(minutes=6)
        db.session.commit()

        caplog.set_level(logging.WARNING)
        picker_import_watchdog()
        assert called == [sel_id]
        assert any("republished" in r.message for r in caplog.records)
