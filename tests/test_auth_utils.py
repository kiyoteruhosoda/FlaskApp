import json
import logging

import pytest

from webapp.auth import utils as auth_utils


class DummyResponse:
    def __init__(self):
        self.status_code = 200
        self.headers = {
            "Authorization": "Bearer response-secret",
            "Content-Type": "application/json",
        }
        self._json = {
            "access_token": "response-access-token",
            "nested": {"refresh_token": "nested-refresh"},
            "list": [{"token": "list-token"}],
        }
        self.text = json.dumps(self._json)

    def json(self):
        return self._json


@pytest.mark.usefixtures("app_context")
def test_log_requests_and_send_masks_sensitive_values(caplog, monkeypatch):
    """リクエスト・レスポンスログで機密値がマスクされること"""

    def dummy_post(*args, **kwargs):
        return DummyResponse()

    monkeypatch.setattr(auth_utils.requests, "post", dummy_post)

    with caplog.at_level(logging.INFO):
        auth_utils.log_requests_and_send(
            "post",
            "https://example.com/token",
            headers={
                "Authorization": "Bearer secret",
                "X-Api-Key": "api-key",
                "Content-Type": "application/json",
            },
            json_data={
                "access_token": "request-access-token",
                "nested": {"token": "nested-token"},
                "list": ["plain"],
            },
        )

    request_record = next(
        record for record in caplog.records if getattr(record, "event", "") == "requests.send"
    )
    request_payload = json.loads(request_record.message)
    assert request_payload["headers"]["Authorization"] == "***"
    assert request_payload["headers"]["X-Api-Key"] == "***"
    assert request_payload["headers"]["Content-Type"] == "application/json"
    assert request_payload["json"]["access_token"] == "***"
    assert request_payload["json"]["nested"]["token"] == "***"
    assert request_payload["json"]["list"] == ["plain"]

    response_record = next(
        record for record in caplog.records if getattr(record, "event", "") == "requests.recv"
    )
    response_payload = json.loads(response_record.message)
    assert response_payload["headers"]["Authorization"] == "***"
    assert response_payload["headers"]["Content-Type"] == "application/json"
    assert response_payload["body"]["access_token"] == "***"
    assert response_payload["body"]["nested"]["refresh_token"] == "***"
    assert response_payload["body"]["list"][0]["token"] == "***"
