"""`check_duplicate_media` の単一実装統合後の挙動テスト。

旧実装へのサイレントフォールバックを廃止し、唯一の正準実装
（`MediaRepositoryImpl.find_by_signature`）に委譲することを検証する。
"""
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import pytest

from shared.kernel.database.db import db


@dataclass
class FakeAnalysis:
    """`check_duplicate_media` が参照する MediaFileAnalysis の最小代替。"""

    file_hash: str
    file_size: int
    perceptual_hash: Optional[str]
    shot_at: Optional[datetime]
    width: Optional[int]
    height: Optional[int]
    duration_ms: Optional[int]
    is_video: bool


@pytest.fixture
def app(tmp_path):
    os.environ["SECRET_KEY"] = "test"
    os.environ["DATABASE_URI"] = f"sqlite:///{tmp_path / 'test.db'}"
    os.environ["GOOGLE_CLIENT_ID"] = "cid"
    os.environ["GOOGLE_CLIENT_SECRET"] = "sec"
    from presentation.web.bootstrap.config import BaseApplicationSettings

    BaseApplicationSettings.SQLALCHEMY_ENGINE_OPTIONS = {}
    from presentation.web import create_app

    app = create_app()
    app.config.update(TESTING=True)
    with app.app_context():
        db.create_all()
    yield app


def _add_media(app, *, sha, phash=None, shot_at=None, w=100, h=100, deleted=False):
    from bounded_contexts.photonest.infrastructure.photo_models import Media

    with app.app_context():
        media = Media(
            source_type="local",
            local_rel_path=f"{sha}.jpg",
            hash_sha256=sha,
            phash=phash,
            bytes=10,
            width=w,
            height=h,
            shot_at=shot_at or datetime(2025, 1, 1, tzinfo=timezone.utc),
            imported_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
            is_video=False,
            is_deleted=deleted,
            has_playback=False,
        )
        db.session.add(media)
        db.session.commit()
        return media.id


def _analysis(sha, *, phash=None, shot_at=None, w=100, h=100):
    return FakeAnalysis(
        file_hash=sha,
        file_size=10,
        perceptual_hash=phash,
        shot_at=shot_at or datetime(2025, 1, 1, tzinfo=timezone.utc),
        width=w,
        height=h,
        duration_ms=None,
        is_video=False,
    )


def test_exact_match_by_sha256(app):
    from bounded_contexts.photonest.tasks.local_import import check_duplicate_media

    sha = "a" * 64
    mid = _add_media(app, sha=sha)
    with app.app_context():
        found = check_duplicate_media(_analysis(sha))
        assert found is not None and found.id == mid


def test_match_by_phash_and_metadata(app):
    from bounded_contexts.photonest.tasks.local_import import check_duplicate_media

    # sha は別だが phash＋メタデータが一致 → 重複扱い
    mid = _add_media(app, sha="b" * 64, phash="p" * 16)
    with app.app_context():
        found = check_duplicate_media(_analysis("c" * 64, phash="p" * 16))
        assert found is not None and found.id == mid


def test_no_duplicate_returns_none(app):
    from bounded_contexts.photonest.tasks.local_import import check_duplicate_media

    _add_media(app, sha="d" * 64)
    with app.app_context():
        assert check_duplicate_media(_analysis("e" * 64)) is None


def test_invalid_hash_is_handled_gracefully(app):
    """不正なハッシュ（FileHash 検証失敗）でも例外を投げず None を返す。"""
    from bounded_contexts.photonest.tasks.local_import import check_duplicate_media

    with app.app_context():
        # 64桁でない・非16進などは FileHash が ValueError を投げるが、
        # 旧実装フォールバックではなく「重複なし」で継続する。
        assert check_duplicate_media(_analysis("not-a-valid-hash")) is None
        assert check_duplicate_media(_analysis("")) is None
