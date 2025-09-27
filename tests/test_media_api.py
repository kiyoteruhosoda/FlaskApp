import os
import base64
import json
import hmac
import hashlib
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from PIL import Image


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
    os.environ["FPV_URL_TTL_ORIGINAL"] = "600"
    thumbs = tmp_path / "thumbs"
    play = tmp_path / "play"
    orig = tmp_path / "orig"
    thumbs.mkdir()
    play.mkdir()
    orig.mkdir()
    os.environ["FPV_NAS_THUMBS_DIR"] = str(thumbs)
    os.environ["FPV_NAS_PLAY_DIR"] = str(play)
    os.environ["FPV_NAS_ORIGINALS_DIR"] = str(orig)
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


def grant_permission(app, code: str) -> None:
    from webapp.extensions import db
    from core.models.user import User, Role, Permission

    with app.app_context():
        perm = Permission.query.filter_by(code=code).first()
        if not perm:
            perm = Permission(code=code)
            db.session.add(perm)
            db.session.flush()

        role = Role.query.filter_by(name="tag-manager").first()
        if not role:
            role = Role(name="tag-manager")
            db.session.add(role)
            db.session.flush()

        if perm not in role.permissions:
            role.permissions.append(perm)

        user = User.query.first()
        if role not in user.roles:
            user.roles.append(role)

        db.session.commit()


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
def seed_media_without_shot_at(app):
    from webapp.extensions import db
    from core.models.photo_models import Media
    from core.models.google_account import GoogleAccount

    with app.app_context():
        account_id = GoogleAccount.query.first().id
        created_ids = []
        for i in range(5):
            media = Media(
                google_media_id=f"missing-shot-{i}",
                account_id=account_id,
                local_rel_path=f"missing-{i}.jpg",
                bytes=1,
                mime_type="image/jpeg",
                width=100,
                height=100,
                shot_at=None,
                is_video=False,
                is_deleted=False,
                has_playback=False,
            )
            db.session.add(media)
            db.session.flush()
            created_ids.append(media.id)
        db.session.commit()
        return created_ids


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
def seed_media_with_tags(app):
    from webapp.extensions import db
    from core.models.photo_models import Media, Tag

    with app.app_context():
        tag_person = Tag(name="Alice", attr="person")
        tag_place = Tag(name="Paris", attr="place")
        tag_thing = Tag(name="Camera", attr="thing")

        base_time = datetime(2025, 1, 1, tzinfo=timezone.utc)
        media1 = Media(
            google_media_id="tag1",
            account_id=1,
            local_rel_path="tag1.jpg",
            bytes=1,
            mime_type="image/jpeg",
            width=10,
            height=10,
            shot_at=base_time,
            imported_at=base_time,
            is_video=False,
            is_deleted=False,
            has_playback=False,
        )
        media2 = Media(
            google_media_id="tag2",
            account_id=1,
            local_rel_path="tag2.jpg",
            bytes=1,
            mime_type="image/jpeg",
            width=10,
            height=10,
            shot_at=base_time + timedelta(days=1),
            imported_at=base_time + timedelta(days=1),
            is_video=False,
            is_deleted=False,
            has_playback=False,
        )
        media3 = Media(
            google_media_id="tag3",
            account_id=1,
            local_rel_path="tag3.jpg",
            bytes=1,
            mime_type="image/jpeg",
            width=10,
            height=10,
            shot_at=base_time + timedelta(days=2),
            imported_at=base_time + timedelta(days=2),
            is_video=False,
            is_deleted=False,
            has_playback=False,
        )

        media1.tags.extend([tag_person, tag_place])
        media2.tags.append(tag_person)
        media3.tags.append(tag_thing)

        db.session.add_all([tag_person, tag_place, tag_thing, media1, media2, media3])
        db.session.commit()

        return {
            "media1": media1.id,
            "media2": media2.id,
            "media3": media3.id,
            "tags": {
                "person": tag_person.id,
                "place": tag_place.id,
                "thing": tag_thing.id,
            },
        }


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
            filename="Original Name.jpg",
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
    orig_base = os.environ["FPV_NAS_ORIGINALS_DIR"]
    orig_path = os.path.join(orig_base, rel)
    os.makedirs(os.path.dirname(orig_path), exist_ok=True)
    with open(orig_path, "wb") as f:
        f.write(b"orig")
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
            filename="Playback Clip.mp4",
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
            filename="Processing Clip.mp4",
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
            filename="Missing Playback.mp4",
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


def test_list_negative_page_falls_back_to_first(client, seed_media_bulk):
    _ = seed_media_bulk
    login(client)

    res = client.get("/api/media?page=-5&pageSize=10")
    assert res.status_code == 200
    data = res.get_json()
    # page=-5 は自動的に1ページ目扱いとなる
    assert data.get("currentPage") == 1
    assert len(data["items"]) == 10


def test_list_cursor_falls_back_to_id(client, seed_media_without_shot_at):
    _ = seed_media_without_shot_at
    login(client)

    res1 = client.get("/api/media?pageSize=2&order=desc")
    assert res1.status_code == 200
    data1 = res1.get_json()
    ids1 = [item["id"] for item in data1["items"]]
    assert ids1 == sorted(ids1, reverse=True)
    cursor1 = data1.get("nextCursor")
    assert cursor1

    res2 = client.get(f"/api/media?pageSize=2&order=desc&cursor={cursor1}")
    assert res2.status_code == 200
    data2 = res2.get_json()
    ids2 = [item["id"] for item in data2["items"]]
    assert ids2 == sorted(ids2, reverse=True)
    assert not set(ids1) & set(ids2)
    cursor2 = data2.get("nextCursor")
    assert cursor2 and cursor2 != cursor1

    res3 = client.get(f"/api/media?pageSize=2&order=desc&cursor={cursor2}")
    assert res3.status_code == 200
    data3 = res3.get_json()
    ids3 = [item["id"] for item in data3["items"]]
    assert ids3 == sorted(ids3, reverse=True)
    assert not (set(ids1) & set(ids3))
    assert not (set(ids2) & set(ids3))
    assert data3.get("nextCursor") is None


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
    assert "tags" in data


