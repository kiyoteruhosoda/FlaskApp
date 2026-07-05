"""PickerSessionService.advance_active_sessions のテスト。

Google フォト側で選択が完了したセッションをサーバー側で自動的に
取り込み開始する定期処理（Celery beat から実行）の挙動を検証する。
"""

import base64
import json
import os
from datetime import datetime, timedelta, timezone

import pytest

from shared.kernel.crypto.crypto import encrypt
from shared.kernel.database.db import db


@pytest.fixture
def app(tmp_path):
    db_path = tmp_path / "test.db"
    db_uri = f"sqlite:///{db_path}"
    os.environ["SECRET_KEY"] = "test"
    os.environ["DATABASE_URI"] = db_uri
    os.environ["GOOGLE_CLIENT_ID"] = "cid"
    os.environ["GOOGLE_CLIENT_SECRET"] = "sec"
    key = base64.urlsafe_b64encode(b"0" * 32).decode()
    os.environ["ENCRYPTION_KEY"] = key
    from presentation.web.bootstrap.config import BaseApplicationSettings
    BaseApplicationSettings.SQLALCHEMY_ENGINE_OPTIONS = {}
    from presentation.web import create_app
    app = create_app()
    app.config.update(TESTING=True)
    app.config["ENCRYPTION_KEY"] = key
    from shared.infrastructure.models.google_account import GoogleAccount
    with app.app_context():
        db.create_all()
        if not GoogleAccount.query.filter_by(email="g@example.com").first():
            acc = GoogleAccount(
                email="g@example.com",
                scopes="",
                oauth_token_json=encrypt(json.dumps({"refresh_token": "r"})),
            )
            db.session.add(acc)
        db.session.commit()
    yield app


def _create_session(app, **kwargs):
    from bounded_contexts.picker_import.infrastructure.picker_session import PickerSession

    with app.app_context():
        defaults = dict(
            account_id=1,
            session_id="picker_sessions/test",
            status="pending",
            media_items_set=False,
        )
        defaults.update(kwargs)
        ps = PickerSession(**defaults)
        db.session.add(ps)
        db.session.commit()
        return ps.id


def test_advance_starts_import_when_media_items_set(app, monkeypatch):
    from bounded_contexts.picker_import.application.picker_session_service import (
        PickerSessionService,
    )

    ps_id = _create_session(
        app,
        media_items_set=True,
        expire_time=datetime.now(timezone.utc) + timedelta(hours=1),
    )

    called = {}

    def fake_media_items(session_id, cursor=None):
        called["session_id"] = session_id
        return {"saved": 3, "duplicates": 0}, 200

    monkeypatch.setattr(PickerSessionService, "media_items", staticmethod(fake_media_items))

    with app.app_context():
        metrics = PickerSessionService.advance_active_sessions()

    assert called["session_id"] == "picker_sessions/test"
    assert metrics["started"] == 1
    assert metrics["expired"] == 0
    assert metrics["errors"] == 0
    assert ps_id is not None


def test_advance_expires_stale_unselected_session(app):
    from bounded_contexts.picker_import.application.picker_session_service import (
        PickerSessionService,
    )
    from bounded_contexts.picker_import.infrastructure.picker_session import PickerSession

    ps_id = _create_session(
        app,
        media_items_set=False,
        expire_time=datetime.now(timezone.utc) - timedelta(minutes=5),
    )

    with app.app_context():
        metrics = PickerSessionService.advance_active_sessions()
        ps = db.session.get(PickerSession, ps_id)
        assert ps.status == "expired"

    assert metrics["expired"] == 1
    assert metrics["started"] == 0


def test_advance_polls_google_when_not_yet_selected(app, monkeypatch):
    from bounded_contexts.picker_import.application.picker_session_service import (
        PickerSessionService,
    )
    from bounded_contexts.picker_import.infrastructure.picker_session import PickerSession

    ps_id = _create_session(
        app,
        media_items_set=False,
        expire_time=datetime.now(timezone.utc) + timedelta(hours=1),
    )

    monkeypatch.setattr(
        PickerSessionService,
        "_auth_headers",
        staticmethod(lambda account_id: {"Authorization": "Bearer t"}),
    )

    def fake_snapshot(ps, headers, session_id):
        # Google 側で選択が完了した状態を模擬
        ps.media_items_set = True
        db.session.commit()

    monkeypatch.setattr(
        PickerSessionService,
        "_refresh_session_snapshot",
        staticmethod(fake_snapshot),
    )

    started = {}

    def fake_media_items(session_id, cursor=None):
        started["session_id"] = session_id
        return {"saved": 1, "duplicates": 0}, 200

    monkeypatch.setattr(PickerSessionService, "media_items", staticmethod(fake_media_items))

    with app.app_context():
        metrics = PickerSessionService.advance_active_sessions()
        ps = db.session.get(PickerSession, ps_id)
        assert ps.media_items_set is True

    assert started["session_id"] == "picker_sessions/test"
    assert metrics["started"] == 1


def test_advance_skips_local_import_sessions(app, monkeypatch):
    from bounded_contexts.picker_import.application.picker_session_service import (
        PickerSessionService,
    )

    _create_session(
        app,
        account_id=None,
        session_id="local-import-xyz",
        status="pending",
    )

    def fail_media_items(session_id, cursor=None):  # pragma: no cover - 呼ばれないこと
        raise AssertionError("local import session must not be advanced")

    monkeypatch.setattr(PickerSessionService, "media_items", staticmethod(fail_media_items))

    with app.app_context():
        metrics = PickerSessionService.advance_active_sessions()

    assert metrics["checked"] == 0


def test_advance_keeps_waiting_session_pending(app, monkeypatch):
    from bounded_contexts.picker_import.application.picker_session_service import (
        PickerSessionService,
    )
    from bounded_contexts.picker_import.infrastructure.picker_session import PickerSession

    ps_id = _create_session(
        app,
        media_items_set=False,
        expire_time=datetime.now(timezone.utc) + timedelta(hours=1),
    )

    monkeypatch.setattr(
        PickerSessionService,
        "_auth_headers",
        staticmethod(lambda account_id: {"Authorization": "Bearer t"}),
    )
    monkeypatch.setattr(
        PickerSessionService,
        "_refresh_session_snapshot",
        staticmethod(lambda ps, headers, session_id: None),
    )

    with app.app_context():
        metrics = PickerSessionService.advance_active_sessions()
        ps = db.session.get(PickerSession, ps_id)
        assert ps.status == "pending"

    assert metrics["started"] == 0
    assert metrics["expired"] == 0
