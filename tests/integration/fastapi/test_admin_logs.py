"""DBログ閲覧 API（GET /api/admin/logs）の統合テスト。

実DB（migrations 適用済み）＋実 FastAPI アプリで、``log`` / ``worker_log``
テーブルの内容が時間範囲・ログレベル等のフィルタ付きで取得できることを検証する。
"""
from __future__ import annotations

from datetime import datetime

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from tests.integration.test_migration_model_consistency import (
    ROOT,
    _setup_test_env,
)

ALEMBIC_INI = ROOT / "migrations" / "alembic.ini"


@pytest.fixture()
def logs_client(tmp_path, monkeypatch) -> TestClient:
    """全マイグレーション適用済みDB＋ログのテストデータ＋FastAPIクライアント。"""
    _setup_test_env()

    db_path = tmp_path / "admin_logs.db"
    url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URI", url)

    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")

    from presentation.fastapi.app import create_app
    from shared.kernel.database.session import get_db
    from shared.kernel.database.db import db as legacy_db

    engine = sa.create_engine(url, connect_args={"check_same_thread": False})
    session_factory = sessionmaker(
        bind=engine, autocommit=False, autoflush=False, expire_on_commit=False
    )
    legacy_db.init_app_engine(engine)

    # テストデータ投入（時刻は固定値。DB保存形式は naive UTC）
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO log (level, event, message, trace, path, request_id, created_at) "
                "VALUES (:level, :event, :message, :trace, :path, :request_id, :created_at)"
            ),
            [
                {
                    "level": "INFO",
                    "event": "request.completed",
                    "message": "GET /api/media ok",
                    "trace": None,
                    "path": "/api/media",
                    "request_id": "req-aaa",
                    "created_at": datetime(2026, 7, 1, 10, 0, 0),
                },
                {
                    "level": "ERROR",
                    "event": "request.failed",
                    "message": "boom: unexpected failure",
                    "trace": "Traceback (most recent call last): ...",
                    "path": "/api/albums",
                    "request_id": "req-bbb",
                    "created_at": datetime(2026, 7, 2, 12, 0, 0),
                },
                {
                    "level": "WARNING",
                    "event": "auth.denied",
                    "message": "permission denied",
                    "trace": None,
                    "path": "/api/admin/users",
                    "request_id": "req-ccc",
                    "created_at": datetime(2026, 7, 3, 9, 30, 0),
                },
            ],
        )
        conn.execute(
            sa.text(
                "INSERT INTO worker_log "
                "(created_at, level, event, task_name, task_uuid, message) "
                "VALUES (:created_at, :level, :event, :task_name, :task_uuid, :message)"
            ),
            [
                {
                    "created_at": datetime(2026, 7, 2, 3, 0, 0),
                    "level": "ERROR",
                    "event": "task.failed",
                    "task_name": "transcode.video",
                    "task_uuid": "task-123",
                    "message": "ffmpeg exited with 1",
                },
            ],
        )

    def _override_get_db():
        db = session_factory()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield TestClient(app, raise_server_exceptions=True)
    finally:
        app.dependency_overrides.pop(get_db, None)
        legacy_db.session.remove()
        engine.dispose()


def _admin_headers(client: TestClient) -> dict[str, str]:
    from shared.domain.auth.master_data import DEFAULT_ADMIN_EMAIL

    resp = client.post(
        "/api/auth/login",
        json={"email": DEFAULT_ADMIN_EMAIL, "password": "admin", "scope": ["gui:view"]},
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.mark.integration
def test_logs_require_authentication(logs_client: TestClient) -> None:
    assert logs_client.get("/api/admin/logs").status_code == 401


@pytest.mark.integration
def test_logs_listed_newest_first_with_pagination(logs_client: TestClient) -> None:
    headers = _admin_headers(logs_client)
    resp = logs_client.get("/api/admin/logs", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["pagination"]["totalCount"] == 3
    events = [log["event"] for log in body["logs"]]
    assert events == ["auth.denied", "request.failed", "request.completed"]
    assert body["logs"][0]["source"] == "app"
    assert set(body["availableLevels"]) == {"INFO", "ERROR", "WARNING"}


@pytest.mark.integration
def test_logs_filter_by_level(logs_client: TestClient) -> None:
    headers = _admin_headers(logs_client)
    resp = logs_client.get(
        "/api/admin/logs", headers=headers, params={"level": "error,warning"}
    )
    assert resp.status_code == 200, resp.text
    levels = {log["level"] for log in resp.json()["logs"]}
    assert levels == {"ERROR", "WARNING"}


@pytest.mark.integration
def test_logs_filter_by_time_range(logs_client: TestClient) -> None:
    headers = _admin_headers(logs_client)
    resp = logs_client.get(
        "/api/admin/logs",
        headers=headers,
        params={"since": "2026-07-02T00:00:00Z", "until": "2026-07-02T23:59:59Z"},
    )
    assert resp.status_code == 200, resp.text
    logs = resp.json()["logs"]
    assert [log["event"] for log in logs] == ["request.failed"]


@pytest.mark.integration
def test_logs_filter_by_message_and_trace_id(logs_client: TestClient) -> None:
    headers = _admin_headers(logs_client)

    resp = logs_client.get("/api/admin/logs", headers=headers, params={"q": "boom"})
    assert [log["requestId"] for log in resp.json()["logs"]] == ["req-bbb"]

    resp = logs_client.get(
        "/api/admin/logs", headers=headers, params={"traceId": "req-ccc"}
    )
    assert [log["event"] for log in resp.json()["logs"]] == ["auth.denied"]


@pytest.mark.integration
def test_worker_logs_source_and_task_uuid_filter(logs_client: TestClient) -> None:
    headers = _admin_headers(logs_client)
    resp = logs_client.get(
        "/api/admin/logs",
        headers=headers,
        params={"source": "worker", "traceId": "task-123"},
    )
    assert resp.status_code == 200, resp.text
    logs = resp.json()["logs"]
    assert len(logs) == 1
    assert logs[0]["source"] == "worker"
    assert logs[0]["taskName"] == "transcode.video"


@pytest.mark.integration
def test_log_detail_returns_full_message_and_trace(logs_client: TestClient) -> None:
    headers = _admin_headers(logs_client)
    listed = logs_client.get(
        "/api/admin/logs", headers=headers, params={"traceId": "req-bbb"}
    ).json()["logs"]
    log_id = listed[0]["id"]
    assert listed[0]["hasTrace"] is True

    resp = logs_client.get(f"/api/admin/logs/app/{log_id}", headers=headers)
    assert resp.status_code == 200, resp.text
    detail = resp.json()["log"]
    assert detail["trace"].startswith("Traceback")
    assert detail["message"] == "boom: unexpected failure"


@pytest.mark.integration
def test_logs_invalid_source_rejected(logs_client: TestClient) -> None:
    headers = _admin_headers(logs_client)
    resp = logs_client.get(
        "/api/admin/logs", headers=headers, params={"source": "nope"}
    )
    assert resp.status_code == 400