def test_detail_404(client):
    login(client)
    res = client.get("/api/media/999999")
    assert res.status_code == 404


def test_media_list_filters_by_tags(client, seed_media_with_tags):
    login(client)
    person_tag = seed_media_with_tags["tags"]["person"]
    res = client.get(f"/api/media?tags={person_tag}")
    assert res.status_code == 200
    data = res.get_json()
    ids = {item["id"] for item in data["items"]}
    assert seed_media_with_tags["media1"] in ids
    assert seed_media_with_tags["media2"] in ids
    assert seed_media_with_tags["media3"] not in ids
    assert all("tags" in item for item in data["items"])

    place_tag = seed_media_with_tags["tags"]["place"]
    res = client.get(f"/api/media?tags={person_tag},{place_tag}")
    assert res.status_code == 200
    data = res.get_json()
    ids = {item["id"] for item in data["items"]}
    assert ids == {seed_media_with_tags["media1"]}


def test_media_detail_includes_tags(client, seed_media_with_tags):
    login(client)
    media_id = seed_media_with_tags["media1"]
    res = client.get(f"/api/media/{media_id}")
    assert res.status_code == 200
    data = res.get_json()
    tag_names = {tag["name"] for tag in data["tags"]}
    assert {"Alice", "Paris"}.issubset(tag_names)


def test_media_update_tags_requires_permission(client, seed_media_with_tags):
    login(client)
    media_id = seed_media_with_tags["media2"]
    res = client.put(f"/api/media/{media_id}/tags", json={"tag_ids": []})
    assert res.status_code == 403


def test_media_update_tags_success(client, app, seed_media_with_tags):
    grant_permission(app, "media:tag-manage")
    login(client)
    media_id = seed_media_with_tags["media2"]
    new_tag = seed_media_with_tags["tags"]["thing"]

    res = client.put(
        f"/api/media/{media_id}/tags",
        json={"tag_ids": [new_tag]},
    )
    assert res.status_code == 200
    data = res.get_json()
    returned_ids = [tag["id"] for tag in data["tags"]]
    assert returned_ids == [new_tag]


def test_unused_tags_removed_from_master(client, app, seed_media_with_tags):
    grant_permission(app, "media:tag-manage")
    login(client)

    media_id = seed_media_with_tags["media1"]
    place_tag_id = seed_media_with_tags["tags"]["place"]
    person_tag_id = seed_media_with_tags["tags"]["person"]

    res = client.put(f"/api/media/{media_id}/tags", json={"tag_ids": []})
    assert res.status_code == 200

    with app.app_context():
        from core.models.photo_models import Tag
        from webapp.extensions import db

        assert db.session.get(Tag, place_tag_id) is None
        assert db.session.get(Tag, person_tag_id) is not None


def test_create_tag_requires_permission(client, app):
    login(client)
    res = client.post("/api/tags", json={"name": "Sunset", "attr": "thing"})
    assert res.status_code == 403

    grant_permission(app, "media:tag-manage")
    res = client.post("/api/tags", json={"name": "Sunset", "attr": "thing"})
    assert res.status_code == 201
    data = res.get_json()
    assert data["tag"]["name"] == "Sunset"
    assert data["created"] is True

    res = client.post("/api/tags", json={"name": "Sunset", "attr": "thing"})
    assert res.status_code == 200
    data = res.get_json()
    assert data["created"] is False


def test_tag_search_returns_matches(client, seed_media_with_tags):
    login(client)
    res = client.get("/api/tags?q=Ali")
    assert res.status_code == 200
    data = res.get_json()
    names = [tag["name"] for tag in data["items"]]
    assert "Alice" in names


def test_update_tag_success(client, app, seed_media_with_tags):
    grant_permission(app, "media:tag-manage")
    login(client)
    tag_id = seed_media_with_tags["tags"]["person"]

    res = client.put(f"/api/tags/{tag_id}", json={"name": "Alison"})
    assert res.status_code == 200
    data = res.get_json()
    assert data["tag"]["name"] == "Alison"
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
    cd = dl.headers.get("Content-Disposition")
    assert cd is not None and cd.startswith("attachment")
    assert "filename=\"Original_Name.jpg\"" in cd
    assert "filename*=UTF-8''Original%20Name.jpg" in cd


def test_thumb_url_not_found(client, seed_thumb_media):
    media_id, _ = seed_thumb_media
    login(client)
    res = client.post(f"/api/media/{media_id}/thumb-url", json={"size": 2048})
    assert res.status_code == 404
    assert res.get_json()["error"] == "not_found"


