"""UI用証明書APIクライアントのテスト"""
from __future__ import annotations

from http import HTTPStatus
from typing import Any

import pytest
import requests

from features.certs.domain.usage import UsageType
from features.certs.presentation.ui.api_client import (
    CertsApiClient,
    CertsApiClientError,
)


class _DummyResponse:
    def __init__(self, *, status_code: int = 200, json_data: Any = None, text: str = "") -> None:
        self.status_code = status_code
        self._json_data = json_data
        self.text = text
        self.headers: dict[str, str] = {}

    def json(self) -> Any:
        if isinstance(self._json_data, Exception):
            raise self._json_data
        return self._json_data


def test_list_certificates_calls_external_api(monkeypatch, app_context):
    app = app_context
    captured: dict[str, Any] = {}

    def fake_send(method, url, **kwargs):
        captured["method"] = method
        captured["url"] = url
        captured["kwargs"] = kwargs
        return _DummyResponse(json_data={"certificates": []})

    monkeypatch.setattr(
        "features.certs.presentation.ui.api_client.log_requests_and_send",
        fake_send,
    )

    with app.test_request_context("/certs/"):
        client = CertsApiClient(app)
        client.list_certificates(UsageType.SERVER_SIGNING)

    assert captured["method"] == "get"
    assert captured["url"].endswith("/api/certs")
    params = captured["kwargs"].get("params")
    assert params == {"usage": UsageType.SERVER_SIGNING.value}
    headers = captured["kwargs"].get("headers")
    assert headers["Accept"] == "application/json"
    assert captured["kwargs"].get("timeout") == pytest.approx(10.0)


def test_timeout_zero_disables_request_limit(monkeypatch, app_context):
    app = app_context
    captured: dict[str, Any] = {}

    def fake_send(method, url, **kwargs):
        captured["timeout"] = kwargs.get("timeout")
        return _DummyResponse(json_data={"certificates": []})

    monkeypatch.setattr(
        "features.certs.presentation.ui.api_client.log_requests_and_send",
        fake_send,
    )

    with app.test_request_context("/certs/"):
        app.config["CERTS_API_TIMEOUT"] = 0
        client = CertsApiClient(app)
        client.list_certificates()

    assert captured["timeout"] is None


def test_dispatch_network_error(monkeypatch, app_context):
    app = app_context

    def fake_send(*args, **kwargs):
        raise requests.RequestException("boom")

    monkeypatch.setattr(
        "features.certs.presentation.ui.api_client.log_requests_and_send",
        fake_send,
    )

    with app.test_request_context("/certs/"):
        client = CertsApiClient(app)
        with pytest.raises(CertsApiClientError) as exc:
            client.list_certificates()

    assert exc.value.status_code == HTTPStatus.BAD_GATEWAY


def test_dispatch_error_response(monkeypatch, app_context):
    app = app_context

    def fake_send(*args, **kwargs):
        return _DummyResponse(status_code=HTTPStatus.BAD_REQUEST, json_data={"error": "ng"})

    monkeypatch.setattr(
        "features.certs.presentation.ui.api_client.log_requests_and_send",
        fake_send,
    )

    with app.test_request_context("/certs/"):
        client = CertsApiClient(app)
        with pytest.raises(CertsApiClientError) as exc:
            client.list_certificates()

    assert exc.value.status_code == HTTPStatus.BAD_REQUEST
    assert "ng" in str(exc.value)
