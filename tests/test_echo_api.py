"""Echo APIのテスト。"""
from __future__ import annotations

import json

import pytest

from webapp import create_app


def _parse_http_message(message: str) -> tuple[str, dict[str, str], str]:
    """HTTPメッセージ形式のテキストをパースするユーティリティ。"""

    if "\r\n\r\n" in message:
        header_section, body = message.split("\r\n\r\n", 1)
    else:
        header_section, body = message.rstrip("\r\n"), ""

    lines = header_section.split("\r\n")
    request_line = lines[0]
    headers: dict[str, str] = {}
    for header_line in lines[1:]:
        if not header_line:
            continue
        name, value = header_line.split(":", 1)
        headers[name.strip()] = value.strip()
    return request_line, headers, body


class TestEchoAPI:
    """Echo APIの挙動を検証するテストケース。"""

    @pytest.fixture
    def client(self):
        app = create_app()
        app.config["TESTING"] = True
        with app.test_client() as client:
            yield client

    def test_echo_returns_plain_text_http_message(self, client):
        payload = {"message": "こんにちは", "value": 42}
        extra_headers = {"X-Debug": "1"}

        response = client.post("/api/echo", json=payload, headers=extra_headers)

        assert response.status_code == 200
        assert response.content_type.startswith("text/plain")

        request_line, headers, body = _parse_http_message(response.get_data(as_text=True))
        assert request_line == "POST /api/echo HTTP/1.1"
        assert headers["Content-Type"] == "application/json"
        assert headers["X-Debug"] == "1"
        assert json.loads(body) == payload

    def test_echo_accepts_non_json_payload(self, client):
        response = client.post(
            "/api/echo",
            data="plain text",
            content_type="text/plain",
        )

        assert response.status_code == 200
        assert response.content_type.startswith("text/plain")

        request_line, headers, body = _parse_http_message(response.get_data(as_text=True))
        assert request_line == "POST /api/echo HTTP/1.1"
        assert headers["Content-Type"] == "text/plain"
        assert body == "plain text"

    def test_echo_supports_json_array(self, client):
        payload = [1, 2, {"nested": True}]

        response = client.post("/api/echo", json=payload)

        assert response.status_code == 200
        _, headers, body = _parse_http_message(response.get_data(as_text=True))
        assert headers["Content-Type"] == "application/json"
        assert json.loads(body) == payload

    def test_echo_accepts_head_method(self, client):
        response = client.head("/api/echo")

        assert response.status_code == 200
        assert response.data == b""

    @pytest.mark.parametrize(
        "method",
        ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    )
    def test_echo_accepts_multiple_http_methods(self, client, method):
        payload = {"method": method}

        response = client.open(
            "/api/echo",
            method=method,
            json=payload,
        )

        assert response.status_code == 200
        assert response.content_type.startswith("text/plain")

        request_line, _, body = _parse_http_message(response.get_data(as_text=True))
        assert request_line.startswith(f"{method} /api/echo")
        assert json.loads(body) == payload
