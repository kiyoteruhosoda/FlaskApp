import os

import pytest


@pytest.fixture
def app(tmp_path):
    os.environ["SECRET_KEY"] = "test"
    os.environ["DATABASE_URI"] = f"sqlite:///{tmp_path / 'test.db'}"
    os.environ.setdefault("JWT_SECRET_KEY", "test-jwt")
    os.environ.setdefault("ACCESS_TOKEN_ISSUER", "test")
    os.environ.setdefault("ACCESS_TOKEN_AUDIENCE", "test")
    os.environ.setdefault("MEDIA_DOWNLOAD_SIGNING_KEY", "test-key-32-bytes-padded-xxxxx")

    from presentation.fastapi.app import create_app

    return create_app()


@pytest.fixture
def client(app):
    from fastapi.testclient import TestClient

    return TestClient(app)


def test_health_live(client):
    resp = client.get("/health/live")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert "commit_hash" in data
    assert "branch" in data

