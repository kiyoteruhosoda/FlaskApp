import pytest
from flask import abort

from webapp import create_app


@pytest.fixture
def api_error_app():
    app = create_app()
    app.config.update(TESTING=True, PROPAGATE_EXCEPTIONS=False)

    @app.route("/api/test/not-found")
    def api_not_found():
        abort(404)

    @app.route("/api/test/server-error")
    def api_server_error():
        raise RuntimeError("boom")

    return app


def test_api_error_default_language(api_error_app):
    with api_error_app.test_client() as client:
        response = client.get("/api/test/not-found")
        assert response.status_code == 404
        body = response.get_json()
        assert body["error"] == "Not Found"
        assert response.headers.get("Content-Language", "").startswith("en")


def test_api_error_respects_accept_language(api_error_app):
    with api_error_app.test_client() as client:
        response = client.get(
            "/api/test/not-found",
            headers={"Accept-Language": "ja"},
        )
        assert response.status_code == 404
        body = response.get_json()
        assert body["error"] == "見つかりません"
        assert response.headers.get("Content-Language", "").startswith("ja")


def test_api_server_error_localized_message(api_error_app):
    with api_error_app.test_client() as client:
        response = client.get("/api/test/server-error")
        assert response.status_code == 500
        body = response.get_json()
        assert body["message"] == "Internal Server Error"
        assert response.headers.get("Content-Language", "").startswith("en")

    with api_error_app.test_client() as client:
        response = client.get(
            "/api/test/server-error",
            headers={"Accept-Language": "ja"},
        )
        assert response.status_code == 500
        body = response.get_json()
        assert body["message"] == "サーバー内部エラー"
        assert response.headers.get("Content-Language", "").startswith("ja")