def test_original_url_ok(client, seed_thumb_media):
    media_id, rel = seed_thumb_media
    login(client)

    orig_path = Path(os.environ["FPV_NAS_ORIGINALS_DIR"]) / rel
    orig_path.parent.mkdir(parents=True, exist_ok=True)
    orig_path.write_bytes(b"orig")

    res = client.post(f"/api/media/{media_id}/original-url")
    assert res.status_code == 200
    data = res.get_json()
    assert data["url"].startswith("/api/dl/")

    dl = client.get(data["url"])
    assert dl.status_code == 200
    assert dl.headers["Content-Type"] == "image/jpeg"
    cd = dl.headers.get("Content-Disposition")
    assert cd is not None and cd.startswith("attachment")
    assert "filename=\"Original_Name.jpg\"" in cd
    assert "filename*=UTF-8''Original%20Name.jpg" in cd
    assert dl.data == b"orig"


def test_original_url_not_found(client, seed_thumb_media):
    media_id, rel = seed_thumb_media
    login(client)

    orig_path = Path(os.environ["FPV_NAS_ORIGINALS_DIR"]) / rel
    if orig_path.exists():
        orig_path.unlink()

    res = client.post(f"/api/media/{media_id}/original-url")
    assert res.status_code == 404
    assert res.get_json()["error"] == "not_found"


def test_download_requires_auth(client, seed_thumb_media):
    media_id, rel = seed_thumb_media
    payload = {
        "v": 1,
        "typ": "thumb",
        "mid": media_id,
        "size": 1024,
        "path": f"thumbs/1024/{rel}",
        "ct": "image/jpeg",
        "exp": int(time.time()) + 600,
        "nonce": "auth",
    }
    token = make_token(payload)
    app = client.application
    original_testing = app.config.get("TESTING")
    original_login_disabled = app.config.get("LOGIN_DISABLED")
    app.config["TESTING"] = False
    app.config["LOGIN_DISABLED"] = False
    try:
        res = client.get(f"/api/dl/{token}")
    finally:
        app.config["TESTING"] = original_testing
        if original_login_disabled is None:
            app.config.pop("LOGIN_DISABLED", None)
        else:
            app.config["LOGIN_DISABLED"] = original_login_disabled
    assert res.status_code == 401
    assert res.get_json()["error"] == "authentication_required"


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
    login(client)
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
    cd = res2.headers.get("Content-Disposition")
    assert cd is not None and "filename=\"Playback_Clip.mp4\"" in cd
    assert "filename*=UTF-8''Playback%20Clip.mp4" in cd


def test_playback_filename_for_mov(client, app):
    from webapp.extensions import db
    from core.models.photo_models import Media, MediaPlayback

    login(client)

    with app.app_context():
        media = Media(
            google_media_id="mov1",
            account_id=1,
            local_rel_path="mov/test.mov",
            filename="Playback Clip.mov",
            bytes=20,
            mime_type="video/quicktime",
            width=100,
            height=100,
            duration_ms=2000,
            is_video=True,
            is_deleted=False,
            has_playback=True,
        )
        db.session.add(media)
        db.session.commit()

        playback = MediaPlayback(
            media_id=media.id,
            preset="std1080p",
            rel_path="2025/08/18/clip.mp4",
            status="done",
        )
        db.session.add(playback)
        db.session.commit()

        media_id = media.id
        playback_rel = playback.rel_path

    play_dir = Path(os.environ["FPV_NAS_PLAY_DIR"])
    playback_path = play_dir / playback_rel
    playback_path.parent.mkdir(parents=True, exist_ok=True)
    playback_path.write_bytes(os.urandom(1024))

    res = client.post(f"/api/media/{media_id}/playback-url")
    assert res.status_code == 200
    url = res.get_json()["url"]

    res2 = client.get(url)
    assert res2.status_code == 200
    cd = res2.headers.get("Content-Disposition")
    assert cd is not None and "filename=\"Playback_Clip.mp4\"" in cd
    assert "filename*=UTF-8''Playback%20Clip.mp4" in cd


def test_media_detail_playback_paths_normalized(client, app):
    from webapp.extensions import db
    from core.models.photo_models import Media, MediaPlayback

    login(client)

    with app.app_context():
        media = Media(
            google_media_id="mov2",
            account_id=1,
            local_rel_path="mov/test.mov",
            filename="Playback Clip.mov",
            bytes=20,
            mime_type="video/quicktime",
            width=100,
            height=100,
            duration_ms=2000,
            is_video=True,
            is_deleted=False,
            has_playback=True,
        )
        db.session.add(media)
        db.session.commit()

        playback = MediaPlayback(
            media_id=media.id,
            preset="std1080p",
            rel_path=r"2025\\08\\18\\clip.MP4",
            poster_rel_path=r"2025\\08\\18\\clip poster.JPG",
            status="done",
        )
        db.session.add(playback)
        db.session.commit()

        media_id = media.id

    res = client.get(f"/api/media/{media_id}")
    assert res.status_code == 200
    data = res.get_json()
    playback_info = data["playback"]

    assert playback_info["rel_path"] == "2025/08/18/clip.MP4"
    assert playback_info["poster_rel_path"] == "2025/08/18/clip poster.JPG"


def test_download_with_accel_redirect(client, seed_thumb_media, app):
    media_id, rel = seed_thumb_media
    login(client)
    app.config["FPV_ACCEL_THUMBS_LOCATION"] = "/protected/thumbs"
    res = client.post(f"/api/media/{media_id}/thumb-url", json={"size": 1024})
    assert res.status_code == 200
    token_url = res.get_json()["url"]
    res2 = client.get(token_url)
    assert res2.status_code == 200
    expected = "/protected/thumbs/" + "/".join(("1024", rel.replace(os.sep, "/")))
    assert res2.headers["X-Accel-Redirect"] == expected
    assert res2.headers["Cache-Control"].startswith("private")
    assert res2.data == b""


