import hashlib
import os

import pytest
from PIL import Image
from pillow_heif import register_heif_opener

from core.tasks import picker_import_item


@pytest.fixture
def picker_app(tmp_path):
    """Create an application instance configured for picker import tests."""

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
    prev_env = {key: os.environ.get(key) for key in env}
    os.environ.update(env)

    import importlib
    import sys

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
        account = GoogleAccount(email="acc@example.com", scopes="", oauth_token_json="{}")
        db.session.add(account)
        db.session.commit()

    yield app

    with app.app_context():
        db.session.remove()
        db.drop_all()

    sys.modules.pop("webapp.config", None)
    sys.modules.pop("webapp", None)

    for key, value in prev_env.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def _setup_item(app, *, mime="image/jpeg", filename="a.jpg", mtype="PHOTO"):
    from webapp.extensions import db
    from core.models.photo_models import MediaItem, PickerSelection
    from core.models.picker_session import PickerSession

    with app.app_context():
        picker_session = PickerSession(account_id=1, status="pending")
        db.session.add(picker_session)
        media_item = MediaItem(id="m1", mime_type=mime, filename=filename, type=mtype)
        db.session.add(media_item)
        db.session.flush()
        selection = PickerSelection(session_id=picker_session.id, google_media_id="m1", status="enqueued")
        db.session.add(selection)
        db.session.commit()
        return picker_session.id, selection.id


def test_picker_import_heic_dimensions(monkeypatch, picker_app):
    """HEICメディアの寸法がダウンロードファイルから補完されることを検証。"""

    register_heif_opener()

    ps_id, pmi_id = _setup_item(picker_app, mime="image/heic", filename="image.heic")

    import importlib

    mod = importlib.import_module("core.tasks.picker_import")

    width, height = 48, 32

    def fake_download(url, dest_dir, headers=None):
        path = dest_dir / "dl.heic"
        Image.new("RGB", (width, height), "white").save(path, format="HEIF")
        data = path.read_bytes()
        return mod.Downloaded(path, len(data), hashlib.sha256(data).hexdigest())

    monkeypatch.setattr(mod, "_download", fake_download)
    monkeypatch.setattr(mod, "_exchange_refresh_token", lambda g, p: ("tok", None))

    class FakeResp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"baseUrl": "http://example/file", "mediaMetadata": {}}

    def fake_requests_get(url, headers=None, timeout=None):
        return FakeResp()

    monkeypatch.setattr(mod.requests, "get", fake_requests_get)

    called_thumbs: list[int] = []
    called_play: list[int] = []

    from core.tasks import media_post_processing as mpp

    monkeypatch.setattr(
        mpp,
        "enqueue_thumbs_generate",
        lambda media_id, **kwargs: called_thumbs.append(media_id),
    )
    monkeypatch.setattr(
        mpp,
        "enqueue_media_playback",
        lambda media_id, **kwargs: called_play.append(media_id),
    )

    with picker_app.app_context():
        result = picker_import_item(selection_id=pmi_id, session_id=ps_id)

        from core.models.photo_models import Media, MediaItem, PickerSelection

        selection = PickerSelection.query.get(pmi_id)
        media = Media.query.one()
        media_item = MediaItem.query.get("m1")

        assert result["ok"] is True
        assert selection.status == "imported"
        assert media.mime_type == "image/heic"
        assert media.width == width
        assert media.height == height
        assert media_item.width == width
        assert media_item.height == height
        assert called_thumbs == [media.id]
        assert called_play == []
