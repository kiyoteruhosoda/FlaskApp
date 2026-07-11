"""実際の /api/auth/login → 管理APIの一気通貫回帰テスト。

過去、``migrations/versions/0900277b3348_sync_role_permissions_with_master_data.py``
で「admin ロールが role_permissions に不足している権限を持つ」ケースを修正したが、
デプロイ後も初期管理者で管理画面（System Overview 等）が「You do not have
permission to view this page」のままだった。

原因は DB 側ではなく ``presentation/fastapi/routers/auth.py`` の
``POST /api/auth/login`` にあった: このハンドラは要求された scope
（リクエストボディの ``scope``）と保有権限の積を発行するが、
``"gui:view" in requested_scope`` の場合のみ全権限を発行する特別扱いをしていた。
一方ブラウザSPA（``frontend/src/pages/LoginPage.tsx``）は ``scope`` を一切
送っておらず、常に空集合との積＝空 scope の JWT が発行されていた。
DB 側の役割・権限がどれだけ正しくても、この空 scope により全ての
``@require_perms`` / ``principal.can()`` ガードが常に拒否していた。

``tests/integration/fastapi/test_login_totp.py`` は
``TokenService.generate_token_pair`` をモックしているため、この scope 計算
バグを検出できない。``tests/integration/test_admin_role_permissions.py`` は
DB の role_permissions のみを検証し、ログインAPIを経由しない。
本テストは実DB（migrations 適用済み）＋実 FastAPI アプリを起動し、
フロントエンドが実際に送るリクエスト形（``scope: ["gui:view"]``）で
``/api/auth/login`` を叩き、返ってきたアクセストークンで実際に
``GET /api/admin/dashboard``（``admin:system-settings`` 権限が必要）が
成功することまで確認する。
"""
from __future__ import annotations

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from tests.integration.test_migration_model_consistency import (
    ROOT,
    _setup_test_env,
)

ALEMBIC_INI = ROOT / "migrations" / "alembic.ini"


@pytest.fixture()
def admin_client(tmp_path, monkeypatch) -> TestClient:
    """全マイグレーション適用済みDB＋実FastAPIアプリのテストクライアントを返す。

    ``shared.kernel.database.session._engine`` はプロセス内で使い回される
    シングルトンで、他のテストが先に ``get_db()`` を呼ぶと別の（マイグレー
    ション未適用の）DBに固定されてしまう。本テストは実DBスキーマの検証が
    目的のため、FastAPI ルーター側は ``app.dependency_overrides`` で
    このテスト専用のセッションに差し替える。JWT署名鍵解決
    (``SystemSettingService``) は Flask-SQLAlchemy 互換のグローバル
    ``shared.kernel.database.db.db.session`` を直接参照するため、
    ``tests/conftest.py`` の ``app_context`` フィクスチャと同じ
    ``db.init_app_engine()`` で同じDBへ揃える。
    """
    _setup_test_env()

    db_path = tmp_path / "login_scope.db"
    url = f"sqlite:///{db_path}"
    # migrations/env.py は DATABASE_URI 環境変数を Config の sqlalchemy.url より
    # 優先して自前で再解決するため、ここで一致させないと別のDBに適用されてしまう。
    monkeypatch.setenv("DATABASE_URI", url)

    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")

    from presentation.fastapi.app import create_app
    from shared.kernel.database.session import get_db
    from shared.kernel.database.db import db as legacy_db

    engine = sa.create_engine(url, connect_args={"check_same_thread": False})
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)
    legacy_db.init_app_engine(engine)

    def _override_get_db():
        db = session_factory()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield TestClient(app, raise_server_exceptions=True)
    finally:
        app.dependency_overrides.pop(get_db, None)
        legacy_db.session.remove()
        engine.dispose()


@pytest.mark.integration
def test_admin_login_scope_grants_access_to_admin_dashboard(admin_client: TestClient) -> None:
    """SPAが送るリクエスト形（scope=["gui:view"]）でログインすると、
    管理画面API（admin:system-settings 必須）へ実際にアクセスできること。
    """
    from shared.domain.auth.master_data import DEFAULT_ADMIN_EMAIL

    login_resp = admin_client.post(
        "/api/auth/login",
        json={"email": DEFAULT_ADMIN_EMAIL, "password": "admin", "scope": ["gui:view"]},
    )
    assert login_resp.status_code == 200, login_resp.text

    body = login_resp.json()
    granted_scope = set(body["scope"].split())
    assert "admin:system-settings" in granted_scope, (
        f"admin ログインで admin:system-settings が発行されていません: {granted_scope}"
    )

    dashboard_resp = admin_client.get(
        "/api/admin/dashboard",
        headers={"Authorization": f"Bearer {body['access_token']}"},
    )
    assert dashboard_resp.status_code == 200, dashboard_resp.text