def test_download_original_with_accel_redirect(client, seed_thumb_media, app):
    media_id, rel = seed_thumb_media
    login(client)
    app.config["FPV_ACCEL_ORIGINALS_LOCATION"] = "/protected/originals"
    res = client.post(f"/api/media/{media_id}/original-url")
    assert res.status_code == 200
    token_url = res.get_json()["url"]
    res2 = client.get(token_url)
    assert res2.status_code == 200
    expected = "/protected/originals/" + rel.replace(os.sep, "/")
    assert res2.headers["X-Accel-Redirect"] == expected
    assert res2.headers["Cache-Control"].startswith("private")
    assert res2.data == b""


def test_download_without_accel_redirect(client, seed_thumb_media, app):
    media_id, rel = seed_thumb_media
    login(client)
    app.config["FPV_ACCEL_THUMBS_LOCATION"] = "/protected/thumbs"
    app.config["FPV_ACCEL_REDIRECT_ENABLED"] = False
    res = client.post(f"/api/media/{media_id}/thumb-url", json={"size": 1024})
    assert res.status_code == 200
    token_url = res.get_json()["url"]
    res2 = client.get(token_url)
    assert res2.status_code == 200
    assert res2.headers.get("X-Accel-Redirect") is None
    assert res2.headers["Cache-Control"].startswith("private")
    assert res2.data == b"jpg"


def test_ct_mismatch(client):
    login(client)
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


def test_media_thumbnail_route_handles_heic(client, app):
    from webapp.extensions import db
    from core.models.photo_models import Media

    with app.app_context():
        media = Media(
            google_media_id="heic-thumb",
            account_id=1,
            local_rel_path="heic-thumb.heic",
            bytes=3,
            mime_type="image/heic",
            width=1,
            height=1,
            shot_at=datetime(2025, 3, 1, tzinfo=timezone.utc),
            imported_at=datetime(2025, 3, 2, tzinfo=timezone.utc),
            is_video=False,
            is_deleted=False,
            has_playback=False,
        )
        db.session.add(media)
        db.session.commit()
        media_id = media.id

    thumb_dir = Path(os.environ["FPV_NAS_THUMBS_DIR"]) / "256"
    thumb_dir.mkdir(parents=True, exist_ok=True)
    thumb_path = thumb_dir / "heic-thumb.jpg"
    payload = b"heic"
    thumb_path.write_bytes(payload)

    login(client)
    res = client.get(f"/api/media/{media_id}/thumbnail?size=256")
    assert res.status_code == 200
    assert res.data == payload


def test_media_thumbnail_route_uses_thumbnail_rel_path(client, app):
    from webapp.extensions import db
    from core.models.photo_models import Media

    with app.app_context():
        media = Media(
            google_media_id="thumb-alt",
            account_id=1,
            local_rel_path="thumb-alt.heic",
            thumbnail_rel_path="alt/thumb-alt.jpg",
            bytes=3,
            mime_type="image/jpeg",
            width=1,
            height=1,
            shot_at=datetime(2025, 4, 1, tzinfo=timezone.utc),
            imported_at=datetime(2025, 4, 2, tzinfo=timezone.utc),
            is_video=False,
            is_deleted=False,
            has_playback=False,
        )
        db.session.add(media)
        db.session.commit()
        media_id = media.id

    thumb_dir = Path(os.environ["FPV_NAS_THUMBS_DIR"]) / "256" / "alt"
    thumb_dir.mkdir(parents=True, exist_ok=True)
    thumb_path = thumb_dir / "thumb-alt.jpg"
    payload = b"alt-thumb"
    thumb_path.write_bytes(payload)

    login(client)
    res = client.get(f"/api/media/{media_id}/thumbnail?size=256")
    assert res.status_code == 200
    assert res.data == payload


def test_thumbnail_falls_back_to_default_path(client, app, monkeypatch, tmp_path):
    from webapp.extensions import db
    from core.models.photo_models import Media
    from webapp.api import routes as api_routes

    with app.app_context():
        original_thumb_dir = app.config["FPV_NAS_THUMBS_DIR"]
        media = Media(
            google_media_id="thumb-fallback",
            account_id=1,
            local_rel_path="thumb-fallback.jpg",
            bytes=3,
            mime_type="image/jpeg",
            width=1,
            height=1,
            shot_at=datetime(2025, 2, 1, tzinfo=timezone.utc),
            imported_at=datetime(2025, 2, 2, tzinfo=timezone.utc),
            is_video=False,
            is_deleted=False,
            has_playback=False,
        )
        db.session.add(media)
        db.session.commit()
        media_id = media.id

    host_path = tmp_path / "host"
    host_path.mkdir()
    fallback_path = tmp_path / "fallback"
    thumb_dir = fallback_path / "512"
    thumb_dir.mkdir(parents=True, exist_ok=True)
    thumb_file = thumb_dir / "thumb-fallback.jpg"
    payload = b"fallback"
    thumb_file.write_bytes(payload)

    monkeypatch.setenv("FPV_NAS_THUMBS_DIR", str(host_path))
    with app.app_context():
        app.config["FPV_NAS_THUMBS_DIR"] = str(host_path)
    monkeypatch.setitem(
        api_routes._STORAGE_DEFAULTS,
        "FPV_NAS_THUMBS_DIR",
        str(fallback_path),
    )

    login(client)
    res = client.get(f"/api/media/{media_id}/thumbnail?size=512")
    assert res.status_code == 200
    assert res.data == payload

    with app.app_context():
        app.config["FPV_NAS_THUMBS_DIR"] = original_thumb_dir


