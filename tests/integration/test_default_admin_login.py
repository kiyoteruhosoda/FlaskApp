"""初期管理者アカウントが案内どおりの認証情報でログインできることを検証する回帰テスト。

``shared/domain/auth/master_data.py`` の ``DEFAULT_ADMIN_PASSWORD_HASH``
（``ADMIN_INITIAL_PASSWORD`` 未指定時にマイグレーションが投入する
フォールバックハッシュ）は、案内どおりの ``admin@example.com`` /
``admin@example.com`` でログインできる必要がある。ハッシュとドキュメントの
平文が乖離するとログインできなくなる（401 invalid_credentials）ため、その
再発を防止する。

本テストは全マイグレーションを空DBへ適用したあと、実際に
``AuthService.authenticate()`` を通してログインできることを確認する。
"""
from __future__ import annotations

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from tests.integration.test_migration_model_consistency import (
    _apply_all_migrations,
    _setup_test_env,
)


@pytest.mark.integration
def test_default_admin_can_login_with_documented_credentials():
    _setup_test_env()

    from shared.domain.auth.master_data import DEFAULT_ADMIN_EMAIL

    engine = sa.create_engine("sqlite://")
    connection = engine.connect()
    try:
        applied = _apply_all_migrations(connection)
        connection.commit()
        assert applied, "適用可能なマイグレーションがありません"

        from shared.application.auth_service import AuthService
        from shared.domain.user import UserRegistrationService
        from shared.infrastructure.user_repository import SqlAlchemyUserRepository

        session = Session(bind=connection)
        try:
            user_repo = SqlAlchemyUserRepository(session)
            auth_service = AuthService(user_repo, UserRegistrationService(user_repo))

            authenticated = auth_service.authenticate(
                DEFAULT_ADMIN_EMAIL, DEFAULT_ADMIN_EMAIL
            )
            assert authenticated is not None, (
                f"案内どおりの認証情報（{DEFAULT_ADMIN_EMAIL} / {DEFAULT_ADMIN_EMAIL}）で"
                "ログインできません。"
                " DEFAULT_ADMIN_PASSWORD_HASH がドキュメントの平文と一致していません。"
            )
            assert authenticated.email == DEFAULT_ADMIN_EMAIL

            # 誤った平文では認証できないことも確認（ハッシュが緩すぎないことの担保）
            assert (
                auth_service.authenticate(DEFAULT_ADMIN_EMAIL, "wrong-password") is None
            )
        finally:
            session.close()
    finally:
        connection.close()
