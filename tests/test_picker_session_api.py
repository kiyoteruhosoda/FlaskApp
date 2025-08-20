import base64
import json
import os
import uuid

import pytest

from core.crypto import encrypt


@pytest.fixture
def app(tmp_path):
    db_path = tmp_path / "test.db"
    db_uri = f"sqlite:///{db_path}"
    os.environ["SECRET_KEY"] = "test"
    os.environ["DATABASE_URI"] = db_uri
    os.environ["GOOGLE_CLIENT_ID"] = "cid"
    os.environ["GOOGLE_CLIENT_SECRET"] = "sec"
    key = base64.urlsafe_b64encode(b"0" * 32).decode()
    os.environ["OAUTH_TOKEN_KEY"] = key
    from webapp.config import Config
    Config.SQLALCHEMY_ENGINE_OPTIONS = {}
    from webapp import create_app
    app = create_app()
    app.config.update(TESTING=True)
    from webapp.extensions import db
    from core.models.user import User
    from core.models.google_account import GoogleAccount
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(email="u@example.com").first():
            u = User(email="u@example.com")
            u.set_password("pass")
            db.session.add(u)
        if not GoogleAccount.query.filter_by(email="g@example.com").first():
            acc = GoogleAccount(
                email="g@example.com",
                scopes="",
                oauth_token_json=encrypt(json.dumps({"refresh_token": "r"})),
            )
            db.session.add(acc)
        db.session.commit()
    yield app


@pytest.fixture
def client(app):
    return app.test_client()


class FakeResp:
    def __init__(self, data, status=200):
        self._data = data
        self.status_code = status

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception("error")


def login(client, app):
    from core.models.user import User
    with app.app_context():
        user = User.query.first()
    client.post(
        "/auth/login",
        data={"email": user.email, "password": "pass"},
        follow_redirects=True,
    )


def test_create_ok(monkeypatch, client, app):
    login(client, app)

    def fake_post(url, *a, **k):
        if url == "https://oauth2.googleapis.com/token":
            return FakeResp({"access_token": "acc"})
        if url == "https://photospicker.googleapis.com/v1/sessions":
            sid = "picker_sessions/" + uuid.uuid4().hex
            return FakeResp({
                "sessionId": sid,
                "pickerUri": "https://picker",
                "expireTime": "2025-03-10T00:00:00Z",
                "pollingConfig": {"pollInterval": "3s", "timeoutIn": "30s"},
                "pickingConfig": {"maxItemCount": "5"},
                "mediaItemsSet": False,
            })
        raise AssertionError("unexpected url" + url)

    monkeypatch.setattr("requests.post", fake_post)
    res = client.post("/api/picker/session", json={"account_id": 1})
    assert res.status_code == 200
    data = res.get_json()
    assert data["pickerSessionId"] > 0
    assert data["sessionId"]
    assert data["pickerUri"]
    assert data["expireTime"]
    assert "pollInterval" in data["pollingConfig"]
    with client.session_transaction() as sess:
        assert sess["picker_session_id"] == data["pickerSessionId"]
    from core.models.picker_session import PickerSession
    with app.app_context():
        ps = PickerSession.query.get(data["pickerSessionId"])
        assert ps.expire_time is not None


def test_create_default_account(monkeypatch, client, app):
    login(client, app)

    def fake_post(url, *a, **k):
        if url == "https://oauth2.googleapis.com/token":
            return FakeResp({"access_token": "acc"})
        if url == "https://photospicker.googleapis.com/v1/sessions":
            sid = "picker_sessions/" + uuid.uuid4().hex
            return FakeResp({
                "sessionId": sid,
                "pickerUri": "https://picker",
                "expireTime": "2025-03-10T00:00:00Z",
                "pollingConfig": {"pollInterval": "3s", "timeoutIn": "30s"},
                "pickingConfig": {"maxItemCount": "5"},
                "mediaItemsSet": False,
            })
        raise AssertionError("unexpected url" + url)

    monkeypatch.setattr("requests.post", fake_post)
    res = client.post("/api/picker/session")
    assert res.status_code == 200
    data = res.get_json()
    assert data["pickerSessionId"] > 0
    assert data["sessionId"]
    assert data["pickerUri"]
    assert data["expireTime"]


def test_create_account_not_found(monkeypatch, client, app):
    login(client, app)
    res = client.post("/api/picker/session", json={"account_id": 999})
    assert res.status_code == 404


def test_create_oauth_error(monkeypatch, client, app):
    login(client, app)

    def fake_post(url, *a, **k):
        if url == "https://oauth2.googleapis.com/token":
            return FakeResp({"error": "invalid_grant"})
        raise AssertionError("unexpected url" + url)

    monkeypatch.setattr("requests.post", fake_post)
    res = client.post("/api/picker/session", json={"account_id": 1})
    assert res.status_code == 401 or res.status_code == 502