def test_media_delete_requires_permission(client, app):
    from webapp.extensions import db
    from core.models.photo_models import Media

    with app.app_context():
        media = Media(
            google_media_id="del-test",
            account_id=1,
            local_rel_path="del-test.jpg",
            bytes=10,
            mime_type="image/jpeg",
            width=100,
            height=100,
            shot_at=datetime(2025, 2, 1, tzinfo=timezone.utc),
            imported_at=datetime(2025, 2, 2, tzinfo=timezone.utc),
            is_video=False,
            is_deleted=False,
            has_playback=False,
        )
        db.session.add(media)
        db.session.commit()
        media_id = media.id

    login(client)
    response = client.delete(f"/api/media/{media_id}")
    assert response.status_code == 403
    data = response.get_json()
    assert data["error"] == "forbidden"


def test_media_recover_requires_permission(client, app):
    from webapp.extensions import db
    from core.models.photo_models import Media

    rel_path = "2024/01/01/recover.jpg"

    with app.app_context():
        media = Media(
            google_media_id="recover-no-perm",
            account_id=1,
            local_rel_path=rel_path,
            bytes=0,
            mime_type="image/jpeg",
            is_video=False,
            is_deleted=False,
            has_playback=False,
        )
        db.session.add(media)
        db.session.commit()
        media_id = media.id

    orig_dir = Path(os.environ["FPV_NAS_ORIGINALS_DIR"]) / "2024" / "01" / "01"
    orig_dir.mkdir(parents=True, exist_ok=True)
    image_path = orig_dir / "recover.jpg"
    Image.new("RGB", (16, 16), color=(200, 80, 80)).save(image_path, format="JPEG")

    with app.app_context():
        app.config["LOGIN_DISABLED"] = False

    login(client)
    res = client.post(f"/api/media/{media_id}/recover")
    assert res.status_code == 403
    payload = res.get_json()
    assert payload["error"] == "forbidden"


def test_media_recover_success(client, app):
    from webapp.extensions import db
    from core.models.photo_models import Media

    rel_path = "2024/02/02/recover-success.jpg"

    with app.app_context():
        media = Media(
            google_media_id="recover-success",
            account_id=1,
            local_rel_path=rel_path,
            bytes=0,
            mime_type="image/jpeg",
            width=None,
            height=None,
            shot_at=None,
            is_video=False,
            is_deleted=False,
            has_playback=False,
        )
        db.session.add(media)
        db.session.commit()
        media_id = media.id

    orig_dir = Path(os.environ["FPV_NAS_ORIGINALS_DIR"]) / "2024" / "02" / "02"
    orig_dir.mkdir(parents=True, exist_ok=True)
    image_path = orig_dir / "recover-success.jpg"
    Image.new("RGB", (48, 32), color=(120, 160, 200)).save(image_path, format="JPEG")

    with app.app_context():
        app.config["LOGIN_DISABLED"] = False

    grant_permission(app, "media:recover")
    login(client)

    res = client.post(f"/api/media/{media_id}/recover")
    assert res.status_code == 200
    payload = res.get_json()
    assert payload["metadataRefreshed"] is True
    assert payload["media"]["id"] == media_id
    assert isinstance(payload.get("thumbnailJobTriggered"), bool)

    with app.app_context():
        refreshed = Media.query.get(media_id)
        assert refreshed is not None
        assert refreshed.hash_sha256 is not None
        assert refreshed.bytes == os.path.getsize(image_path)
        assert refreshed.width == 48
        assert refreshed.height == 32
        assert refreshed.thumbnail_rel_path == refreshed.local_rel_path


def test_thumbnail_missing_triggers_regeneration(client, app):
    from webapp.extensions import db
    from core.models.photo_models import Media

    rel_path = "2024/03/03/thumb-missing.jpg"

    with app.app_context():
        media = Media(
            google_media_id="thumb-missing",
            account_id=1,
            local_rel_path=rel_path,
            bytes=0,
            mime_type="image/jpeg",
            width=None,
            height=None,
            is_video=False,
            is_deleted=False,
            has_playback=False,
        )
        db.session.add(media)
        db.session.commit()
        media_id = media.id

    orig_dir = Path(os.environ["FPV_NAS_ORIGINALS_DIR"]) / "2024" / "03" / "03"
    orig_dir.mkdir(parents=True, exist_ok=True)
    image_path = orig_dir / "thumb-missing.jpg"
    Image.new("RGB", (32, 24), color=(10, 200, 150)).save(image_path, format="JPEG")

    login(client)
    res = client.get(f"/api/media/{media_id}/thumbnail?size=256")
    assert res.status_code == 404
    payload = res.get_json()
    assert payload["error"] == "not_found"
    assert payload.get("thumbnailJobTriggered") is True

    with app.app_context():
        refreshed = Media.query.get(media_id)
        assert refreshed is not None
        assert refreshed.is_deleted is False


