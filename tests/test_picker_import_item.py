import hashlib
import os
import time
from datetime import datetime, timezone, timedelta

import requests

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
        "FPV_NAS_ORIGINALS_DIR": str(orig_dir),
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
    monkeypatch.setattr(mod, "enqueue_media_playback", lambda mid, **kwargs: called_play.append(mid))

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
        assert media.source_type == "google_photos"
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
    monkeypatch.setattr(mod, "enqueue_media_playback", lambda mid, **kwargs: called_play.append(mid))

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
        assert pmi.finished_at is not None
        assert pmi.locked_by is None
        assert pmi.lock_heartbeat_at is None
        assert Media.query.count() == 1
        assert called_thumbs == []
        assert called_play == []


def test_picker_import_item_reimports_deleted_media(monkeypatch, app, tmp_path):
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
    monkeypatch.setattr(mod, "enqueue_media_playback", lambda mid, **kwargs: called_play.append(mid))

    from core.models.photo_models import Media
    from webapp.extensions import db
    from datetime import datetime, timezone

    with app.app_context():
        Media.query.delete()
        db.session.commit()

        deleted_media = Media(
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
            is_deleted=True,
        )
        db.session.add(deleted_media)
        db.session.commit()

        res = picker_import_item(selection_id=pmi_id, session_id=ps_id)
        from core.models.photo_models import PickerSelection

        pmi = PickerSelection.query.get(pmi_id)
        assert res["ok"] is True
        assert pmi.status == "imported"
        assert Media.query.filter_by(is_deleted=False).count() == 1
        new_media = Media.query.filter_by(is_deleted=False).one()
        assert new_media.hash_sha256 == sha
        assert Media.query.count() == 2
        assert called_thumbs == [new_media.id]
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
    monkeypatch.setattr(mod, "enqueue_media_playback", lambda mid, **kwargs: called_play.append(mid))

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

    def fake_enqueue(selection_id, session_id):
        called.append((selection_id, session_id))

    monkeypatch.setattr(mod, "enqueue_picker_import_item", fake_enqueue)

    with app.app_context():
        res = picker_import_queue_scan()
        assert res["queued"] == 1
        assert called == [(pmi_id, ps_id)]


def test_picker_import_queue_scan_skips_local(app):
    from webapp.extensions import db
    from core.models.photo_models import PickerSelection
    from core.models.picker_session import PickerSession

    with app.app_context():
        session = PickerSession(account_id=None, status="importing")
        db.session.add(session)
        db.session.flush()

        local_selection = PickerSelection(
            session_id=session.id,
            google_media_id=None,
            local_file_path="/tmp/example.jpg",
            status="enqueued",
        )
        db.session.add(local_selection)
        db.session.commit()

        res = picker_import_queue_scan()
        assert res["queued"] == 0


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
    monkeypatch.setattr(mod, "enqueue_media_playback", lambda mid, **kwargs: None)

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


def test_picker_import_item_reresolves_expired_base_url(monkeypatch, app, tmp_path):
    ps_id, pmi_id = _setup_item(app)

    import importlib
    mod = importlib.import_module("core.tasks.picker_import")

    from webapp.extensions import db
    from core.models.photo_models import PickerSelection
    from core.models.picker_session import PickerSession
    with app.app_context():
        pmi = PickerSelection.query.get(pmi_id)
        pmi.base_url = "http://old"
        pmi.base_url_fetched_at = datetime.now(timezone.utc) - timedelta(hours=2)
        pmi.base_url_valid_until = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.session.commit()
        before = PickerSession.query.get(ps_id).last_progress_at

    monkeypatch.setattr(mod, "_exchange_refresh_token", lambda g, p: ("tok", None))

    def fake_get(url, headers=None):
        class Resp:
            def raise_for_status(self):
                return None

            def json(self):
                return {"baseUrl": "http://new", "mediaMetadata": {"width": "1", "height": "1"}}

        assert url.endswith("mediaItems/m1")
        return Resp()

    monkeypatch.setattr(mod.requests, "get", fake_get)
    content = b"hi"
    sha = hashlib.sha256(content).hexdigest()

    def fake_download(url, dest_dir, headers=None):
        assert url.startswith("http://new")
        path = dest_dir / "dl"
        with open(path, "wb") as fh:
            fh.write(content)
        return mod.Downloaded(path, len(content), sha)

    monkeypatch.setattr(mod, "_download", fake_download)
    monkeypatch.setattr(mod, "enqueue_thumbs_generate", lambda mid: None)
    monkeypatch.setattr(mod, "enqueue_media_playback", lambda mid, **kwargs: None)

    with app.app_context():
        res = picker_import_item(selection_id=pmi_id, session_id=ps_id)
        pmi = PickerSelection.query.get(pmi_id)
        ps = PickerSession.query.get(ps_id)
        assert res["status"] == "imported"
        assert pmi.base_url == "http://new"
        assert pmi.base_url_valid_until is not None
        assert ps.last_progress_at > before


