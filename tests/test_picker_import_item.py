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


def _setup_item(app, *, mime="image/jpeg", filename="a.jpg", mtype="PHOTO"):
    from webapp.extensions import db
    from core.models.photo_models import MediaItem, PickerSelection
    from core.models.picker_session import PickerSession

    with app.app_context():
        ps = PickerSession(account_id=1, status="pending")
        db.session.add(ps)
        mi = MediaItem(id="m1", mime_type=mime, filename=filename, type=mtype)
        db.session.add(mi)
        db.session.flush()
        pmi = PickerSelection(session_id=ps.id, google_media_id="m1", status="enqueued")
        db.session.add(pmi)
        db.session.commit()
        return ps.id, pmi.id


def test_picker_import_item_imports(monkeypatch, app, tmp_path):
    ps_id, pmi_id = _setup_item(app)

    import importlib
    mod = importlib.import_module("core.tasks.picker_import")

    content = b"hello"
    sha = hashlib.sha256(content).hexdigest()

    def fake_download(url, dest_dir, headers=None):
        path = dest_dir / "dl"
        with open(path, "wb") as fh:
            fh.write(content)
        return mod.Downloaded(path, len(content), sha)

    monkeypatch.setattr(mod, "_download", fake_download)
    monkeypatch.setattr(mod, "_exchange_refresh_token", lambda g, p: ("tok", None))

    class FakeResp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"baseUrl": "http://example/file", "mediaMetadata": {"width": "1", "height": "1"}}

    monkeypatch.setattr(mod.requests, "get", lambda url, headers=None: FakeResp())

    called_thumbs: list[int] = []
    called_play: list[int] = []
    monkeypatch.setattr(mod, "enqueue_thumbs_generate", lambda mid: called_thumbs.append(mid))
    monkeypatch.setattr(mod, "enqueue_media_playback", lambda mid: called_play.append(mid))

    with app.app_context():
        res = picker_import_item(selection_id=pmi_id, session_id=ps_id)
        from core.models.photo_models import PickerSelection, Media

        pmi = PickerSelection.query.get(pmi_id)
        media = Media.query.one()
        assert res["ok"] is True
        assert pmi.status == "imported"
        assert pmi.attempts == 1
        assert pmi.finished_at is not None
        assert pmi.locked_by is None
        assert pmi.lock_heartbeat_at is None
        assert Media.query.count() == 1
        assert called_thumbs == [media.id]
        assert called_play == []


def test_picker_import_item_dup(monkeypatch, app, tmp_path):
    ps_id, pmi_id = _setup_item(app)

    import importlib
    mod = importlib.import_module("core.tasks.picker_import")
    content = b"hello"
    sha = hashlib.sha256(content).hexdigest()

    def fake_download(url, dest_dir, headers=None):
        path = dest_dir / "dl"
        with open(path, "wb") as fh:
            fh.write(content)
        return mod.Downloaded(path, len(content), sha)

    monkeypatch.setattr(mod, "_download", fake_download)
    monkeypatch.setattr(mod, "_exchange_refresh_token", lambda g, p: ("tok", None))

    class FakeResp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"baseUrl": "http://example/file", "mediaMetadata": {"width": "1", "height": "1"}}

    monkeypatch.setattr(mod.requests, "get", lambda url, headers=None: FakeResp())

    called_thumbs: list[int] = []
    called_play: list[int] = []
    monkeypatch.setattr(mod, "enqueue_thumbs_generate", lambda mid: called_thumbs.append(mid))
    monkeypatch.setattr(mod, "enqueue_media_playback", lambda mid: called_play.append(mid))

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
        assert pmi.locked_by is None
        assert pmi.lock_heartbeat_at is None
        assert Media.query.count() == 1
        assert called_thumbs == []
        assert called_play == []


def test_picker_import_item_video_queues_playback(monkeypatch, app, tmp_path):
    ps_id, pmi_id = _setup_item(app, mime="video/mp4", filename="v.mp4", mtype="VIDEO")

    import importlib
    mod = importlib.import_module("core.tasks.picker_import")
    content = b"hello"
    sha = hashlib.sha256(content).hexdigest()

    def fake_download(url, dest_dir, headers=None):
        path = dest_dir / "dl"
        with open(path, "wb") as fh:
            fh.write(content)
        return mod.Downloaded(path, len(content), sha)

    monkeypatch.setattr(mod, "_download", fake_download)
    monkeypatch.setattr(mod, "_exchange_refresh_token", lambda g, p: ("tok", None))

    class FakeResp:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "baseUrl": "http://example/file",
                "mediaMetadata": {"width": "1", "height": "1", "video": {"durationMillis": "1000"}},
            }

    monkeypatch.setattr(mod.requests, "get", lambda url, headers=None: FakeResp())

    called_thumbs: list[int] = []
    called_play: list[int] = []
    monkeypatch.setattr(mod, "enqueue_thumbs_generate", lambda mid: called_thumbs.append(mid))
    monkeypatch.setattr(mod, "enqueue_media_playback", lambda mid: called_play.append(mid))

    with app.app_context():
        res = picker_import_item(selection_id=pmi_id, session_id=ps_id)
        from core.models.photo_models import PickerSelection, Media

        pmi = PickerSelection.query.get(pmi_id)
        media = Media.query.one()
        assert res["ok"] is True
        assert pmi.status == "imported"
        assert media.is_video is True
        assert called_thumbs == []
        assert called_play == [media.id]


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

    heartbeat_vals: list = []

    def fake_download(url, dest_dir, headers=None):
        path = dest_dir / "dl"
        with open(path, "wb") as fh:
            fh.write(content)
        time.sleep(0.05)
        from core.models.photo_models import PickerSelection as PS
        heartbeat_vals.append(PS.query.get(pmi_id).lock_heartbeat_at)
        return mod.Downloaded(path, len(content), sha)

    monkeypatch.setattr(mod, "_download", fake_download)
    monkeypatch.setattr(mod, "_exchange_refresh_token", lambda g, p: ("tok", None))

    class FakeResp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"baseUrl": "http://example/file", "mediaMetadata": {"width": "1", "height": "1"}}

    monkeypatch.setattr(mod.requests, "get", lambda url, headers=None: FakeResp())
    monkeypatch.setattr(mod, "enqueue_thumbs_generate", lambda mid: None)
    monkeypatch.setattr(mod, "enqueue_media_playback", lambda mid: None)

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
        assert heartbeat_vals[0] is not None
        assert pmi.locked_by is None
        assert pmi.lock_heartbeat_at is None
        assert pmi.attempts == 1
        assert pmi.started_at is not None
        assert pmi.finished_at is not None
