"""ユーザー設定 API（/api/user/preferences）の統合テスト。

実DB（migrations 適用済み）＋実 FastAPI アプリで、設定の取得・更新と
タイムゾーン（IANA 名）バリデーションを検証する。
"""
from __future__ import annotations

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
def prefs_client(tmp_path, monkeypatch) -> TestClient:
    """全マイグレーション適用済みDB＋FastAPIクライアント。"""
    _setup_test_env()

    db_path = tmp_path / "user_prefs.db"
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
    from shared.domain.auth.master_data import (
        DEFAULT_ADMIN_EMAIL,
        DEFAULT_ADMIN_PASSWORD,
    )

    resp = client.post(
        "/api/auth/login",
        json={"email": DEFAULT_ADMIN_EMAIL, "password": DEFAULT_ADMIN_PASSWORD, "scope": ["gui:view"]},
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.mark.integration
def test_preferences_require_authentication(prefs_client: TestClient) -> None:
    assert prefs_client.get("/api/user/preferences").status_code == 401


@pytest.mark.integration
def test_defaults_returned_when_unset(prefs_client: TestClient) -> None:
    headers = _admin_headers(prefs_client)
    resp = prefs_client.get("/api/user/preferences", headers=headers)
    assert resp.status_code == 200, resp.text
    prefs = resp.json()["preferences"]
    # timezone は既定値を持たず未設定時は含まれない（ブラウザ検出に委ねる）
    assert prefs["slideshow_interval"] == 5
    assert "timezone" not in prefs


@pytest.mark.integration
def test_set_valid_timezone_persists(prefs_client: TestClient) -> None:
    headers = _admin_headers(prefs_client)
    resp = prefs_client.put(
        "/api/user/preferences", headers=headers, json={"timezone": "Asia/Tokyo"}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "timezone" in body["updated"]
    assert body["preferences"]["timezone"] == "Asia/Tokyo"

    # 再取得しても保持されている
    again = prefs_client.get("/api/user/preferences", headers=headers).json()
    assert again["preferences"]["timezone"] == "Asia/Tokyo"


@pytest.mark.integration
def test_empty_timezone_allowed_as_reset(prefs_client: TestClient) -> None:
    """空文字は「自動（ブラウザ）」を意味し、明示的に許可される。"""
    headers = _admin_headers(prefs_client)
    resp = prefs_client.put(
        "/api/user/preferences", headers=headers, json={"timezone": ""}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["preferences"]["timezone"] == ""


@pytest.mark.integration
def test_invalid_timezone_rejected(prefs_client: TestClient) -> None:
    headers = _admin_headers(prefs_client)
    resp = prefs_client.put(
        "/api/user/preferences",
        headers=headers,
        json={"timezone": "Not/AZone"},
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"]["key"] == "timezone"
