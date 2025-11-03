"""Googleインポートログ抽出ロジックのテスト"""

import json
from datetime import datetime, timezone

import pytest

from core.models.google_account import GoogleAccount
from core.models.picker_session import PickerSession
from core.models.worker_log import WorkerLog
from webapp.api.picker_session import _collect_local_import_logs
from webapp.extensions import db


@pytest.mark.usefixtures("app_context")
def test_collect_logs_includes_google_import_entries(app_context):
    """Googleインポート用のログも抽出対象になることを検証"""

    with app_context.app_context():
        account = GoogleAccount(email="google@example.com", status="active", scopes="photos")
        db.session.add(account)
        db.session.commit()

        session = PickerSession(
            account_id=account.id,
            session_id="picker_sessions/google_session_1",
            status="importing",
        )
        db.session.add(session)
        db.session.commit()

        nested_payload = {
            "message": "Import session created",
            "_extra": {
                "session": {"session_id": session.session_id, "source": "google"},
                "import_source": "google",
                "account_id": account.id,
            },
        }
        db.session.add(
            WorkerLog(
                level="INFO",
                event="import.session.created",
                message=json.dumps(nested_payload, ensure_ascii=False),
                extra_json=nested_payload["_extra"],
                created_at=datetime.now(timezone.utc),
            )
        )

        alias_payload = {
            "message": "Fetching media from Google",
            "_extra": {
                "session_id": f"google-{account.id}",
                "import_source": "google",
                "account_id": account.id,
            },
        }
        db.session.add(
            WorkerLog(
                level="INFO",
                event="import.stage.fetch.start",
                message=json.dumps(alias_payload, ensure_ascii=False),
                extra_json=alias_payload["_extra"],
                created_at=datetime.now(timezone.utc),
            )
        )

        account_scoped_payload = {
            "message": "Account scoped log",
            "_extra": {
                "import_source": "google",
                "account_id": account.id,
            },
        }
        db.session.add(
            WorkerLog(
                level="INFO",
                event="import.stage.normalize.start",
                message=json.dumps(account_scoped_payload, ensure_ascii=False),
                extra_json=account_scoped_payload["_extra"],
                created_at=datetime.now(timezone.utc),
            )
        )

        db.session.commit()

        logs = _collect_local_import_logs(session, limit=None)

        assert len(logs) == 3
        events = {entry["event"] for entry in logs}
        assert "import.session.created" in events
        assert "import.stage.fetch.start" in events
        assert "import.stage.normalize.start" in events
