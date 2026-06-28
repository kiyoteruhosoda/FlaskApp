"""重複検出 API (`GET /api/media/duplicates`) のテスト。"""
import base64
import os
import uuid
from datetime import datetime, timezone

import pytest

from shared.kernel.database.db import db


@pytest.fixture
def app(tmp_path):
    db_path = tmp_path / "test.db"
    os.environ["SECRET_KEY"] = "test"
    os.environ["DATABASE_URI"] = f"sqlite:///{db_path}"
    os.environ["GOOGLE_CLIENT_ID"] = "cid"
    os.environ["GOOGLE_CLIENT_SECRET"] = "sec"
    os.environ["ENCRYPTION_KEY"] = base64.urlsafe_b64encode(b"0" * 32).decode()
    os.environ["MEDIA_DOWNLOAD_SIGNING_KEY"] = base64.urlsafe_b64encode(b"1" * 32).decode()
    for key in ("MEDIA_THUMBNAILS_DIRECTORY", "MEDIA_PLAYBACK_DIRECTORY", "MEDIA_ORIGINALS_DIRECTORY"):
        d = tmp_path / key.lower()
        d.mkdir()
        os.environ[key] = str(d)

    from presentation.web.bootstrap.config import BaseApplicationSettings

    BaseApplicationSettings.SQLALCHEMY_ENGINE_OPTIONS = {}
    from presentation.web import create_app

    app = create_app()
    app.config.update(TESTING=True)

    from shared.infrastructure.models.user import User

    with app.app_context():
        db.create_all()
        user = User(email="u@example.com")
        user.set_password("pass")
        db.session.add(user)
        db.session.commit()

    yield app


@pytest.fixture
def client(app):
    return app.test_client()


def _login(client):
    client.post(
        "/auth/login",
        data={"email": "u@example.com", "password": "pass"},
        follow_redirects=True,
    )


def _grant(app, code: str) -> None:
    from shared.infrastructure.models.user import User, Role, Permission

    with app.app_context():
        perm = Permission.query.filter_by(code=code).first() or Permission(code=code)
        db.session.add(perm)
        db.session.flush()
        role = Role.query.filter_by(name="reviewer").first() or Role(name="reviewer")
        db.session.add(role)
        db.session.flush()
        if perm not in role.permissions:
            role.permissions.append(perm)
        user = User.query.first()
        if role not in user.roles:
            user.roles.append(role)
        db.session.commit()


def _add_media(app, *, sha=None, phash=None, deleted=False, **extra) -> int:
    from bounded_contexts.photonest.infrastructure.photo_models import Media

    with app.app_context():
        media = Media(
            source_type="local",
            google_media_id=None,
            local_rel_path=f"{uuid.uuid4()}.jpg",
            filename=extra.get("filename", "f.jpg"),
            hash_sha256=sha,
            phash=phash,
            bytes=extra.get("bytes", 10),
            width=100,
            height=100,
            shot_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
            imported_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
            is_video=False,
            is_deleted=deleted,
            has_playback=False,
        )
        db.session.add(media)
        db.session.commit()
        return media.id


def test_requires_media_view_permission(app, client):
    _login(client)
    resp = client.get("/api/media/duplicates")
    assert resp.status_code == 403


def test_exact_duplicates_grouped_by_sha256(app, client):
    _grant(app, "media:view")
    _login(client)
    _add_media(app, sha="a" * 64)
    _add_media(app, sha="a" * 64)
    _add_media(app, sha="b" * 64)  # unique → not a group

    resp = client.get("/api/media/duplicates")
    assert resp.status_code == 200
    groups = resp.get_json()["groups"]
    assert len(groups) == 1
    assert groups[0]["match_type"] == "exact"
    assert groups[0]["count"] == 2


def test_similar_group_excludes_exact_members(app, client):
    _grant(app, "media:view")
    _login(client)
    # exact pair (同一 sha) かつ phash も同じ
    _add_media(app, sha="c" * 64, phash="p" * 16)
    _add_media(app, sha="c" * 64, phash="p" * 16)
    # phash だけ一致（sha は別） → similar
    _add_media(app, sha="d" * 64, phash="q" * 16)
    _add_media(app, sha="e" * 64, phash="q" * 16)

    resp = client.get("/api/media/duplicates")
    groups = {g["match_type"]: g for g in resp.get_json()["groups"]}
    assert groups["exact"]["count"] == 2
    assert groups["similar"]["count"] == 2
    # similar グループに exact メンバー(phash="p")が混ざらない
    assert all(it["id"] for it in groups["similar"]["items"])
    similar_phash_group_keys = [g["key"] for g in resp.get_json()["groups"] if g["match_type"] == "similar"]
    assert similar_phash_group_keys == ["phash:" + "q" * 16]


def test_deleted_media_excluded(app, client):
    _grant(app, "media:view")
    _login(client)
    _add_media(app, sha="f" * 64)
    _add_media(app, sha="f" * 64, deleted=True)  # 削除済みは除外 → グループ不成立

    resp = client.get("/api/media/duplicates")
    assert resp.get_json()["groups"] == []
