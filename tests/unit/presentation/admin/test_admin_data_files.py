from urllib.parse import urlparse

import pytest

from shared.infrastructure.models.user import User, Role, Permission
from presentation.web.bootstrap.extensions import db


# NOTE: データファイル閲覧機能（ディレクトリ別ファイル一覧・フィルタ・ページング）は
# React SPA 移行で廃止された。サーバルート ``/admin/data-files`` は ``/`` へ
# リダイレクトするスタブで、対応する API も存在しない。そのため当該機能の
# 一覧/フィルタ/ページングを検証していたテストは削除した。アクセス制御
# （非管理者の拒否）のみ下記で引き続き検証する。


@pytest.fixture
def client(app_context):
    return app_context.test_client()


def _login(client, user):
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


def test_data_files_requires_system_manage_permission(client):
    user = User(email="user@example.com")
    user.set_password("secret")
    db.session.add(user)
    db.session.commit()

    _login(client, user)

    response = client.get("/admin/data-files")
    assert response.status_code == 302
    with client.application.test_request_context():
        target = urlparse(response.headers["Location"])
        assert target.path == "/"