def test_media_delete_success(client, app):
    from webapp.extensions import db
    from core.models.photo_models import Media

    with app.app_context():
        media = Media(
            google_media_id="del-success",
            account_id=1,
            local_rel_path="del-success.jpg",
            bytes=5,
            mime_type="image/jpeg",
            width=80,
            height=80,
            shot_at=datetime(2025, 3, 1, tzinfo=timezone.utc),
            imported_at=datetime(2025, 3, 2, tzinfo=timezone.utc),
            is_video=False,
            is_deleted=False,
            has_playback=False,
        )
        db.session.add(media)
        db.session.commit()
        media_id = media.id
        orig_dir = Path(app.config["FPV_NAS_ORIGINALS_DIR"])
        (orig_dir / media.local_rel_path).write_bytes(b"data")

    grant_permission(app, "media:delete")
    login(client)

    response = client.delete(f"/api/media/{media_id}")
    assert response.status_code == 200
    data = response.get_json()
    assert data["result"] == "deleted"

    with app.app_context():
        refreshed = Media.query.get(media_id)
        assert refreshed is not None
        assert refreshed.is_deleted is True
        assert not (Path(app.config["FPV_NAS_ORIGINALS_DIR"]) / refreshed.local_rel_path).exists()


def test_media_delete_removes_media_from_albums(client, app):
    from webapp.extensions import db
    from core.models.photo_models import Media, Album, album_item

    with app.app_context():
        media1 = Media(
            google_media_id="album-media-1",
            account_id=1,
            local_rel_path="album-media-1.jpg",
            bytes=5,
            mime_type="image/jpeg",
            width=80,
            height=80,
            shot_at=datetime(2025, 4, 1, tzinfo=timezone.utc),
            imported_at=datetime(2025, 4, 2, tzinfo=timezone.utc),
            is_video=False,
            is_deleted=False,
            has_playback=False,
        )
        media2 = Media(
            google_media_id="album-media-2",
            account_id=1,
            local_rel_path="album-media-2.jpg",
            bytes=5,
            mime_type="image/jpeg",
            width=80,
            height=80,
            shot_at=datetime(2025, 4, 3, tzinfo=timezone.utc),
            imported_at=datetime(2025, 4, 4, tzinfo=timezone.utc),
            is_video=False,
            is_deleted=False,
            has_playback=False,
        )
        album = Album(
            name="Album",
            description=None,
            visibility="private",
            cover_media_id=None,
        )
        db.session.add_all([media1, media2, album])
        db.session.commit()

        db.session.execute(
            album_item.insert(),
            [
                {"album_id": album.id, "media_id": media1.id, "sort_index": 0},
                {"album_id": album.id, "media_id": media2.id, "sort_index": 1},
            ],
        )
        album.cover_media_id = media1.id
        db.session.commit()

        media_id = media1.id
        album_id = album.id
        remaining_id = media2.id

    grant_permission(app, "media:delete")
    login(client)

    response = client.delete(f"/api/media/{media_id}")
    assert response.status_code == 200

    with app.app_context():
        album = Album.query.get(album_id)
        remaining_entries = db.session.execute(
            album_item.select().where(album_item.c.album_id == album_id)
        ).all()
        remaining_media_ids = [row.media_id for row in remaining_entries]

        assert media_id not in remaining_media_ids
        assert remaining_id in remaining_media_ids
        assert album.cover_media_id == remaining_id


def test_media_delete_clears_cover_when_album_becomes_empty(client, app):
    from webapp.extensions import db
    from core.models.photo_models import Media, Album, album_item

    with app.app_context():
        media = Media(
            google_media_id="album-only-media",
            account_id=1,
            local_rel_path="album-only-media.jpg",
            bytes=5,
            mime_type="image/jpeg",
            width=80,
            height=80,
            shot_at=datetime(2025, 5, 1, tzinfo=timezone.utc),
            imported_at=datetime(2025, 5, 2, tzinfo=timezone.utc),
            is_video=False,
            is_deleted=False,
            has_playback=False,
        )
        album = Album(
            name="Solo Album",
            description=None,
            visibility="private",
            cover_media_id=None,
        )
        db.session.add_all([media, album])
        db.session.commit()

        db.session.execute(
            album_item.insert(),
            [{"album_id": album.id, "media_id": media.id, "sort_index": 0}],
        )
        album.cover_media_id = media.id
        db.session.commit()

        media_id = media.id
        album_id = album.id

    grant_permission(app, "media:delete")
    login(client)

    response = client.delete(f"/api/media/{media_id}")
    assert response.status_code == 200

    with app.app_context():
        album = Album.query.get(album_id)
        remaining_entries = db.session.execute(
            album_item.select().where(album_item.c.album_id == album_id)
        ).all()
        assert remaining_entries == []
        assert album.cover_media_id is None


def test_album_list_custom_order(client, app):
    from webapp.extensions import db
    from core.models.photo_models import Album

    with app.app_context():
        a1 = Album(name="First", description=None, visibility="private", display_order=2)
        a2 = Album(name="Second", description=None, visibility="private", display_order=0)
        a3 = Album(name="Third", description=None, visibility="private", display_order=1)
        db.session.add_all([a1, a2, a3])
        db.session.commit()
        ids = [a1.id, a2.id, a3.id]

    grant_permission(app, "media:view")
    grant_permission(app, "album:view")
    login(client)

    response = client.get("/api/albums?order=custom&pageSize=10")
    assert response.status_code == 200
    data = response.get_json()
    returned_ids = [item["id"] for item in data["items"]]
    assert returned_ids == [ids[1], ids[2], ids[0]]
    assert data["items"][0]["displayOrder"] == 0


