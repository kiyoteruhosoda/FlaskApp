"""Wiki テスト用フィクスチャ。

``test_wiki_services.py`` は旧 conftest が提供していた ``app`` / ``db_session`` /
``test_user`` フィクスチャに依存している。Flask-SQLAlchemy ではなく SQLAlchemy を
直接使ったテスト用エンジンで提供する。
"""

from __future__ import annotations

import os
from contextlib import contextmanager

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


class _FakeApp:
    """Flask の app.app_context() を模倣する軽量スタブ。"""

    @contextmanager
    def app_context(self):
        yield


@pytest.fixture
def app(tmp_path):
    """テーブル作成済みのテスト用エンジンを提供する（Flask 不要）。"""
    _setup_test_env()

    # Wiki モデルをメタデータに登録（FKが参照するすべてのモデルを先にインポート）
    import shared.infrastructure.models  # noqa: F401
    from shared.infrastructure.models.impersonation_audit_log import ImpersonationAuditLog  # noqa: F401
    from bounded_contexts.certs.infrastructure.models import (  # noqa: F401
        CertificateGroupEntity, IssuedCertificateEntity, CertificatePrivateKeyEntity,
    )
    from bounded_contexts.picker_import.infrastructure.picker_session import PickerSession  # noqa: F401
    from bounded_contexts.photonest.infrastructure import photo_models as _pm  # noqa: F401
    from bounded_contexts.totp.infrastructure.totp_models import TOTPCredential  # noqa: F401
    import bounded_contexts.wiki.infrastructure.wiki_models  # noqa: F401

    engine = sa.create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    _db.init_app_engine(engine)
    _db.metadata.create_all(engine)
    try:
        yield _FakeApp()
    finally:
        _db.session.remove()
        _db.metadata.drop_all(engine)


@pytest.fixture
def db_session(app):
    """アクティブな DB セッションを返す。テスト後にロールバックする。"""
    session = _db.session
    try:
        yield session
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