@pytest.mark.integration
def test_admin_login_without_scope_field_grants_no_permissions(admin_client: TestClient) -> None:
    """回帰確認: scope未指定のログインリクエストは権限なしのJWTを発行する
    （バックエンドの意図した挙動）。フロントエンドが scope を送り忘れると
    この空トークンになり、あらゆる管理画面が「権限がありません」になる。
    """
    from shared.domain.auth.master_data import DEFAULT_ADMIN_EMAIL

    login_resp = admin_client.post(
        "/api/auth/login",
        json={"email": DEFAULT_ADMIN_EMAIL, "password": "admin"},
    )
    assert login_resp.status_code == 200, login_resp.text
    assert login_resp.json()["scope"] == ""


def _revoke_admin_permission(admin_client: TestClient, code: str) -> None:
    """テスト用: admin ロールから権限コードのリンクを直接剥奪する。"""
    from shared.kernel.database.session import get_db

    override = admin_client.app.dependency_overrides[get_db]
    gen = override()
    db = next(gen)
    try:
        db.execute(
            sa.text(
                "DELETE FROM role_permissions WHERE perm_id IN "
                "(SELECT id FROM permission WHERE code = :code) "
                "AND role_id IN (SELECT id FROM role WHERE name = 'admin')"
            ),
            {"code": code},
        )
        db.commit()
    finally:
        gen.close()


@pytest.mark.integration
def test_refresh_recomputes_scope_from_current_db_permissions(admin_client: TestClient) -> None:
    """権限剥奪がトークンリフレッシュで即時反映されること。

    旧実装はリフレッシュトークンに埋め込まれた発行時 scope を無検証で
    引き継いでいたため、剥奪した権限を持つ JWT がローテーションの度に
    再発行され、最長30日間（リフレッシュトークン寿命）権限が生き続けた。
    """
    from shared.domain.auth.master_data import DEFAULT_ADMIN_EMAIL

    login_resp = admin_client.post(
        "/api/auth/login",
        json={"email": DEFAULT_ADMIN_EMAIL, "password": "admin", "scope": ["gui:view"]},
    )
    assert login_resp.status_code == 200, login_resp.text
    body = login_resp.json()
    assert "wiki:admin" in body["scope"].split()

    # ログイン後に管理者から wiki:admin を剥奪
    _revoke_admin_permission(admin_client, "wiki:admin")

    refresh_resp = admin_client.post(
        "/api/auth/refresh",
        json={"refresh_token": body["refresh_token"]},
    )
    assert refresh_resp.status_code == 200, refresh_resp.text
    refreshed_scope = set(refresh_resp.json()["scope"].split())

    assert "wiki:admin" not in refreshed_scope, (
        "剥奪済みの権限がリフレッシュ後の scope に残っています"
    )
    # 剥奪していない権限は維持される（gui:view セッションは全保有権限を再交付）
    assert "admin:system-settings" in refreshed_scope


@pytest.mark.integration
def test_refresh_does_not_escalate_legacy_empty_scope_token(admin_client: TestClient) -> None:
    """発行時 scope が空のリフレッシュトークン（scope送信バグ時代のセッション）は、
    リフレッシュしても空のまま（勝手に昇格しない）。該当ユーザーは一度
    再ログインが必要（ログインは常に現在の権限から再計算するため復旧する）。
    """
    from shared.domain.auth.master_data import DEFAULT_ADMIN_EMAIL

    login_resp = admin_client.post(
        "/api/auth/login",
        json={"email": DEFAULT_ADMIN_EMAIL, "password": "admin"},  # scope なし
    )
    assert login_resp.status_code == 200, login_resp.text
    body = login_resp.json()
    assert body["scope"] == ""

    refresh_resp = admin_client.post(
        "/api/auth/refresh",
        json={"refresh_token": body["refresh_token"]},
    )
    assert refresh_resp.status_code == 200, refresh_resp.text
    assert refresh_resp.json()["scope"] == "", (
        "空 scope のリフレッシュトークンが権限を獲得しています（権限昇格）"
    )
