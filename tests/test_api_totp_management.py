import importlib
import os
import uuid

import pytest


@pytest.fixture()
def app(tmp_path):
    tmp_dir = tmp_path / "totp-api"
    tmp_dir.mkdir()
    db_path = tmp_dir / "test.db"

    original_env = {}
    for key, value in {
        "SECRET_KEY": "test",  # noqa: S105 - テスト用
        "JWT_SECRET_KEY": "jwt-secret",  # noqa: S105 - テスト用
        "DATABASE_URI": f"sqlite:///{db_path}",
    }.items():
        original_env[key] = os.environ.get(key)
        os.environ[key] = value

    import webapp.config as config_module

    config_module = importlib.reload(config_module)
    BaseApplicationSettings = config_module.BaseApplicationSettings

    BaseApplicationSettings.SQLALCHEMY_ENGINE_OPTIONS = {}
    from webapp import create_app

    app = create_app()
    app.config.update(TESTING=True)

    from webapp.extensions import db

    with app.app_context():
        db.create_all()
    # API 認証の動作を確認するために TESTING フラグでのログイン無効化を解除
    app.config["TESTING"] = False
    app.config["LOGIN_DISABLED"] = False

    yield app

    with app.app_context():
        db.session.remove()
        db.drop_all()

    for key, value in original_env.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


@pytest.fixture()
def client(app):
    return app.test_client()


def _create_user(app, *, permissions):
    from webapp.extensions import db
    from core.models.user import User, Role, Permission

    with app.app_context():
        perm_models = {}
        for code in permissions:
            perm = Permission.query.filter_by(code=code).first()
            if not perm:
                perm = Permission(code=code)
                db.session.add(perm)
            perm_models[code] = perm
        role = Role(name=f"role-{uuid.uuid4().hex[:6]}")
        role.permissions = [perm_models[code] for code in permissions]
        db.session.add(role)
        user = User(email=f"user-{uuid.uuid4().hex[:8]}@example.com")
        user.set_password("pass")
        user.roles.append(role)
        db.session.add(user)
        db.session.commit()
        return user.id


def _login(client, user_id):
    with client.session_transaction() as session:
        session["_user_id"] = str(user_id)
        session["_fresh"] = True


def test_totp_api_permission_flow(client, app):
    from webapp.extensions import db
    from core.models.totp import TOTPCredential

    viewer_id = _create_user(app, permissions=["totp:view"])
    editor_id = _create_user(app, permissions=["totp:view", "totp:write"])

    # 未ログインでは401
    res = client.get("/api/totp")
    assert res.status_code == 401

    # ビュー権限のみで一覧取得は可能
    _login(client, viewer_id)
    res = client.get("/api/totp")
    assert res.status_code == 200
    assert res.get_json()["items"] == []

    # ビュー権限のみでは登録は403
    res = client.post(
        "/api/totp",
        json={"account": "alice@example.com", "issuer": "Example", "secret": "JBSWY3DPEHPK3PXP"},
    )
    assert res.status_code == 403

    # 編集権限を持つユーザーでログインし直す
    _login(client, editor_id)

    # 新規登録
    res = client.post(
        "/api/totp",
        json={
            "account": "alice@example.com",
            "issuer": "Example",
            "secret": "JBSWY3DPEHPK3PXP",
            "description": "Example account",
        },
    )
    assert res.status_code == 201
    created = res.get_json()["item"]
    assert created["account"] == "alice@example.com"
    assert created["issuer"] == "Example"
    assert created["description"] == "Example account"
    assert created["otp"]
    credential_id = created["id"]

    # 一覧取得で OTP が含まれていること
    res = client.get("/api/totp")
    assert res.status_code == 200
    items = res.get_json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == credential_id
    assert items[0]["otp"]
    assert items[0]["remaining_seconds"] > 0

    # 別ユーザーは他人のTOTPを閲覧できない
    _login(client, viewer_id)
    res = client.get("/api/totp")
    assert res.status_code == 200
    assert res.get_json()["items"] == []

    # 以降の操作のため編集権限ユーザーに戻す
    _login(client, editor_id)

    # 更新（説明を変更）
    res = client.put(
        f"/api/totp/{credential_id}",
        json={"description": "Updated", "digits": 6, "period": 30},
    )
    assert res.status_code == 200
    updated = res.get_json()["item"]
    assert updated["description"] == "Updated"

    # エクスポート
    res = client.get("/api/totp/export")
    assert res.status_code == 200
    exported = res.get_json()
    assert len(exported) == 1
    assert exported[0]["account"] == "alice@example.com"
    assert exported[0]["secret"] == "JBSWY3DPEHPK3PXP"

    # インポート - 既存と重複で409
    res = client.post(
        "/api/totp/import",
        json={
            "items": [
                {
                    "account": "alice@example.com",
                    "issuer": "Example",
                    "secret": "JBSWY3DPEHPK3PXP",
                    "created_at": "2025-10-15T14:00:00Z",
                }
            ]
        },
    )
    assert res.status_code == 409
    conflicts = res.get_json()["conflicts"]
    assert conflicts and conflicts[0]["account"] == "alice@example.com"

    # 強制インポートで上書き
    res = client.post(
        "/api/totp/import",
        json={
            "force": True,
            "items": [
                {
                    "account": "bob@example.com",
                    "issuer": "Example",
                    "secret": "NB2W45DFOIZA====",
                    "description": "Bob",
                    "digits": 6,
                    "period": 30,
                    "created_at": "2025-10-16T12:00:00Z",
                }
            ],
        },
    )
    assert res.status_code == 200
    result = res.get_json()
    assert result["imported"]

    with app.app_context():
        credentials = db.session.query(TOTPCredential).all()
        assert len(credentials) == 2
        assert all(credential.user_id == editor_id for credential in credentials)

    # 削除
    res = client.delete(f"/api/totp/{credential_id}")
    assert res.status_code == 200
    assert res.get_json()["result"] == "deleted"

    with app.app_context():
        assert db.session.get(TOTPCredential, credential_id) is None
