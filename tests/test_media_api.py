import os
import base64
import json
import hmac
import hashlib
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


@pytest.fixture
def app(tmp_path):
    db_path = tmp_path / "test.db"
    os.environ["SECRET_KEY"] = "test"
    os.environ["DATABASE_URI"] = f"sqlite:///{db_path}"
    os.environ["GOOGLE_CLIENT_ID"] = "cid"
    os.environ["GOOGLE_CLIENT_SECRET"] = "sec"
    key = base64.urlsafe_b64encode(b"0" * 32).decode()
    os.environ["OAUTH_TOKEN_KEY"] = key
    os.environ["FPV_DL_SIGN_KEY"] = base64.urlsafe_b64encode(b"1" * 32).decode()
    os.environ["FPV_URL_TTL_THUMB"] = "600"
    os.environ["FPV_URL_TTL_PLAYBACK"] = "600"
    thumbs = tmp_path / "thumbs"
    play = tmp_path / "play"
    thumbs.mkdir()
    play.mkdir()
    os.environ["FPV_NAS_THUMBS_DIR"] = str(thumbs)
    os.environ["FPV_NAS_PLAY_DIR"] = str(play)
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
    from core.models.user import User
    from core.models.google_account import GoogleAccount

    with app.app_context():
        db.create_all()
        u = User(email="u@example.com")
        u.set_password("pass")
        db.session.add(u)
        db.session.flush()
        acc = GoogleAccount(user_id=u.id, email="g@example.com", scopes="", oauth_token_json="{}")
        db.session.add(acc)
        db.session.commit()

    yield app
    del sys.modules["webapp.config"]
    del sys.modules["webapp"]


@pytest.fixture
def client(app):
    return app.test_client()


def login(client):
    from core.models.user import User

    app = client.application
    with app.app_context():
        user = User.query.first()

    client.post(
        "/auth/login",
        data={"email": user.email, "password": "pass"},
        follow_redirects=True,
    )


def make_token(payload: dict) -> str:
    canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    key = base64.urlsafe_b64decode(os.environ["FPV_DL_SIGN_KEY"])
    sig = hmac.new(key, canonical, hashlib.sha256).digest()
    return (
        base64.urlsafe_b64encode(canonical).rstrip(b"=").decode()
        + "."
        + base64.urlsafe_b64encode(sig).rstrip(b"=").decode()
    )


@pytest.fixture
def seed_media_bulk(app):
    from webapp.extensions import db
    from core.models.photo_models import Media

    base_shot = datetime(2025, 8, 1, tzinfo=timezone.utc)
    base_imp = datetime(2025, 8, 2, tzinfo=timezone.utc)
    with app.app_context():
        for i in range(250):
            m = Media(
                source_type='google_photos',
                google_media_id=f"gm{i}",
                account_id=1,
                local_rel_path=f"{i}.jpg",
                bytes=1,
                mime_type="image/jpeg",
                width=100,
                height=100,
                shot_at=base_shot + timedelta(minutes=i),
                imported_at=base_imp + timedelta(minutes=i),
                is_video=False,
                is_deleted=False,
                has_playback=False,
            )
            db.session.add(m)
        for i in range(5):
            m = Media(
                source_type='google_photos',
                google_media_id=f"del{i}",
                account_id=1,
                local_rel_path=f"del{i}.jpg",
                bytes=1,
                mime_type="image/jpeg",
                width=100,
                height=100,
                shot_at=base_shot + timedelta(minutes=250 + i),
                imported_at=base_imp + timedelta(minutes=250 + i),
                is_video=False,
                is_deleted=True,
                has_playback=False,
            )
            db.session.add(m)
        db.session.commit()
        deleted_ids = [m.id for m in Media.query.filter_by(is_deleted=True).all()]
        return deleted_ids


