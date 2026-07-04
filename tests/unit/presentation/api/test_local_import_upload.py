"""ローカルインポート手動アップロード API (`/api/sync/local-import/upload`) の単体テスト。"""
from __future__ import annotations

import io
import uuid
from unittest.mock import patch

import pytest

from shared.kernel.database.db import db
from shared.infrastructure.models.user import Permission, Role, User


def _create_user_with_perms(*perm_codes: str) -> User:
    perms = []
    for code in perm_codes:
        p = Permission(code=code)
        db.session.add(p)
        perms.append(p)

    role = Role(name=f"uploader-{uuid.uuid4().hex[:6]}")
    role.permissions = perms
    db.session.add(role)

    user = User(email=f"uploader-{uuid.uuid4().hex[:8]}@example.com")
    user.set_password("pass")
    user.roles.append(role)
    db.session.add(user)
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


def _config_for(import_dir: str, *, exists: bool = True) -> dict:
    info = {
        "raw": import_dir,
        "absolute": import_dir,
        "realpath": import_dir,
        "exists": exists,
    }
    return {
        "import_dir": import_dir,
        "originals_dir": import_dir,
        "import_dir_info": info,
        "originals_dir_info": info,
        "directories": [],
    }


@pytest.fixture
def client(app_context):
    return app_context.test_client()


@pytest.mark.usefixtures("app_context")
class TestLocalImportUploadApi:
    def test_upload_requires_permission(self, client, app_context, tmp_path):
        user = _create_user_with_perms()  # no permissions
        _login(client, user)

        res = client.post(
            "/api/sync/local-import/upload",
            data={"files": (io.BytesIO(b"data"), "photo.jpg")},
            content_type="multipart/form-data",
        )
        assert res.status_code == 403

    def test_upload_saves_supported_files(self, client, app_context, tmp_path):
        user = _create_user_with_perms("admin:photo-settings")
        _login(client, user)

        with patch(
            "presentation.web.api.routes_local_import._resolve_local_import_config",
            return_value=_config_for(str(tmp_path)),
        ):
            res = client.post(
                "/api/sync/local-import/upload",
                data={"files": (io.BytesIO(b"fake image"), "photo.jpg")},
                content_type="multipart/form-data",
            )

        assert res.status_code == 200
        payload = res.get_json()
        assert payload["success"] is True
        assert payload["saved"] == [{"filename": "photo.jpg", "size": len(b"fake image")}]
        assert (tmp_path / "photo.jpg").read_bytes() == b"fake image"

    def test_upload_rejects_unsupported_extension(self, client, app_context, tmp_path):
        user = _create_user_with_perms("admin:photo-settings")
        _login(client, user)

        with patch(
            "presentation.web.api.routes_local_import._resolve_local_import_config",
            return_value=_config_for(str(tmp_path)),
        ):
            res = client.post(
                "/api/sync/local-import/upload",
                data={"files": (io.BytesIO(b"binary"), "malware.exe")},
                content_type="multipart/form-data",
            )

        assert res.status_code == 400
        payload = res.get_json()
        assert payload["success"] is False
        assert payload["skipped"] == [
            {"filename": "malware.exe", "reason": "unsupported_extension"}
        ]
        assert list(tmp_path.iterdir()) == []

    def test_upload_avoids_overwriting_existing_files(self, client, app_context, tmp_path):
        user = _create_user_with_perms("admin:photo-settings")
        _login(client, user)

        (tmp_path / "photo.jpg").write_bytes(b"existing")

        with patch(
            "presentation.web.api.routes_local_import._resolve_local_import_config",
            return_value=_config_for(str(tmp_path)),
        ):
            res = client.post(
                "/api/sync/local-import/upload",
                data={"files": (io.BytesIO(b"new data"), "photo.jpg")},
                content_type="multipart/form-data",
            )

        assert res.status_code == 200
        payload = res.get_json()
        assert payload["saved"][0]["filename"] == "photo_1.jpg"
        assert (tmp_path / "photo.jpg").read_bytes() == b"existing"
        assert (tmp_path / "photo_1.jpg").read_bytes() == b"new data"

    def test_upload_fails_when_import_directory_missing(self, client, app_context, tmp_path):
        user = _create_user_with_perms("admin:photo-settings")
        _login(client, user)

        with patch(
            "presentation.web.api.routes_local_import._resolve_local_import_config",
            return_value=_config_for(str(tmp_path / "missing"), exists=False),
        ):
            res = client.post(
                "/api/sync/local-import/upload",
                data={"files": (io.BytesIO(b"data"), "photo.jpg")},
                content_type="multipart/form-data",
            )

        assert res.status_code == 409

    def test_upload_without_files_returns_400(self, client, app_context, tmp_path):
        user = _create_user_with_perms("admin:photo-settings")
        _login(client, user)

        with patch(
            "presentation.web.api.routes_local_import._resolve_local_import_config",
            return_value=_config_for(str(tmp_path)),
        ):
            res = client.post(
                "/api/sync/local-import/upload",
                data={},
                content_type="multipart/form-data",
            )

        assert res.status_code == 400
