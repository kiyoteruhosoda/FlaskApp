import os
import importlib
import sys

import pytest


@pytest.fixture
def app(tmp_path):
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
    from core.models.user import User
    with app.app_context():
        db.create_all()
        acc = GoogleAccount(email="acc@example.com", scopes="", oauth_token_json="{}")
        user = User(email="u@example.com", password_hash="x")
        db.session.add_all([acc, user])
        db.session.commit()
    yield app
    del sys.modules["webapp.config"]
    del sys.modules["webapp"]
    for k, v in prev.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def _create_selection(app):
    from webapp.extensions import db
    from core.models.photo_models import MediaItem, PickerSelection
    from core.models.picker_session import PickerSession
    with app.app_context():
        ps = PickerSession(account_id=1, status="pending")
        db.session.add(ps)
        mi = MediaItem(id="m1", mime_type="image/jpeg", filename="a.jpg", type="PHOTO")
        db.session.add(mi)
        db.session.flush()
        sel = PickerSelection(session_id=ps.id, google_media_id="m1", status="pending")
        db.session.add(sel)
        db.session.commit()
        return ps.id


def test_picker_session_selections_endpoint(app):
    ps_id = _create_selection(app)
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = "1"
        sess["_fresh"] = True
    resp = client.get(f"/api/picker/session/{ps_id}/selections")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["counts"]["pending"] == 1
    assert data["selections"][0]["filename"] == "a.jpg"


def test_picker_session_selections_by_session_id_endpoint(app):
    import uuid
    from webapp.extensions import db
    from core.models.photo_models import MediaItem, PickerSelection
    from core.models.picker_session import PickerSession

    with app.app_context():
        sess_id = f"picker_sessions/{uuid.uuid4().hex}"
        ps = PickerSession(account_id=1, status="pending", session_id=sess_id)
        db.session.add(ps)
        mi = MediaItem(id="m2", mime_type="image/jpeg", filename="b.jpg", type="PHOTO")
        db.session.add(mi)
        db.session.flush()
        sel = PickerSelection(session_id=ps.id, google_media_id="m2", status="pending")
        db.session.add(sel)
        db.session.commit()

    client = app.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = "1"
        sess["_fresh"] = True
    uuid_part = sess_id.split("/", 1)[1]
    resp = client.get(f"/api/picker/session/{uuid_part}/selections")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["counts"]["pending"] == 1
    assert data["selections"][0]["filename"] == "b.jpg"
