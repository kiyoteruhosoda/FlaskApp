"""Googleインポートログ抽出ロジックのテスト"""

import json
from datetime import datetime, timezone
from typing import Dict

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

        detailed_payload = {
            "message": "Download completed",
            "_extra": {
                "session_id": session.session_id,
                "chunk_index": 1,
                "item_index": 1,
                "bytes": 2048,
                "sha256": "deadbeef",
            },
        }
        db.session.add(
            WorkerLog(
                level="INFO",
                event="import.picker.item.download.success",
                message=json.dumps(detailed_payload, ensure_ascii=False),
                extra_json=detailed_payload["_extra"],
                created_at=datetime.now(timezone.utc),
            )
        )

        db.session.commit()

        logs = _collect_local_import_logs(session, limit=None)

        assert len(logs) == 4
        events = {entry["event"] for entry in logs}
        assert "import.session.created" in events
        assert "import.stage.fetch.start" in events
        assert "import.stage.normalize.start" in events
        assert "import.picker.item.download.success" in events

        download_entry = next(
            entry for entry in logs if entry["event"] == "import.picker.item.download.success"
        )
        assert download_entry["details"]["chunk_index"] == 1
        assert download_entry["details"]["item_index"] == 1
        assert download_entry["details"]["bytes"] == 2048
        assert download_entry["details"]["sha256"] == "deadbeef"


@pytest.mark.usefixtures("app_context")
def test_collect_logs_filters_by_file_task_id(app_context):
    with app_context.app_context():
        session = PickerSession(
            session_id="local_import_session",
            status="processing",
        )
        db.session.add(session)
        db.session.commit()

        base_payload = {
            "message": "Processing file",
            "_extra": {"session_id": session.session_id},
        }

        first_payload = dict(base_payload)
        first_payload["_extra"] = dict(base_payload["_extra"])
        first_payload["_extra"]["file"] = "alpha.jpg"
        db.session.add(
            WorkerLog(
                level="INFO",
                event="local_import.file.begin",
                message=json.dumps(first_payload, ensure_ascii=False),
                extra_json=first_payload["_extra"],
                file_task_id="alpha",
                created_at=datetime.now(timezone.utc),
            )
        )

        second_payload = dict(base_payload)
        second_payload["_extra"] = dict(base_payload["_extra"])
        second_payload["_extra"]["file"] = "beta.jpg"
        db.session.add(
            WorkerLog(
                level="INFO",
                event="local_import.file.begin",
                message=json.dumps(second_payload, ensure_ascii=False),
                extra_json=second_payload["_extra"],
                file_task_id="beta",
                created_at=datetime.now(timezone.utc),
            )
        )

        db.session.commit()

        index: Dict[str, int] = {}
        all_logs = _collect_local_import_logs(
            session,
            limit=None,
            file_task_id_index=index,
        )

        assert {entry["fileTaskId"] for entry in all_logs} == {"alpha", "beta"}
        assert set(index.keys()) == {"alpha", "beta"}

        alpha_logs = _collect_local_import_logs(
            session,
            limit=None,
            file_task_id="alpha",
        )

        assert len(alpha_logs) == 1
        assert alpha_logs[0]["fileTaskId"] == "alpha"
