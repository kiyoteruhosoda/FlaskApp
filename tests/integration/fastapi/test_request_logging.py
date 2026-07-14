"""リクエストロギングミドルウェアと DB ログ構成の統合テスト。

T11 の FastAPI 移行で DB ログハンドラの配線が失われ、API のエラーが
System Logs（``log`` テーブル）へ一切記録されない状態になっていた。
本テストはその再発を防ぐ:

- ``RequestLoggingMiddleware`` が ``/api`` の入出力と未処理例外を
  requestId 付きで記録すること。
- ``configure_db_logging`` がルートロガーへ ``DBLogHandler`` を装着すること
  （テスト時・インメモリ SQLite 時はスキップすること）。
"""
from __future__ import annotations

import json
import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from presentation.fastapi.middleware.request_logging import RequestLoggingMiddleware

MIDDLEWARE_LOGGER = "presentation.fastapi.middleware.request_logging"


@pytest.fixture(autouse=True)
def _enable_middleware_logger():
    """他テストの logging.config.fileConfig で無効化されていても有効に戻す。"""
    logging.getLogger(MIDDLEWARE_LOGGER).disabled = False
    yield


@pytest.fixture()
def client() -> TestClient:
    app = FastAPI()
    app.add_middleware(RequestLoggingMiddleware)

    @app.get("/api/ok")
    async def _ok():
        return {"result": "ok"}

    @app.get("/api/boom")
    async def _boom():
        raise RuntimeError("boom")

    @app.get("/spa-page")
    async def _spa():
        return {"page": True}

    return TestClient(app, raise_server_exceptions=False)


def _records_by_event(caplog, event: str):
    return [r for r in caplog.records if getattr(r, "event", None) == event]


class TestRequestLoggingMiddleware:
    def test_api_input_and_output_logged_with_request_id(self, client, caplog) -> None:
        with caplog.at_level(logging.INFO, logger=MIDDLEWARE_LOGGER):
            resp = client.get("/api/ok", params={"page": "1", "token": "secret-value"})

        assert resp.status_code == 200
        request_id = resp.headers["X-Request-ID"]

        inputs = _records_by_event(caplog, "api.input")
        outputs = _records_by_event(caplog, "api.output")
        assert len(inputs) == 1
        assert len(outputs) == 1
        assert inputs[0].request_id == request_id
        assert outputs[0].request_id == request_id

        input_payload = json.loads(inputs[0].getMessage())
        assert input_payload["method"] == "GET"
        assert input_payload["path"] == "/api/ok"
        # 機密クエリはマスクされる
        assert input_payload["query"]["token"] == "***"
        assert input_payload["query"]["page"] == "1"

        output_payload = json.loads(outputs[0].getMessage())
        assert output_payload["status"] == 200

    def test_unhandled_exception_logged_with_traceback(self, client, caplog) -> None:
        with caplog.at_level(logging.INFO, logger=MIDDLEWARE_LOGGER):
            resp = client.get("/api/boom")

        assert resp.status_code == 500
        errors = _records_by_event(caplog, "api.error")
        assert len(errors) == 1
        record = errors[0]
        assert record.levelno == logging.ERROR
        assert record.exc_info is not None  # traceback が DB の trace 列へ入る
        payload = json.loads(record.getMessage())
        assert payload["path"] == "/api/boom"
        assert "RuntimeError" in payload["error"]

    def test_non_api_paths_not_logged_but_get_request_id(self, client, caplog) -> None:
        with caplog.at_level(logging.INFO, logger=MIDDLEWARE_LOGGER):
            resp = client.get("/spa-page")

        assert resp.status_code == 200
        assert resp.headers.get("X-Request-ID")
        assert not _records_by_event(caplog, "api.input")
        assert not _records_by_event(caplog, "api.output")

    def test_http_error_status_logged_as_warning(self, client, caplog) -> None:
        with caplog.at_level(logging.INFO, logger=MIDDLEWARE_LOGGER):
            resp = client.get("/api/not-found")

        assert resp.status_code == 404
        outputs = _records_by_event(caplog, "api.output")
        assert len(outputs) == 1
        assert outputs[0].levelno == logging.WARNING


class TestUnhandledExceptionResponse:
    def test_create_app_returns_generic_500_json(self, caplog) -> None:
        """本物の create_app でも未処理例外がログされ 500 JSON が返ること。"""
        from fastapi.routing import APIRoute

        from presentation.fastapi.app import create_app

        app = create_app()

        async def _boom():
            raise RuntimeError("boom from create_app")

        # SPA catch-all（/{path:path}）より先に評価されるよう先頭へ挿入する
        app.router.routes.insert(
            0, APIRoute("/api/_test/boom", _boom, methods=["GET"])
        )

        test_client = TestClient(app, raise_server_exceptions=False)
        with caplog.at_level(logging.INFO, logger=MIDDLEWARE_LOGGER):
            resp = test_client.get("/api/_test/boom")

        assert resp.status_code == 500
        assert resp.json() == {
            "error": "internal_server_error",
            "message": "An unexpected error occurred.",
        }
        errors = _records_by_event(caplog, "api.error")
        assert len(errors) == 1


class TestConfigureDbLogging:
    def _cleanup_root_handlers(self) -> None:
        from shared.kernel.logging.db_log_handler import DBLogHandler

        root = logging.getLogger()
        for handler in list(root.handlers):
            if isinstance(handler, DBLogHandler):
                root.removeHandler(handler)

    def test_skipped_when_testing(self) -> None:
        from presentation.fastapi.logging_setup import configure_db_logging
        from shared.kernel.logging.db_log_handler import DBLogHandler

        # conftest が TESTING=true を設定している
        configure_db_logging()
        root = logging.getLogger()
        assert not any(isinstance(h, DBLogHandler) for h in root.handlers)

    def test_attaches_handler_to_root_logger(self, monkeypatch, tmp_path) -> None:
        from presentation.fastapi.logging_setup import configure_db_logging
        from shared.kernel.logging.db_log_handler import DBLogHandler
        from shared.kernel.logging.request_context import RequestIdLogFilter

        monkeypatch.setenv("TESTING", "false")
        monkeypatch.setenv("DATABASE_URI", f"sqlite:///{tmp_path}/logs.db")
        monkeypatch.delenv("SQLALCHEMY_DATABASE_URI", raising=False)

        try:
            configure_db_logging()
            root = logging.getLogger()
            db_handlers = [h for h in root.handlers if isinstance(h, DBLogHandler)]
            assert len(db_handlers) == 1
            assert any(
                isinstance(f, RequestIdLogFilter) for f in db_handlers[0].filters
            )
            assert root.getEffectiveLevel() <= logging.INFO

            # 二重呼び出しでもハンドラは増えない
            configure_db_logging()
            db_handlers = [h for h in root.handlers if isinstance(h, DBLogHandler)]
            assert len(db_handlers) == 1
        finally:
            self._cleanup_root_handlers()

    def test_skipped_for_in_memory_sqlite(self, monkeypatch) -> None:
        from presentation.fastapi.logging_setup import configure_db_logging
        from shared.kernel.logging.db_log_handler import DBLogHandler

        monkeypatch.setenv("TESTING", "false")
        monkeypatch.setenv("DATABASE_URI", "sqlite:///:memory:")
        monkeypatch.delenv("SQLALCHEMY_DATABASE_URI", raising=False)

        try:
            configure_db_logging()
            root = logging.getLogger()
            assert not any(isinstance(h, DBLogHandler) for h in root.handlers)
        finally:
            self._cleanup_root_handlers()
