"""ピッカーセッション API（/api/picker/session/*）の統合テスト。

FastAPI 移行時に ``PickerSessionService`` に存在しないメソッド
（``serialize_session_detail`` 等）を呼んで 500 になっていた退行の再発防止。
実DB（migrations 適用済み）＋実 FastAPI アプリで、セッション詳細・選択一覧・
ログ・コールバックの各エンドポイントを検証する。
"""
from __future__ import annotations

import json
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

SESSION_UUID = "021ab0b3-7779-46b9-90b1-80cad124a622"
SESSION_ID = f"picker_sessions/{SESSION_UUID}"


@pytest.fixture()
def picker_client(tmp_path, monkeypatch) -> TestClient:
    """全マイグレーション適用済みDB＋ピッカーセッションのテストデータ＋クライアント。"""
    _setup_test_env()

    db_path = tmp_path / "picker_session.db"
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

    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO picker_session "
                "(id, account_id, session_id, status, selected_count, trigger, "
                " created_at, updated_at) "
                "VALUES (1, NULL, :session_id, 'processing', NULL, 'user', "
                "        :created_at, :created_at)"
            ),
            {"session_id": SESSION_ID, "created_at": datetime(2026, 7, 14, 10, 0, 0)},
        )
        conn.execute(
            sa.text(
                "INSERT INTO picker_selection "
                "(session_id, google_media_id, status, attempts, created_at, updated_at) "
                "VALUES (1, :gid, :status, 0, :ts, :ts)"
            ),
            [
                {"gid": "media-1", "status": "imported", "ts": datetime(2026, 7, 14, 10, 5, 0)},
                {"gid": "media-2", "status": "dup", "ts": datetime(2026, 7, 14, 10, 6, 0)},
            ],
        )
        conn.execute(
            sa.text(
                "INSERT INTO worker_log (created_at, level, event, message) "
                "VALUES (:created_at, 'INFO', 'import.picker.item', :message)"
            ),
            {
                "created_at": datetime(2026, 7, 14, 10, 7, 0),
                "message": json.dumps(
                    {"message": "imported media-1", "session_id": SESSION_ID}
                ),
            },
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


def _auth_headers(client: TestClient) -> dict[str, str]:
    from shared.domain.auth.master_data import DEFAULT_ADMIN_EMAIL

    resp = client.post(
        "/api/auth/login",
        json={"email": DEFAULT_ADMIN_EMAIL, "password": "admin", "scope": ["gui:view"]},
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.mark.integration
def test_session_status_requires_authentication(picker_client: TestClient) -> None:
    assert picker_client.get(f"/api/picker/session/{SESSION_UUID}").status_code == 401


@pytest.mark.integration
def test_session_status_by_session_id(picker_client: TestClient) -> None:
    """GET /api/picker/session/{session_id} がステータスペイロードを直接返す。"""
    headers = _auth_headers(picker_client)
    resp = picker_client.get(f"/api/picker/session/{SESSION_UUID}", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["sessionId"] == SESSION_ID
    assert body["isLocalImport"] is True
    assert body["counts"] == {"imported": 1, "dup": 1}
    assert body["selectedCount"] == 2
    # 全件確定済み（pending なし・imported あり）なので imported へ遷移する
    assert body["status"] == "imported"


@pytest.mark.integration
def test_session_status_unknown_session_returns_404(picker_client: TestClient) -> None:
    headers = _auth_headers(picker_client)
    resp = picker_client.get("/api/picker/session/no-such-session", headers=headers)
    assert resp.status_code == 404
    assert resp.json()["detail"]["error"] == "not_found"


@pytest.mark.integration
def test_session_summary_by_numeric_id(picker_client: TestClient) -> None:
    """GET /api/picker/session/{数値ID} は件数とジョブ概要を返す（Flask 版と同じ契約）。"""
    headers = _auth_headers(picker_client)
    resp = picker_client.get("/api/picker/session/1", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["countsByStatus"] == {"imported": 1, "dup": 1}
    assert body["jobSync"] is None


@pytest.mark.integration
def test_session_selections(picker_client: TestClient) -> None:
    """選択一覧は ``selections`` キーで返る（フロントエンドの期待する形）。"""
    headers = _auth_headers(picker_client)
    resp = picker_client.get(
        f"/api/picker/session/{SESSION_UUID}/selections",
        params={"pageSize": 200},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert {sel["googleMediaId"] for sel in body["selections"]} == {"media-1", "media-2"}
    assert body["counts"] == {"imported": 1, "dup": 1}

    filtered = picker_client.get(
        f"/api/picker/session/{SESSION_UUID}/selections",
        params={"pageSize": 200, "status": ["imported"]},
        headers=headers,
    )
    assert filtered.status_code == 200, filtered.text
    assert [sel["googleMediaId"] for sel in filtered.json()["selections"]] == ["media-1"]


@pytest.mark.integration
def test_session_logs(picker_client: TestClient) -> None:
    """取り込みログが session_id で照合されて返る。"""
    headers = _auth_headers(picker_client)
    resp = picker_client.get(
        f"/api/picker/session/{SESSION_UUID}/logs",
        params={"limit": 100},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["hasNext"] is False
    assert len(body["logs"]) == 1
    entry = body["logs"][0]
    assert entry["event"] == "import.picker.item"
    assert entry["message"] == "imported media-1"


@pytest.mark.integration
def test_session_callback_marks_ready(picker_client: TestClient) -> None:
    headers = _auth_headers(picker_client)
    resp = picker_client.post(
        f"/api/picker/session/{SESSION_UUID}/callback",
        json={"mediaItemIds": ["media-3", "media-4"]},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"result": "ok", "count": 2}

    status_resp = picker_client.get(f"/api/picker/session/{SESSION_UUID}", headers=headers)
    assert status_resp.status_code == 200
    assert status_resp.json()["mediaItemsSet"] is True