@pytest.fixture
def seed_media_range(app):
    from webapp.extensions import db
    from core.models.photo_models import Media

    with app.app_context():
        m1 = Media(
            google_media_id="m1",
            account_id=1,
            local_rel_path="m1.jpg",
            bytes=1,
            mime_type="image/jpeg",
            width=1,
            height=1,
            shot_at=datetime(2025, 7, 15, tzinfo=timezone.utc),
            imported_at=datetime(2025, 7, 16, tzinfo=timezone.utc),
            is_video=False,
            is_deleted=False,
            has_playback=False,
        )
        m2 = Media(
            google_media_id="m2",
            account_id=1,
            local_rel_path="m2.jpg",
            bytes=1,
            mime_type="image/jpeg",
            width=1,
            height=1,
            shot_at=datetime(2025, 8, 15, tzinfo=timezone.utc),
            imported_at=datetime(2025, 8, 16, tzinfo=timezone.utc),
            is_video=False,
            is_deleted=False,
            has_playback=False,
        )
        m3 = Media(
            google_media_id="m3",
            account_id=1,
            local_rel_path="m3.jpg",
            bytes=1,
            mime_type="image/jpeg",
            width=1,
            height=1,
            shot_at=datetime(2025, 9, 15, tzinfo=timezone.utc),
            imported_at=datetime(2025, 9, 16, tzinfo=timezone.utc),
            is_video=False,
            is_deleted=False,
            has_playback=False,
        )
        db.session.add_all([m1, m2, m3])
        db.session.commit()


@pytest.fixture
def seed_media_detail(app):
    from webapp.extensions import db
    from core.models.photo_models import (
        Media,
        Exif,
        MediaSidecar,
        MediaPlayback,
    )

    with app.app_context():
        m = Media(
            google_media_id="detail",
            account_id=1,
            local_rel_path="path.jpg",
            bytes=123,
            mime_type="image/jpeg",
            width=4032,
            height=3024,
            shot_at=datetime(2025, 8, 17, tzinfo=timezone.utc),
            imported_at=datetime(2025, 8, 18, tzinfo=timezone.utc),
            is_video=False,
            is_deleted=False,
            has_playback=True,
        )
        db.session.add(m)
        db.session.commit()

        exif = Exif(
            media_id=m.id,
            camera_make="Apple",
            camera_model="iPhone",
            lens=None,
            iso=125,
            shutter="1/120",
            f_number=1.6,
            focal_len=26.0,
            gps_lat=None,
            gps_lng=None,
        )
        side = MediaSidecar(
            media_id=m.id,
            type="video",
            rel_path="2025/08/18/side.mp4",
            bytes=1234,
        )
        pb = MediaPlayback(
            media_id=m.id,
            preset="original",
            rel_path="2025/08/18/pb.mp4",
            status="done",
        )
        db.session.add_all([exif, side, pb])
        db.session.commit()
        return m.id


