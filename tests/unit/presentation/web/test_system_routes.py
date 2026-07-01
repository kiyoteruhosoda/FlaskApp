"""`presentation/web/routes/system_routes.py` の言語切替ルートのテスト。

ログイン前のページでも ``?lang=`` クエリパラメータで言語を切り替えられ、
その選択が Cookie として次回以降のリクエストに引き継がれることを検証する。
"""

from __future__ import annotations

import pytest


@pytest.fixture
def client(app_context):
    return app_context.test_client()


def test_query_lang_param_sets_cookie(client):
    response = client.get("/?lang=ja")
    assert response.status_code == 200

    cookies = response.headers.getlist("Set-Cookie")
    assert any(cookie.startswith("lang=ja") for cookie in cookies)


def test_invalid_query_lang_param_does_not_set_cookie(client):
    response = client.get("/?lang=fr")
    assert response.status_code == 200

    cookies = response.headers.getlist("Set-Cookie")
    assert not any(cookie.startswith("lang=") for cookie in cookies)


def test_set_lang_route_redirects_and_sets_cookie(client):
    response = client.get("/lang/ja", follow_redirects=False)
    assert response.status_code in (302, 303)

    cookies = response.headers.getlist("Set-Cookie")
    assert any(cookie.startswith("lang=ja") for cookie in cookies)
