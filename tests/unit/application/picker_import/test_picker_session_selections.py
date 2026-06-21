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
        "MEDIA_TEMP_DIRECTORY": str(tmp_dir),
        "MEDIA_ORIGINALS_DIRECTORY": str(orig_dir),
    }
    prev = {k: os.environ.get(k) for k in env}
    os.environ.update(env)

    # webapp / webapp.config を reload しない。create_app は DATABASE_URI を runtime に
    # 再解決し、settings は env を遅延参照するため reload は不要。reload(webapp) は
    # シム submodule の identity を分岐させ、後続テストの monkeypatch を無効化する。
    from webapp.config import BaseApplicationSettings
    BaseApplicationSettings.SQLALCHEMY_ENGINE_OPTIONS = {}
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
    # webapp / webapp.config を sys.modules から削除すると、後続テストが参照する
    # シム submodule（例: webapp.api.picker_session）の identity が変わり
    # monkeypatch が効かなくなる。reload は in-place で identity を保つため del しない。
    for k, v in prev.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def _create_selection(app):
    import uuid
    from webapp.extensions import db
    from core.models.photo_models import MediaItem, PickerSelection
    from core.models.picker_session import PickerSession
    with app.app_context():
        # 数値IDによる参照はセキュリティ上廃止されたため、session_id を割り当てる
        sess_id = f"picker_sessions/{uuid.uuid4().hex}"
        ps = PickerSession(account_id=1, status="pending", session_id=sess_id)
        db.session.add(ps)
        mi = MediaItem(id="m1", mime_type="image/jpeg", filename="a.jpg", type="PHOTO")
        db.session.add(mi)
        db.session.flush()
        sel = PickerSelection(session_id=ps.id, google_media_id="m1", status="pending")
        db.session.add(sel)
        db.session.commit()
    return sess_id


def _login_client(client):
    from flask import session as flask_session
    from flask_login import login_user
    from core.models.user import User
    from webapp.services.token_service import TokenService

    with client.application.test_request_context():
        user = User.query.first()
        principal = TokenService.create_principal_for_user(user)
        login_user(principal)
        flask_session["_fresh"] = True
        persisted = dict(flask_session)

    with client.session_transaction() as sess:
        sess.update(persisted)
        sess.modified = True


def test_picker_session_selections_endpoint(app):
    sess_id = _create_selection(app)
    client = app.test_client()
    _login_client(client)
    uuid_part = sess_id.split("/", 1)[1]
    resp = client.get(f"/api/picker/session/{uuid_part}/selections")
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
    _login_client(client)
    uuid_part = sess_id.split("/", 1)[1]
    resp = client.get(f"/api/picker/session/{uuid_part}/selections")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["counts"]["pending"] == 1
    assert data["selections"][0]["filename"] == "b.jpg"