def test_picker_import_item_reresolve_failure_marks_expired(monkeypatch, app, tmp_path):
    ps_id, pmi_id = _setup_item(app)

    import importlib
    mod = importlib.import_module("core.tasks.picker_import")

    from webapp.extensions import db
    from core.models.photo_models import PickerSelection
    from core.models.picker_session import PickerSession
    with app.app_context():
        pmi = PickerSelection.query.get(pmi_id)
        pmi.base_url = "http://old"
        pmi.base_url_valid_until = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.session.commit()
        before = PickerSession.query.get(ps_id).last_progress_at

    monkeypatch.setattr(mod, "_exchange_refresh_token", lambda g, p: ("tok", None))

    class Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {}

    monkeypatch.setattr(mod.requests, "get", lambda url, headers=None: Resp())
    monkeypatch.setattr(mod, "_download", lambda url, dest_dir, headers=None: None)
    monkeypatch.setattr(mod, "enqueue_thumbs_generate", lambda mid: None)
    monkeypatch.setattr(mod, "enqueue_media_playback", lambda mid, **kwargs: None)

    with app.app_context():
        res = picker_import_item(selection_id=pmi_id, session_id=ps_id)
        pmi = PickerSelection.query.get(pmi_id)
        ps = PickerSession.query.get(ps_id)
        assert res["status"] == "expired"
        assert pmi.status == "expired"
        assert ps.last_progress_at > before


def test_picker_import_item_network_error_requeues(monkeypatch, app, tmp_path):
    ps_id, pmi_id = _setup_item(app)

    import importlib
    mod = importlib.import_module("core.tasks.picker_import")

    monkeypatch.setattr(mod, "_exchange_refresh_token", lambda g, p: ("tok", None))

    class FakeResp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"baseUrl": "http://example/file", "mediaMetadata": {"width": "1", "height": "1"}}

    monkeypatch.setattr(mod.requests, "get", lambda url, headers=None: FakeResp())

    def fail_download(url, dest_dir, headers=None):
        raise requests.exceptions.ConnectionError()

    monkeypatch.setattr(mod, "_download", fail_download)
    monkeypatch.setattr(mod, "enqueue_thumbs_generate", lambda mid: None)
    monkeypatch.setattr(mod, "enqueue_media_playback", lambda mid, **kwargs: None)

    with app.app_context():
        from core.models.picker_session import PickerSession
        before = PickerSession.query.get(ps_id).last_progress_at
        res = picker_import_item(selection_id=pmi_id, session_id=ps_id)
        from core.models.photo_models import PickerSelection
        pmi = PickerSelection.query.get(pmi_id)
        ps = PickerSession.query.get(ps_id)
        assert res["status"] == "enqueued"
        assert pmi.finished_at is None
        assert ps.last_progress_at == before


def test_picker_import_item_auth_error_fails(monkeypatch, app, tmp_path):
    ps_id, pmi_id = _setup_item(app)

    import importlib
    mod = importlib.import_module("core.tasks.picker_import")

    monkeypatch.setattr(mod, "_exchange_refresh_token", lambda g, p: (None, "oauth_failed"))

    with app.app_context():
        from core.models.picker_session import PickerSession
        before = PickerSession.query.get(ps_id).last_progress_at
        res = picker_import_item(selection_id=pmi_id, session_id=ps_id)
        from core.models.photo_models import PickerSelection
        pmi = PickerSelection.query.get(pmi_id)
        ps = PickerSession.query.get(ps_id)
        assert res["status"] == "failed"
        assert pmi.finished_at is not None
        assert ps.last_progress_at > before
