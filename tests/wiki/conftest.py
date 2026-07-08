"""Wiki テスト用フィクスチャ。

``test_wiki_services.py`` は旧 conftest が提供していた ``app`` / ``db_session`` /
``test_user`` フィクスチャに依存している。Flask-SQLAlchemy ではなく SQLAlchemy を
直接使ったテスト用エンジンで提供する。
"""

from __future__ import annotations

import os

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import scoped_session, sessionmaker

from shared.kernel.database.db import db as _db
from shared.infrastructure.models.user import User


def _setup_test_env() -> None:
    for key, value in {
        "TESTING": "true",
        "DATABASE_URI": "sqlite:///:memory:",
        "SECRET_KEY": "test-secret",
        "JWT_SECRET_KEY": "test-jwt",
        "GOOGLE_CLIENT_ID": "",
        "GOOGLE_CLIENT_SECRET": "",
        "ACCESS_TOKEN_ISSUER": "test",
        "ACCESS_TOKEN_AUDIENCE": "test",
        "MEDIA_DOWNLOAD_SIGNING_KEY": "test-signing-key-32-bytes-padding",
        "ENCRYPTION_KEY": "a" * 32,
    }.items():
        os.environ.setdefault(key, value)


@pytest.fixture
def app(tmp_path):
    """テーブル作成済みのテスト用エンジンを提供する（Flask 不要）。"""
    _setup_test_env()

    # Wiki モデルをメタデータに登録
    import shared.infrastructure.models.user  # noqa: F401
    import shared.infrastructure.models.group  # noqa: F401
    import bounded_contexts.wiki.infrastructure.wiki_models  # noqa: F401

    engine = sa.create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    _db.metadata.create_all(engine)
    return engine


@pytest.fixture
def db_session(app):
    """アクティブな DB セッションを返す。テスト後にロールバックする。"""
    engine = app
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = scoped_session(factory)
    try:
        yield session()
    finally:
        session.remove()


@pytest.fixture
def test_user(db_session):
    """Wiki ページの作成者として利用するユーザーを作成する。"""
    user = User(email="wiki-user@example.com")
    user.set_password("password123")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user
