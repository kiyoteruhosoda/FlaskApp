import hashlib
import os
import time

import pytest

from core.tasks import picker_import_item, picker_import_queue_scan


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
        "FPV_TMP_DIR": str(tmp_dir),
        "FPV_NAS_ORIG_DIR": str(orig_dir),
    }
    prev = {k: os.environ.get(k) for k in env}
    os.environ.update(env)

    import importlib, sys
    import webapp.config as config_module
    importlib.reload(config_module)
    import webapp as webapp_module
    importlib.reload(webapp_module)
    from webapp.config import Config
    Config.SQLALCHEMY_ENGINE_OPTIONS = {}
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
        pmi = PickerSelection(session_id=ps.id, google_media_id="m1", status="enqueued", base_url="http://example/file")
        db.session.add(pmi)
        db.session.commit()
        return ps.id, pmi.id


def test_picker_import_item_imports(monkeypatch, app, tmp_path):
    ps_id, pmi_id = _setup_item(app)

    # fake download
    import importlib
    mod = importlib.import_module("core.tasks.picker_import")

    content = b"hello"
    sha = hashlib.sha256(content).hexdigest()

    def fake_download(url, dest_dir):
        path = dest_dir / "dl"
        with open(path, "wb") as fh:
            fh.write(content)
        return mod.Downloaded(path, len(content), sha)

    monkeypatch.setattr(mod, "_download", fake_download)

    with app.app_context():
        res = picker_import_item(selection_id=pmi_id, session_id=ps_id)
        from core.models.photo_models import PickerSelection, Media

        pmi = PickerSelection.query.get(pmi_id)
        assert res["ok"] is True
        assert pmi.status == "imported"
        assert pmi.attempts == 1
        assert pmi.finished_at is not None
        assert Media.query.count() == 1


def test_picker_import_item_dup(monkeypatch, app, tmp_path):
    ps_id, pmi_id = _setup_item(app)

    import importlib
    mod = importlib.import_module("core.tasks.picker_import")
    content = b"hello"
    sha = hashlib.sha256(content).hexdigest()

    def fake_download(url, dest_dir):
        path = dest_dir / "dl"
        with open(path, "wb") as fh:
            fh.write(content)
        return mod.Downloaded(path, len(content), sha)

    monkeypatch.setattr(mod, "_download", fake_download)

    # pre-create media with same hash
    from core.models.photo_models import Media
    from webapp.extensions import db
    from datetime import datetime, timezone

    with app.app_context():
        m = Media(
            google_media_id="x",
            account_id=1,
            local_rel_path="x",
            hash_sha256=sha,
            bytes=len(content),
            mime_type="image/jpeg",
            width=None,
            height=None,
            duration_ms=None,
            shot_at=datetime.now(timezone.utc),
            imported_at=datetime.now(timezone.utc),
            is_video=False,
        )
        db.session.add(m)
        db.session.commit()

        res = picker_import_item(selection_id=pmi_id, session_id=ps_id)
        from core.models.photo_models import PickerSelection
        pmi = PickerSelection.query.get(pmi_id)
        assert res["ok"] is True
        assert pmi.status == "dup"
        assert Media.query.count() == 1


def test_picker_import_queue_scan(monkeypatch, app):
    ps_id, pmi_id = _setup_item(app)

    called: list[int] = []

    import importlib
    mod = importlib.import_module("core.tasks.picker_import")

    def fake_enqueue(selection_id):
        called.append(selection_id)

    monkeypatch.setattr(mod, "enqueue_picker_import_item", fake_enqueue)

    with app.app_context():
        res = picker_import_queue_scan()
        assert res["queued"] == 1
        assert called == [pmi_id]


def test_picker_import_item_heartbeat(monkeypatch, app, tmp_path):
    ps_id, pmi_id = _setup_item(app)

    import importlib
    mod = importlib.import_module("core.tasks.picker_import")

    content = b"hi"
    sha = hashlib.sha256(content).hexdigest()

    def fake_download(url, dest_dir):
        path = dest_dir / "dl"
        with open(path, "wb") as fh:
            fh.write(content)
        time.sleep(0.05)
        return mod.Downloaded(path, len(content), sha)

    monkeypatch.setattr(mod, "_download", fake_download)

    with app.app_context():
        res = picker_import_item(
            selection_id=pmi_id,
            session_id=ps_id,
            locked_by="w1",
            heartbeat_interval=0.01,
        )
        from core.models.photo_models import PickerSelection

        pmi = PickerSelection.query.get(pmi_id)
        assert res["ok"] is True
        assert pmi.locked_by == "w1"
        assert pmi.attempts == 1
        assert pmi.started_at is not None
        assert pmi.lock_heartbeat_at is not None
        diff = (pmi.lock_heartbeat_at - pmi.started_at).total_seconds()
        assert diff >= 0.01