def test_album_reorder_updates_display_order(client, app):
    from webapp.extensions import db
    from core.models.photo_models import Album

    with app.app_context():
        albums = [
            Album(name="One", description=None, visibility="private"),
            Album(name="Two", description=None, visibility="private"),
            Album(name="Three", description=None, visibility="private"),
        ]
        db.session.add_all(albums)
        db.session.commit()
        album_ids = [album.id for album in albums]

    grant_permission(app, "album:edit")
    login(client)

    desired_order = [album_ids[2], album_ids[0], album_ids[1]]
    response = client.put("/api/albums/order", json={"albumIds": desired_order})
    assert response.status_code == 200
    data = response.get_json()
    assert data["updated"] is True

    with app.app_context():
        refreshed = {
            album.id: album.display_order
            for album in Album.query.filter(Album.id.in_(desired_order)).all()
        }
        assert refreshed[desired_order[0]] == 0
        assert refreshed[desired_order[1]] == 1
        assert refreshed[desired_order[2]] == 2


def test_album_update_removing_all_media_clears_cover(client, app):
    from webapp.extensions import db
    from core.models.photo_models import Media, Album, album_item

    with app.app_context():
        media1 = Media(
            google_media_id="album-update-media-1",
            account_id=1,
            local_rel_path="album-update-media-1.jpg",
            bytes=5,
            mime_type="image/jpeg",
            width=80,
            height=80,
            shot_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
            imported_at=datetime(2025, 6, 2, tzinfo=timezone.utc),
            is_video=False,
            is_deleted=False,
            has_playback=False,
        )
        media2 = Media(
            google_media_id="album-update-media-2",
            account_id=1,
            local_rel_path="album-update-media-2.jpg",
            bytes=5,
            mime_type="image/jpeg",
            width=80,
            height=80,
            shot_at=datetime(2025, 6, 3, tzinfo=timezone.utc),
            imported_at=datetime(2025, 6, 4, tzinfo=timezone.utc),
            is_video=False,
            is_deleted=False,
            has_playback=False,
        )
        album = Album(
            name="Update Album",
            description=None,
            visibility="private",
            cover_media_id=None,
        )
        db.session.add_all([media1, media2, album])
        db.session.commit()

        db.session.execute(
            album_item.insert(),
            [
                {"album_id": album.id, "media_id": media1.id, "sort_index": 0},
                {"album_id": album.id, "media_id": media2.id, "sort_index": 1},
            ],
        )
        album.cover_media_id = media1.id
        db.session.commit()

        album_id = album.id

    grant_permission(app, "album:edit")
    login(client)

    response = client.put(f"/api/albums/{album_id}", json={"mediaIds": []})
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["updated"] is True
    assert payload["album"]["mediaIds"] == []
    assert payload["album"]["coverMediaId"] is None

    with app.app_context():
        refreshed = Album.query.get(album_id)
        assert refreshed.cover_media_id is None


def test_album_api_handles_missing_cover_media(client, app):
    from webapp.extensions import db
    from core.models.photo_models import Album

    with app.app_context():
        album = Album(
            name="Stale Cover",
            description=None,
            visibility="private",
            cover_media_id=999,
        )
        db.session.add(album)
        db.session.commit()
        album_id = album.id

    grant_permission(app, "media:view")
    grant_permission(app, "album:view")
    login(client)

    detail_resp = client.get(f"/api/albums/{album_id}")
    assert detail_resp.status_code == 200
    detail_payload = detail_resp.get_json()
    assert detail_payload["album"]["media"] == []
    assert detail_payload["album"]["coverMediaId"] is None

    list_resp = client.get("/api/albums?pageSize=10")
    assert list_resp.status_code == 200
    list_payload = list_resp.get_json()
    assert list_payload["items"][0]["coverImageId"] is None


def test_album_media_reorder_updates_sort_index(client, app):
    from webapp.extensions import db
    from core.models.photo_models import Media, Album, album_item

    with app.app_context():
        media_items = []
        for index in range(3):
            media = Media(
                google_media_id=f"album-reorder-{index}",
                account_id=1,
                local_rel_path=f"album-reorder-{index}.jpg",
                bytes=5,
                mime_type="image/jpeg",
                width=80,
                height=80,
                shot_at=datetime(2025, 7, index + 1, tzinfo=timezone.utc),
                imported_at=datetime(2025, 7, index + 2, tzinfo=timezone.utc),
                is_video=False,
                is_deleted=False,
                has_playback=False,
            )
            media_items.append(media)

        album = Album(
            name="Reorder Album",
            description=None,
            visibility="private",
            cover_media_id=None,
        )
        db.session.add(album)
        db.session.add_all(media_items)
        db.session.commit()

        for position, media in enumerate(media_items):
            db.session.execute(
                album_item.insert(),
                [{"album_id": album.id, "media_id": media.id, "sort_index": position}],
            )
        db.session.commit()

        album_id = album.id
        reordered_ids = [media_items[2].id, media_items[0].id, media_items[1].id]

    grant_permission(app, "album:edit")
    login(client)

    response = client.put(
        f"/api/albums/{album_id}/media/order",
        json={"mediaIds": reordered_ids},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["updated"] is True
    assert [item["id"] for item in payload["album"]["media"]] == reordered_ids
    assert [item["sortIndex"] for item in payload["album"]["media"]] == [0, 1, 2]

    with app.app_context():
        rows = db.session.execute(
            album_item.select()
            .where(album_item.c.album_id == album_id)
            .order_by(album_item.c.sort_index.asc())
        ).all()
        assert [row.media_id for row in rows] == reordered_ids
        assert [row.sort_index for row in rows] == [0, 1, 2]


def _create_album_with_media(app, *, rel_path: str = "fullsize.jpg"):
    from webapp.extensions import db
    from core.models.photo_models import Media, Album, album_item

    with app.app_context():
        media = Media(
            google_media_id="album-full",
            account_id=1,
            local_rel_path=rel_path,
            bytes=5,
            mime_type="image/jpeg",
            width=80,
            height=80,
            shot_at=datetime(2025, 7, 1, tzinfo=timezone.utc),
            imported_at=datetime(2025, 7, 2, tzinfo=timezone.utc),
            is_video=False,
            is_deleted=False,
            has_playback=False,
        )
        album = Album(
            name="Preview Album",
            description=None,
            visibility="private",
            cover_media_id=None,
        )
        db.session.add_all([media, album])
        db.session.commit()

        db.session.execute(
            album_item.insert(),
            [{"album_id": album.id, "media_id": media.id, "sort_index": 0}],
        )
        db.session.commit()

        return album.id, media.id


def test_album_detail_includes_full_size_thumbnail(client, app):
    rel_path = "albums/preview/test.jpg"
    thumbs_base = Path(os.environ["FPV_NAS_THUMBS_DIR"])
    for size in ("512", "2048"):
        target = thumbs_base / size / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"thumb")

    album_id, _ = _create_album_with_media(app, rel_path=rel_path)

    grant_permission(app, "media:view")
    grant_permission(app, "album:view")
    login(client)

    response = client.get(f"/api/albums/{album_id}")
    assert response.status_code == 200
    payload = response.get_json()
    media_items = payload["album"]["media"]
    assert len(media_items) == 1
    media_entry = media_items[0]
    assert media_entry["thumbnailUrl"].endswith("size=512")
    assert media_entry["fullUrl"].endswith("size=2048")