def test_status_ok(monkeypatch, client, app):
    login(client, app)

    def fake_post(url, *a, **k):
        if url == "https://oauth2.googleapis.com/token":
            return FakeResp({"access_token": "acc"})
        if url == "https://photospicker.googleapis.com/v1/sessions":
            sid = "picker_sessions/" + uuid.uuid4().hex
            return FakeResp({
                "sessionId": sid,
                "pickerUri": "https://picker",
                "expireTime": "2025-03-10T00:00:00Z",
                "pollingConfig": {"pollInterval": "3s", "timeoutIn": "30s"},
                "pickingConfig": {"maxItemCount": "5"},
                "mediaItemsSet": False,
            })
        raise AssertionError("unexpected url" + url)

    monkeypatch.setattr("requests.post", fake_post)
    # create session
    res = client.post("/api/picker/session", json={"account_id": 1})
    ps_id = res.get_json()["pickerSessionId"]

    def fake_get(url, *a, **k):
        return FakeResp({"selectedMediaCount": 0})

    monkeypatch.setattr("requests.get", fake_get)
    res = client.get(f"/api/picker/session/{ps_id}")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "pending"
    assert data["serverTimeRFC1123"].endswith("GMT")


def test_status_not_found(monkeypatch, client, app):
    login(client, app)
    res = client.get("/api/picker/session/999")
    assert res.status_code == 404


def test_import_enqueue_ok(monkeypatch, client, app):
    login(client, app)

    def fake_post(url, *a, **k):
        if url == "https://oauth2.googleapis.com/token":
            return FakeResp({"access_token": "acc"})
        if url == "https://photospicker.googleapis.com/v1/sessions":
            sid = "picker_sessions/" + uuid.uuid4().hex
            return FakeResp({
                "sessionId": sid,
                "pickerUri": "https://picker",
                "expireTime": "2025-03-10T00:00:00Z",
                "pollingConfig": {"pollInterval": "3s", "timeoutIn": "30s"},
                "pickingConfig": {"maxItemCount": "5"},
                "mediaItemsSet": False,
            })
        raise AssertionError("unexpected url" + url)

    monkeypatch.setattr("requests.post", fake_post)
    res = client.post("/api/picker/session", json={"account_id": 1})
    ps_id = res.get_json()["pickerSessionId"]
    session_name = res.get_json()["sessionId"]

    res = client.post(f"/api/picker/session/{session_name}/import")
    assert res.status_code == 202
    data = res.get_json()
    assert data["enqueued"] is True
    assert data["celeryTaskId"]
    from core.models.picker_session import PickerSession
    with app.app_context():
        ps = PickerSession.query.get(ps_id)
        assert ps.status == "importing"


def test_import_idempotent(monkeypatch, client, app):
    login(client, app)

    def fake_post(url, *a, **k):
        if url == "https://oauth2.googleapis.com/token":
            return FakeResp({"access_token": "acc"})
        if url == "https://photospicker.googleapis.com/v1/sessions":
            sid = "picker_sessions/" + uuid.uuid4().hex
            return FakeResp({
                "sessionId": sid,
                "pickerUri": "https://picker",
                "expireTime": "2025-03-10T00:00:00Z",
                "pollingConfig": {"pollInterval": "3s", "timeoutIn": "30s"},
                "pickingConfig": {"maxItemCount": "5"},
                "mediaItemsSet": False,
            })
        raise AssertionError("unexpected url" + url)

    monkeypatch.setattr("requests.post", fake_post)
    res = client.post("/api/picker/session", json={"account_id": 1})
    ps_id = res.get_json()["pickerSessionId"]
    session_name = res.get_json()["sessionId"]
    res = client.post(f"/api/picker/session/{session_name}/import")
    assert res.status_code == 202
    res = client.post(f"/api/picker/session/{session_name}/import")
    assert res.status_code == 409


def test_import_not_found(monkeypatch, client, app):
    login(client, app)
    res = client.post("/api/picker/session/999/import", json={"account_id": 1})
    assert res.status_code == 404


