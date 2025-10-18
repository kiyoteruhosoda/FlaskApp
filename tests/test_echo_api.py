"""Echo APIのテスト。"""
from __future__ import annotations

import json

import pytest

from webapp import create_app


class TestEchoAPI:
    """Echo APIの挙動を検証するテストケース。"""

    @pytest.fixture
    def client(self):
        app = create_app()
        app.config["TESTING"] = True
        with app.test_client() as client:
            yield client

    def test_echo_returns_headers_and_json_payload(self, client):
        payload = {"message": "こんにちは", "value": 42}
        extra_headers = {"X-Debug": "1"}

        response = client.post("/api/echo", json=payload, headers=extra_headers)

        assert response.status_code == 200
        assert response.content_type == "application/json"

        response_body = response.get_json()
        assert response_body["json"] == payload
        assert json.loads(response_body["body"]) == payload
        assert response_body["headers"]["Content-Type"] == "application/json"
        assert response_body["headers"]["X-Debug"] == "1"

    def test_echo_accepts_non_json_payload(self, client):
        response = client.post(
            "/api/echo",
            data="plain text",
            content_type="text/plain",
        )

        assert response.status_code == 200
        response_body = response.get_json()
        assert response_body["json"] is None
        assert response_body["body"] == "plain text"
        assert response_body["headers"]["Content-Type"] == "text/plain"

    def test_echo_supports_json_array(self, client):
        payload = [1, 2, {"nested": True}]

        response = client.post("/api/echo", json=payload)

        assert response.status_code == 200
        response_body = response.get_json()
        assert response_body["json"] == payload
        assert json.loads(response_body["body"]) == payload

    def test_echo_does_not_allow_get_method(self, client):
        response = client.get("/api/echo")

        assert response.status_code == 405