@pytest.fixture
def seed_thumb_media(app):
    from webapp.extensions import db
    from core.models.photo_models import Media

    rel = "2025/08/18/pic.jpg"
    with app.app_context():
        m = Media(
            google_media_id="thumb",
            account_id=1,
            local_rel_path=rel,
            bytes=10,
            mime_type="image/jpeg",
            width=100,
            height=100,
            is_video=False,
            is_deleted=False,
            has_playback=False,
        )
        db.session.add(m)
        db.session.commit()
        mid = m.id

    base = os.environ["FPV_NAS_THUMBS_DIR"]
    path = os.path.join(base, "1024", rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(b"jpg")
    return mid, rel


@pytest.fixture
def seed_playback_media(app):
    from webapp.extensions import db
    from core.models.photo_models import Media, MediaPlayback

    with app.app_context():
        m_ok = Media(
            google_media_id="v1",
            account_id=1,
            local_rel_path="v1.mp4",
            bytes=20,
            mime_type="video/mp4",
            width=100,
            height=100,
            is_video=True,
            is_deleted=False,
            has_playback=True,
        )
        m_run = Media(
            google_media_id="v2",
            account_id=1,
            local_rel_path="v2.mp4",
            bytes=20,
            mime_type="video/mp4",
            width=100,
            height=100,
            is_video=True,
            is_deleted=False,
            has_playback=True,
        )
        m_none = Media(
            google_media_id="v3",
            account_id=1,
            local_rel_path="v3.mp4",
            bytes=20,
            mime_type="video/mp4",
            width=100,
            height=100,
            is_video=True,
            is_deleted=False,
            has_playback=False,
        )
        db.session.add_all([m_ok, m_run, m_none])
        db.session.commit()
        ok_id, run_id, none_id = m_ok.id, m_run.id, m_none.id

        pb_ok = MediaPlayback(
            media_id=m_ok.id,
            preset="std1080p",
            rel_path="2025/08/18/ok.mp4",
            status="done",
        )
        pb_run = MediaPlayback(
            media_id=m_run.id,
            preset="std1080p",
            rel_path="2025/08/18/run.mp4",
            status="processing",
        )
        db.session.add_all([pb_ok, pb_run])
        db.session.commit()
        ok_rel = pb_ok.rel_path

    base = os.environ["FPV_NAS_PLAY_DIR"]
    ok_path = os.path.join(base, ok_rel)
    os.makedirs(os.path.dirname(ok_path), exist_ok=True)
    with open(ok_path, "wb") as f:
        f.write(os.urandom(2048))

    return ok_id, run_id, none_id


@pytest.fixture
def seed_deleted_media(app):
    from webapp.extensions import db
    from core.models.photo_models import Media

    with app.app_context():
        m = Media(
            google_media_id="delm",
            account_id=1,
            local_rel_path="del.jpg",
            bytes=1,
            mime_type="image/jpeg",
            width=1,
            height=1,
            is_video=False,
            is_deleted=True,
            has_playback=False,
        )
        db.session.add(m)
        db.session.commit()
        mid = m.id
        return mid


def test_list_first_page(client, seed_media_bulk):
    _ = seed_media_bulk
    login(client)
    res = client.get("/api/media?limit=200")
    assert res.status_code == 200
    data = res.get_json()
    assert len(data["items"]) == 200
    assert data.get("nextCursor") is not None
    decoded = json.loads(base64.urlsafe_b64decode(data["nextCursor"] + "==").decode())
    assert decoded["id"] == data["items"][-1]["id"]
    ids = [item["id"] for item in data["items"]]
    assert ids == sorted(ids, reverse=True)
    assert data["serverTime"].endswith("Z") and "T" in data["serverTime"]


def test_list_second_page(client, seed_media_bulk):
    _ = seed_media_bulk
    login(client)
    res1 = client.get("/api/media?limit=200")
    cursor = res1.get_json()["nextCursor"]
    res = client.get(f"/api/media?cursor={cursor}&limit=200")
    assert res.status_code == 200
    data = res.get_json()
    assert len(data["items"]) <= 50
    assert data.get("nextCursor") is None


def test_list_deleted_excluded(client, seed_media_bulk):
    deleted_ids = seed_media_bulk
    login(client)
    res = client.get("/api/media?include_deleted=0")
    assert res.status_code == 200
    data = res.get_json()
    returned_ids = {item["id"] for item in data["items"]}
    for did in deleted_ids:
        assert did not in returned_ids


def test_list_range_after_before(client, seed_media_range):
    login(client)
    res = client.get(
        "/api/media?after=2025-08-01T00:00:00Z&before=2025-08-31T23:59:59Z"
    )
    assert res.status_code == 200
    data = res.get_json()
    assert len(data["items"]) == 1
    shot = data["items"][0]["shot_at"]
    dt = datetime.fromisoformat(shot.replace("Z", "+00:00")).replace(tzinfo=None)
    assert datetime(2025, 8, 1) <= dt <= datetime(2025, 8, 31, 23, 59, 59)


def test_detail_ok(client, seed_media_detail):
    media_id = seed_media_detail
    login(client)
    res = client.get(f"/api/media/{media_id}")
    assert res.status_code == 200
    data = res.get_json()
    assert data["id"] == media_id
    assert data["exif"]["camera_make"] == "Apple"
    assert data["sidecars"]
    assert data["playback"]["available"] is True
    assert data["serverTime"].endswith("Z") and "T" in data["serverTime"]


def test_detail_404(client):
    login(client)
    res = client.get("/api/media/999999")
    assert res.status_code == 404


def test_thumb_url_ok(client, seed_thumb_media):
    media_id, _ = seed_thumb_media
    login(client)
    res = client.post(f"/api/media/{media_id}/thumb-url", json={"size": 1024})
    assert res.status_code == 200
    data = res.get_json()
    assert data["url"].startswith("/api/dl/")
    dl = client.get(data["url"])
    assert dl.status_code == 200
    assert dl.headers["Content-Type"] == "image/jpeg"


def test_thumb_url_not_found(client, seed_thumb_media):
    media_id, _ = seed_thumb_media
    login(client)
    res = client.post(f"/api/media/{media_id}/thumb-url", json={"size": 2048})
    assert res.status_code == 404
    assert res.get_json()["error"] == "not_found"


def test_playback_url_states(client, seed_playback_media):
    ok_id, run_id, none_id = seed_playback_media
    login(client)
    res_ok = client.post(f"/api/media/{ok_id}/playback-url")
    assert res_ok.status_code == 200
    res_run = client.post(f"/api/media/{run_id}/playback-url")
    assert res_run.status_code == 409
    assert res_run.get_json()["error"] == "not_ready"
    res_none = client.post(f"/api/media/{none_id}/playback-url")
    assert res_none.status_code == 404


def test_token_tamper(client, seed_thumb_media):
    media_id, _ = seed_thumb_media
    login(client)
    res = client.post(f"/api/media/{media_id}/thumb-url", json={"size": 1024})
    token = res.get_json()["url"].split("/api/dl/")[1]
    tampered = token[:-1] + ("A" if token[-1] != "A" else "B")
    res2 = client.get(f"/api/dl/{tampered}")
    assert res2.status_code == 403
    assert res2.get_json()["error"] == "invalid_token"


def test_token_expired(client, seed_thumb_media):
    media_id, rel = seed_thumb_media
    payload = {
        "v": 1,
        "typ": "thumb",
        "mid": media_id,
        "size": 1024,
        "path": f"thumbs/1024/{rel}",
        "ct": "image/jpeg",
        "exp": int(time.time()) - 10,
        "nonce": "n",
    }
    token = make_token(payload)
    res = client.get(f"/api/dl/{token}")
    assert res.status_code == 403
    assert res.get_json()["error"] == "expired"


def test_range_video(client, seed_playback_media):
    ok_id, _, _ = seed_playback_media
    login(client)
    res = client.post(f"/api/media/{ok_id}/playback-url")
    url = res.get_json()["url"]
    res2 = client.get(url, headers={"Range": "bytes=0-1023"})
    assert res2.status_code == 206
    assert res2.headers["Content-Range"].startswith("bytes 0-")
    assert res2.headers["Accept-Ranges"] == "bytes"


def test_ct_mismatch(client):
    rel = "2025/08/18/foo.png"
    base = os.environ["FPV_NAS_THUMBS_DIR"]
    path = os.path.join(base, "256", rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(b"png")
    payload = {
        "v": 1,
        "typ": "thumb",
        "mid": 0,
        "size": 256,
        "path": f"thumbs/256/{rel}",
        "ct": "image/jpeg",
        "exp": int(time.time()) + 600,
        "nonce": "x",
    }
    token = make_token(payload)
    res = client.get(f"/api/dl/{token}")
    assert res.status_code == 403
    assert res.get_json()["error"] == "forbidden"


def test_thumb_url_deleted_media(client, seed_deleted_media):
    media_id = seed_deleted_media
    login(client)
    res = client.post(f"/api/media/{media_id}/thumb-url", json={"size": 256})
    assert res.status_code == 410


def test_media_thumbnail_route(client, app):
    from webapp.extensions import db
    from core.models.photo_models import Media

    with app.app_context():
        m = Media(
            google_media_id="thumb",
            account_id=1,
            local_rel_path="thumb.jpg",
            bytes=3,
            mime_type="image/jpeg",
            width=1,
            height=1,
            shot_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
            imported_at=datetime(2025, 1, 2, tzinfo=timezone.utc),
            is_video=False,
            is_deleted=False,
            has_playback=False,
        )
        db.session.add(m)
        db.session.commit()
        media_id = m.id

    thumb_dir = Path(os.environ["FPV_NAS_THUMBS_DIR"]) / "256"
    thumb_dir.mkdir(parents=True, exist_ok=True)
    thumb_path = thumb_dir / "thumb.jpg"
    data = b"testdata"
    thumb_path.write_bytes(data)

    login(client)
    res = client.get(f"/api/media/{media_id}/thumbnail?size=256")
    assert res.status_code == 200
    assert res.data == data
    assert res.headers["Cache-Control"].startswith("private")

