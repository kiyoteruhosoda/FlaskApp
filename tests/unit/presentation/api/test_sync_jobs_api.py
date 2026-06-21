"""`/api/sync/jobs` 同期ジョブ履歴 API の単体テスト。"""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta

import pytest

pytestmark = pytest.mark.integration

from core.db import db
from core.models.job_sync import JobSync
from presentation.web.api.routes_sync_jobs import categorize_target


def _add_job(target, status, *, started_offset_min=0, stats=None, task_name=""):
    job = JobSync(
        target=target,
        task_name=task_name or target,
        status=status,
        started_at=datetime.now(timezone.utc) - timedelta(minutes=started_offset_min),
        stats_json=json.dumps(stats or {}),
    )
    db.session.add(job)
    db.session.commit()
    return job


def test_categorize_target():
    assert categorize_target("local_import_task") == "local_import"
    assert categorize_target("picker_import_item") == "picker_import"
    assert categorize_target("media_playback_transcode") == "transcode"
    assert categorize_target("thumbs_generate") == "thumbnail"
    assert categorize_target("google_oauth_refresh") == "google_photos"
    assert categorize_target("something_else") == "other"


@pytest.mark.usefixtures("app_context")
def test_jobs_list_returns_history(app_context):
    app = app_context
    _add_job("local_import_task", "success", started_offset_min=5,
             stats={"total": 10, "success": 9, "failed": 1})
    _add_job("picker_import_item", "failed", started_offset_min=1)

    client = app.test_client()
    resp = client.get("/api/sync/jobs")
    assert resp.status_code == 200
    body = resp.get_json()

    assert body["pagination"]["totalCount"] == 2
    assert len(body["jobs"]) == 2
    # 新しい順(picker が後で開始 → 先頭)
    assert body["jobs"][0]["target"] == "picker_import_item"
    assert body["jobs"][0]["targetCategory"] == "picker_import"
    assert body["jobs"][0]["retryable"] is True

    local_job = body["jobs"][1]
    assert local_job["targetCategory"] == "local_import"
    assert local_job["statsSummary"] == {"total": 10, "success": 9, "failed": 1}
    assert "server_time" in body


@pytest.mark.usefixtures("app_context")
def test_jobs_list_filters_by_status(app_context):
    app = app_context
    _add_job("local_import_task", "success")
    _add_job("local_import_task", "failed")

    client = app.test_client()
    resp = client.get("/api/sync/jobs?status=failed")
    body = resp.get_json()
    assert all(j["status"] == "failed" for j in body["jobs"])
    assert len(body["jobs"]) == 1


@pytest.mark.usefixtures("app_context")
def test_jobs_list_filters_by_target_category(app_context):
    app = app_context
    _add_job("local_import_task", "success")
    _add_job("thumbs_generate", "success")
    _add_job("picker_import_item", "success")

    client = app.test_client()
    resp = client.get("/api/sync/jobs?target=thumbnail")
    body = resp.get_json()
    assert len(body["jobs"]) == 1
    assert body["jobs"][0]["targetCategory"] == "thumbnail"


@pytest.mark.usefixtures("app_context")
def test_jobs_list_pagination(app_context):
    app = app_context
    for i in range(5):
        _add_job("local_import_task", "success", started_offset_min=i)

    client = app.test_client()
    resp = client.get("/api/sync/jobs?page=1&pageSize=2")
    body = resp.get_json()
    assert body["pagination"]["totalCount"] == 5
    assert body["pagination"]["totalPages"] == 3
    assert body["pagination"]["hasNext"] is True
    assert body["pagination"]["hasPrev"] is False
    assert len(body["jobs"]) == 2


@pytest.mark.usefixtures("app_context")
def test_job_detail_returns_full_stats(app_context):
    app = app_context
    job = _add_job("local_import_task", "success",
                   stats={"total": 3, "success": 3, "details": [1, 2, 3]})

    client = app.test_client()
    resp = client.get(f"/api/sync/jobs/{job.id}")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["job"]["id"] == job.id
    assert body["job"]["stats"]["details"] == [1, 2, 3]


@pytest.mark.usefixtures("app_context")
def test_job_detail_404(app_context):
    app = app_context
    client = app.test_client()
    resp = client.get("/api/sync/jobs/999999")
    assert resp.status_code == 404