def test_album_detail_full_size_fallback(client, app):
    rel_path = "albums/preview/fallback.jpg"
    thumbs_base = Path(os.environ["FPV_NAS_THUMBS_DIR"])
    target = thumbs_base / "512" / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"thumb")

    album_id, _ = _create_album_with_media(app, rel_path=rel_path)

    grant_permission(app, "media:view")
    grant_permission(app, "album:view")
    login(client)

    response = client.get(f"/api/albums/{album_id}")
    assert response.status_code == 200
    payload = response.get_json()
    media_entry = payload["album"]["media"][0]
    assert media_entry["thumbnailUrl"].endswith("size=512")
    assert media_entry["fullUrl"].endswith("size=512")


def test_album_media_reorder_rejects_missing_ids(client, app):
    from webapp.extensions import db
    from core.models.photo_models import Media, Album, album_item

    with app.app_context():
        media1 = Media(
            google_media_id="album-reorder-missing-1",
            account_id=1,
            local_rel_path="album-reorder-missing-1.jpg",
            bytes=5,
            mime_type="image/jpeg",
            width=80,
            height=80,
            shot_at=datetime(2025, 8, 1, tzinfo=timezone.utc),
            imported_at=datetime(2025, 8, 2, tzinfo=timezone.utc),
            is_video=False,
            is_deleted=False,
            has_playback=False,
        )
        media2 = Media(
            google_media_id="album-reorder-missing-2",
            account_id=1,
            local_rel_path="album-reorder-missing-2.jpg",
            bytes=5,
            mime_type="image/jpeg",
            width=80,
            height=80,
            shot_at=datetime(2025, 8, 3, tzinfo=timezone.utc),
            imported_at=datetime(2025, 8, 4, tzinfo=timezone.utc),
            is_video=False,
            is_deleted=False,
            has_playback=False,
        )
        album = Album(
            name="Reorder Invalid",
            description=None,
            visibility="private",
            cover_media_id=None,
        )
        db.session.add_all([album, media1, media2])
        db.session.commit()

        db.session.execute(
            album_item.insert(),
            [
                {"album_id": album.id, "media_id": media1.id, "sort_index": 0},
                {"album_id": album.id, "media_id": media2.id, "sort_index": 1},
            ],
        )
        db.session.commit()

        media1_id = media1.id
        album_id = album.id

    grant_permission(app, "album:edit")
    login(client)

    response = client.put(
        f"/api/albums/{album_id}/media/order",
        json={"mediaIds": [media1_id]},
    )
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["error"] == "invalid_media_order"
def test_picker_session_service_allows_reimport_of_deleted_media(app):
    from webapp.extensions import db
    from core.models.photo_models import Media
    from core.models.picker_session import PickerSession
    from core.models.google_account import GoogleAccount
    from webapp.api.picker_session_service import PickerSessionService

    with app.app_context():
        account = GoogleAccount.query.first()
        assert account is not None

        session = PickerSession(
            account_id=account.id,
            session_id="picker_sessions/reimport",
            status="pending",
        )
        db.session.add(session)
        db.session.commit()

        deleted_media = Media(
            source_type="google_photos",
            google_media_id="gid-reimport",
            account_id=account.id,
            local_rel_path="2024/01/dup.jpg",
            filename="dup.jpg",
            hash_sha256="0" * 64,
            bytes=123,
            mime_type="image/jpeg",
            width=10,
            height=10,
            shot_at=datetime.now(timezone.utc),
            imported_at=datetime.now(timezone.utc),
            is_video=False,
            is_deleted=True,
        )
        db.session.add(deleted_media)
        db.session.commit()

        item = {
            "id": deleted_media.google_media_id,
            "createTime": datetime.now(timezone.utc).isoformat(),
            "mediaFile": {
                "mimeType": "image/jpeg",
                "filename": "dup.jpg",
                "baseUrl": "http://example.com/base",
                "mediaFileMetadata": {"width": "10", "height": "10"},
            },
        }

        selection = PickerSessionService._save_single_item(session, item)
        assert selection is not None
        assert selection.status == "pending"
        assert selection.google_media_id == deleted_media.google_media_id

