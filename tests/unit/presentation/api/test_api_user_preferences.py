"""ユーザー設定 API (`/api/user/preferences`) のユニットテスト。"""
from __future__ import annotations

import uuid
import pytest

from shared.kernel.database.db import db
from shared.infrastructure.models.user import User, Role, Permission
from shared.infrastructure.models.user_preference import UserPreference


def _create_user() -> User:
    role = Role(name=f"r-{uuid.uuid4().hex[:6]}")
    perm = Permission(code=f"gui:view-{uuid.uuid4().hex[:6]}")
    role.permissions.append(perm)
    user = User(email=f"u-{uuid.uuid4().hex[:8]}@example.com")
    user.set_password("pass")
    user.roles.append(role)
    db.session.add_all([perm, role, user])
    db.session.commit()
    return user


def _login(client, user: User):
    from flask import session as flask_session
    from flask_login import login_user
    from presentation.web.services.token_service import TokenService

    active_role_id = user.roles[0].id if user.roles else None
    with client.application.test_request_context():
        principal = TokenService.create_principal_for_user(user, active_role_id=active_role_id)
        login_user(principal)
        flask_session["_fresh"] = True
        persisted = dict(flask_session)

    with client.session_transaction() as session:
        session.update(persisted)
        session.modified = True


@pytest.fixture
def client(app_context):
    return app_context.test_client()


class TestUserPreferencesApi:
    def test_get_returns_defaults_when_no_setting(self, client, app_context):
        """設定なしの場合、デフォルト値が返ること。"""
        user = _create_user()
        _login(client, user)

        res = client.get("/api/user/preferences")
        assert res.status_code == 200
        data = res.get_json()
        assert "preferences" in data
        # slideshow_interval のデフォルトは 5
        assert data["preferences"]["slideshow_interval"] == 5

    def test_get_requires_authentication(self, client, app_context):
        """未認証では 401 が返ること。"""
        res = client.get("/api/user/preferences")
        assert res.status_code == 401

    def test_put_updates_slideshow_interval(self, client, app_context):
        """slideshow_interval を更新できること。"""
        user = _create_user()
        _login(client, user)

        res = client.put("/api/user/preferences", json={"slideshow_interval": 10})
        assert res.status_code == 200
        data = res.get_json()
        assert data["preferences"]["slideshow_interval"] == 10
        assert "slideshow_interval" in data["updated"]

    def test_put_persists_to_db(self, client, app_context):
        """PUT した値が DB に永続化されること。"""
        user = _create_user()
        _login(client, user)

        client.put("/api/user/preferences", json={"slideshow_interval": 8})

        row = UserPreference.query.filter_by(
            user_id=user.id, key=UserPreference.KEY_SLIDESHOW_INTERVAL
        ).first()
        assert row is not None
        assert row.value == 8

    def test_put_upserts_existing_value(self, client, app_context):
        """同じキーへの PUT は上書き（アップサート）されること。"""
        user = _create_user()
        _login(client, user)

        client.put("/api/user/preferences", json={"slideshow_interval": 7})
        res = client.put("/api/user/preferences", json={"slideshow_interval": 15})
        assert res.status_code == 200
        assert res.get_json()["preferences"]["slideshow_interval"] == 15

        # DB に重複行がないこと
        rows = UserPreference.query.filter_by(
            user_id=user.id, key=UserPreference.KEY_SLIDESHOW_INTERVAL
        ).all()
        assert len(rows) == 1

    def test_put_rejects_interval_below_minimum(self, client, app_context):
        """1秒未満の値は 400 が返ること。"""
        user = _create_user()
        _login(client, user)

        res = client.put("/api/user/preferences", json={"slideshow_interval": 0})
        assert res.status_code == 400
        assert res.get_json()["error"] == "value_out_of_range"

    def test_put_rejects_interval_above_maximum(self, client, app_context):
        """300秒超の値は 400 が返ること。"""
        user = _create_user()
        _login(client, user)

        res = client.put("/api/user/preferences", json={"slideshow_interval": 301})
        assert res.status_code == 400

    def test_put_rejects_non_integer_interval(self, client, app_context):
        """文字列など非数値は 400 が返ること。"""
        user = _create_user()
        _login(client, user)

        res = client.put("/api/user/preferences", json={"slideshow_interval": "fast"})
        assert res.status_code == 400
        assert res.get_json()["error"] == "invalid_value"

    def test_put_ignores_unknown_keys(self, client, app_context):
        """未知のキーは無視されること（エラーにならない）。"""
        user = _create_user()
        _login(client, user)

        res = client.put("/api/user/preferences", json={"unknown_key": "value", "slideshow_interval": 6})
        assert res.status_code == 200
        data = res.get_json()
        assert "unknown_key" not in data["preferences"]
        assert data["preferences"]["slideshow_interval"] == 6

    def test_preferences_are_isolated_per_user(self, client, app_context):
        """ユーザー設定は他のユーザーに影響しないこと。"""
        user_a = _create_user()
        user_b = _create_user()

        _login(client, user_a)
        client.put("/api/user/preferences", json={"slideshow_interval": 20})

        _login(client, user_b)
        res = client.get("/api/user/preferences")
        # user_b はデフォルト値のまま
        assert res.get_json()["preferences"]["slideshow_interval"] == 5