def test_callback_stores_ids(monkeypatch, client, app):
    login(client, app)

    class FakeResp:
        def __init__(self, data, status=200):
            self._data = data
            self.status_code = status

        def json(self):
            return self._data

        def raise_for_status(self):
            if self.status_code >= 400:
                raise Exception("error")

    def fake_post(url, *a, **k):
        if url == "https://oauth2.googleapis.com/token":
            return FakeResp({"access_token": "acc"})
        if url == "https://photospicker.googleapis.com/v1/sessions":
            sid = "picker_sessions/" + uuid.uuid4().hex
            return FakeResp({
                "sessionId": sid,
                "pickerUri": "https://picker",
                "expireTime": "2025-03-10T00:00:00Z",
                "pollingConfig": {"pollInterval": "3s", "timeoutIn": "30s"},
                "pickingConfig": {"maxItemCount": "5"},
                "mediaItemsSet": False,
            })
        raise AssertionError("unexpected url" + url)

    monkeypatch.setattr("requests.post", fake_post)
    res = client.post("/api/picker/session", json={"account_id": 1})
    ps_id = res.get_json()["pickerSessionId"]

    payload = {"mediaItemIds": ["m1", "m2"]}
    res = client.post(f"/api/picker/session/{ps_id}/callback", json=payload)
    assert res.status_code == 200
    data = res.get_json()
    assert data["count"] == 2

    from core.models.picker_import_item import PickerImportItem
    from core.models.picker_session import PickerSession
    with app.app_context():
        items = PickerImportItem.query.filter_by(picker_session_id=ps_id).all()
        assert len(items) == 2
        ps = PickerSession.query.get(ps_id)
        assert ps.status == "ready"
        assert ps.selected_count == 2
        assert ps.media_items_set is True

    res = client.get(f"/api/picker/session/{ps_id}")
    assert res.status_code == 200
    status = res.get_json()
    assert status["selectedCount"] == 2
    assert status["status"] == "ready"


def test_media_items_endpoint(monkeypatch, client, app):
    login(client, app)

    class FakeResp:
        def __init__(self, data, status=200):
            self._data = data
            self.status_code = status

        def json(self):
            return self._data

        def raise_for_status(self):
            if self.status_code >= 400:
                raise Exception("error")

    def fake_post(url, *a, **k):
        if url == "https://oauth2.googleapis.com/token":
            return FakeResp({"access_token": "acc"})
        if url == "https://photospicker.googleapis.com/v1/sessions":
            sid = "picker_sessions/" + uuid.uuid4().hex
            return FakeResp({
                "sessionId": sid,
                "pickerUri": "https://picker",
                "expireTime": "2025-03-10T00:00:00Z",
                "pollingConfig": {"pollInterval": "3s"},
                "mediaItemsSet": False,
            })
        raise AssertionError("unexpected url" + url)

    monkeypatch.setattr("requests.post", fake_post)

    res = client.post("/api/picker/session", json={"account_id": 1})
    session_name = res.get_json()["sessionId"]
    cursor = "c1"
    from webapp.extensions import db
    from core.models.picker_session import PickerSession
    with app.app_context():
        ps = PickerSession.query.filter_by(session_id=session_name).first()
        ps.status = "processing"
        db.session.commit()

    def fake_get(url, *a, **k):
        if url == "https://photospicker.googleapis.com/v1/mediaItems":
            params = k.get("params", {})
            assert params.get("sessionId") == session_name
            assert params.get("pageToken") == cursor
            return FakeResp(
                {
                    "mediaItems": [
                        {
                            "id": "m1",
                            "mediaFile": {
                                "baseUrl": "https://base/1",
                                "mimeType": "image/jpeg",
                                "filename": "a.jpg",
                                "mediaFileMetadata": {
                                    "width": "100",
                                    "height": "50",
                                    "photoMetadata": {
                                        "cameraMake": "Canon",
                                        "cameraModel": "EOS",
                                        "focalLength": 10.0,
                                        "apertureFNumber": 2.8,
                                        "isoEquivalent": 100,
                                        "exposureTime": "1/50",
                                    },
                                },
                            },
                        }
                    ],
                    "nextPageToken": "tok",
                }
            )
        raise AssertionError("unexpected url" + url)

    monkeypatch.setattr("requests.get", fake_get)

    res = client.post(
        "/api/picker/session/mediaItems",
        json={"sessionId": session_name, "cursor": cursor},
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["saved"] == 1
    assert data["duplicates"] == 0
    assert data["nextCursor"] == "tok"

    from core.models.photo_models import PickedMediaItem
    with app.app_context():
        pmi = PickedMediaItem.query.get("m1")
        assert pmi is not None
        assert pmi.status == "pending"
        assert pmi.media_file_metadata[0].width == 100


def test_media_items_busy(monkeypatch, client, app):
    login(client, app)
    session_id = "sid"

    from webapp.api import picker_session as ps_module
    lock = ps_module._get_media_items_lock(session_id)
    assert lock.acquire(blocking=False)
    try:
        res = client.post(
            "/api/picker/session/mediaItems", json={"sessionId": session_id}
        )
        assert res.status_code == 409
    finally:
        lock.release()
        ps_module._release_media_items_lock(session_id, lock)
