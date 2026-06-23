"""Wiki テスト用フィクスチャ。

``test_wiki_services.py`` は旧 conftest が提供していた ``app`` / ``db_session`` /
``test_user`` フィクスチャに依存している。テスト再編でこれらが失われ、全テストが
収集時エラー（→ skip 化）になっていたため、ここで再提供する。
"""

from __future__ import annotations

import pytest

from presentation.web import create_app
from presentation.web.bootstrap.extensions import db as _db
from shared.infrastructure.models.user import User
from tests.config import TestConfig


@pytest.fixture
def app():
    """テーブル作成済みのテスト用 Flask アプリケーションを提供する。"""
    app = create_app()
    app.config.from_object(TestConfig)

    with app.app_context():
        _db.create_all()
        try:
            yield app
        finally:
            _db.session.remove()
            _db.drop_all()


@pytest.fixture
def db_session(app):
    """アクティブな DB セッションを返す。"""
    return _db.session


@pytest.fixture
def test_user(app):
    """Wiki ページの作成者として利用するユーザーを作成する。"""
    user = User(email="wiki-user@example.com")
    user.set_password("password123")
    _db.session.add(user)
    _db.session.commit()
    _db.session.refresh(user)
    return user
