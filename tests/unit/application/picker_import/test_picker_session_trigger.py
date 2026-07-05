"""セッション作成のきっかけ（誰の操作か／自動か）が picker_session に記録されることの単体テスト。"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from bounded_contexts.picker_import.infrastructure.picker_session import PickerSession
from shared.infrastructure.models.user import Permission, Role, User
from shared.kernel.database.db import db


def _create_user_with_perms(*perm_codes: str) -> User:
    perms = []
    for code in perm_codes:
        p = Permission(code=code)
        db.session.add(p)
        perms.append(p)

    role = Role(name=f"trigger-{uuid.uuid4().hex[:6]}")
    role.permissions = perms
    db.session.add(role)

    user = User(email=f"trigger-{uuid.uuid4().hex[:8]}@example.com")
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


@pytest.fixture
def client(app_context):
    return app_context.test_client()


@pytest.mark.usefixtures("app_context")
class TestPickerSessionTrigger:
    def test_manual_local_import_records_user_trigger(self, client, app_context):
        """手動トリガー（API）で作られたセッションは trigger=user と操作ユーザーを持つ。"""
        user = _create_user_with_perms("system:manage")
        _login(client, user)

        fake_task = MagicMock()
        fake_task.id = "celery-task-id"
        with patch(
            "cli.src.celery.tasks.local_import_task_celery.delay",
            return_value=fake_task,
        ):
            res = client.post("/api/sync/local-import")

        assert res.status_code == 200
        session_id = res.get_json()["session_id"]
        ps = PickerSession.query.filter_by(session_id=session_id).one()
        assert ps.trigger == "user"
        assert ps.triggered_by_user_id == user.id

    def test_default_trigger_is_unknown(self, app_context):
        """明示されない場合（過去データ相当）は trigger=unknown・操作ユーザーなし。"""
        ps = PickerSession(session_id=f"legacy_{uuid.uuid4().hex[:8]}", status="pending")
        db.session.add(ps)
        db.session.commit()

        assert ps.trigger == "unknown"
        assert ps.triggered_by_user_id is None

    def test_worker_created_session_records_worker_trigger(self, app_context):
        """セッションID無しで走った取り込み（自動処理）は trigger=worker で記録される。"""
        from bounded_contexts.photonest.application.local_import.use_case import (
            LocalImportUseCase,
        )

        use_case = LocalImportUseCase.__new__(LocalImportUseCase)
        use_case._db = db
        use_case._logger = MagicMock()

        result = MagicMock()
        session = use_case._load_or_create_session(None, result, celery_task_id=None)

        assert session is not None
        assert session.trigger == "worker"
        assert session.triggered_by_user_id is None
