from datetime import datetime, timedelta, timezone

import pytest

from core.db import db
from core.models import CeleryTaskRecord, CeleryTaskStatus

from cli.src.celery.inspect_tasks import (
    PENDING_STATUSES,
    format_summary,
    format_tasks_table,
    get_task_overview,
    parse_status_filters,
)


class TestStatusParsing:
    def test_parse_status_filters_accepts_values(self):
        statuses = parse_status_filters(["queued", "SUCCESS"])
        assert statuses == [CeleryTaskStatus.QUEUED, CeleryTaskStatus.SUCCESS]

    def test_parse_status_filters_includes_pending_shortcut(self):
        statuses = parse_status_filters(["success"], include_pending=True)
        for status in PENDING_STATUSES:
            assert status in statuses
        assert CeleryTaskStatus.SUCCESS in statuses

    def test_parse_status_filters_rejects_unknown_value(self):
        with pytest.raises(ValueError):
            parse_status_filters(["not-a-status"])


class TestTaskOverview:
    def _create_task(
        self,
        *,
        name: str,
        status: CeleryTaskStatus,
        created_at: datetime,
        object_type: str | None = None,
        object_id: str | None = None,
        celery_id: str | None = None,
        scheduled_for: datetime | None = None,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
        error_message: str | None = None,
    ) -> CeleryTaskRecord:
        record = CeleryTaskRecord(
            task_name=name,
            status=status,
            object_type=object_type,
            object_id=object_id,
            celery_task_id=celery_id,
            scheduled_for=scheduled_for,
            started_at=started_at,
            finished_at=finished_at,
            error_message=error_message,
        )
        record.created_at = created_at
        record.updated_at = created_at
        return record

    def test_get_task_overview_filters_and_serializes(self, app_context):
        now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        with app_context.app_context():
            queued = self._create_task(
                name="task.alpha",
                status=CeleryTaskStatus.QUEUED,
                created_at=now,
                object_type="media",
                object_id="42",
                celery_id="celery-1",
                scheduled_for=now + timedelta(minutes=5),
                started_at=now + timedelta(minutes=1),
            )
            queued.set_payload({"foo": "bar"})

            success = self._create_task(
                name="task.beta",
                status=CeleryTaskStatus.SUCCESS,
                created_at=now - timedelta(minutes=1),
                celery_id="celery-2",
            )
            success.set_result({"ok": True})

            failed = self._create_task(
                name="task.gamma",
                status=CeleryTaskStatus.FAILED,
                created_at=now - timedelta(minutes=2),
                error_message="boom",
            )

            db.session.add_all([queued, success, failed])
            db.session.commit()

            summary, tasks = get_task_overview(
                [CeleryTaskStatus.QUEUED, CeleryTaskStatus.SUCCESS],
                include_payload=True,
                include_result=True,
            )

            assert [task["task_name"] for task in tasks] == ["task.alpha", "task.beta"]
            assert tasks[0]["payload"] == {"foo": "bar"}
            assert tasks[1]["result"] == {"ok": True}
            assert summary["queued"] == 1
            assert summary["failed"] == 1
            assert summary["total"] == 3

            limited_summary, limited_tasks = get_task_overview(limit=1)
            assert len(limited_tasks) == 1
            assert limited_tasks[0]["task_name"] == "task.alpha"
            assert "payload" not in limited_tasks[0]
            assert limited_summary["total"] == 3

    def test_format_tasks_table_output(self):
        task = {
            "id": 1,
            "task_name": "task.alpha",
            "status": "queued",
            "object_type": "media",
            "object_id": "42",
            "celery_task_id": "celery-1",
            "created_at": "2024-01-01 12:00:00Z",
            "scheduled_for": "2024-01-01 12:05:00Z",
            "started_at": "2024-01-01 12:01:00Z",
            "finished_at": None,
            "error_message": "this is a very long error message that should be truncated" + "!" * 80,
            "payload": {"foo": "bar"},
            "result": {"ok": True},
        }

        table = format_tasks_table([task], include_payload=True, include_result=True)
        lines = table.splitlines()
        assert lines[0].startswith("ID")
        assert "task.alpha" in table
        assert "media:42" in table
        assert "foo" in table
        assert "…" in table  # truncated error

        empty = format_tasks_table([], include_payload=False, include_result=False)
        assert "No Celery task records" in empty

    def test_format_summary_lists_all_statuses(self):
        summary = {"queued": 2, "success": 5, "total": 10}
        text = format_summary(summary)
        for status in CeleryTaskStatus:
            assert status.value in text
        assert text.strip().splitlines()[-1].endswith("total: 10")
