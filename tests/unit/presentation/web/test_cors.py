"""`presentation/web/cors.py` の純粋ロジックの単体テスト。

許可オリジン判定とヘッダ付与は、認可境界に直結するため誤りが許されない。
アプリ生成・リクエストコンテキストに依存しない形で境界条件を検証する
（フック登録を伴う ``configure_cors`` は既存の統合テストで網羅済み）。
"""

import types

from werkzeug.datastructures import Headers

from presentation.web import cors
from presentation.web.cors import (
    DEFAULT_CORS_MAX_AGE,
    allowed_origins_from_settings,
    apply_base_headers,
    is_origin_allowed,
)


class _FakeResponse:
    def __init__(self):
        self.headers = Headers()


class TestIsOriginAllowed:
    def test_empty_origin_is_rejected(self):
        assert is_origin_allowed("", ("https://a",)) is False
        assert is_origin_allowed(None, ("https://a",)) is False

    def test_empty_allowlist_rejects(self):
        assert is_origin_allowed("https://a", ()) is False

    def test_exact_match_allowed(self):
        assert is_origin_allowed("https://a", ("https://a", "https://b")) is True

    def test_unlisted_origin_rejected(self):
        assert is_origin_allowed("https://c", ("https://a",)) is False

    def test_wildcard_allows_any(self):
        assert is_origin_allowed("https://anything", ("*",)) is True


class TestAllowedOriginsFromSettings:
    def test_filters_empty_values(self, monkeypatch):
        monkeypatch.setattr(
            cors,
            "settings",
            types.SimpleNamespace(cors_allowed_origins=["https://a", "", None, "https://b"]),
        )
        assert allowed_origins_from_settings() == ("https://a", "https://b")


class TestApplyBaseHeaders:
    def test_wildcard_sets_star_without_credentials(self):
        response = _FakeResponse()
        apply_base_headers(response, "https://a", ("*",))
        assert response.headers["Access-Control-Allow-Origin"] == "*"
        assert "Access-Control-Allow-Credentials" not in response.headers
        assert response.headers["Access-Control-Max-Age"] == DEFAULT_CORS_MAX_AGE

    def test_specific_origin_sets_credentials_and_vary(self):
        response = _FakeResponse()
        apply_base_headers(response, "https://a", ("https://a",))
        assert response.headers["Access-Control-Allow-Origin"] == "https://a"
        assert response.headers["Access-Control-Allow-Credentials"] == "true"
        assert "Origin" in (response.headers.get("Vary") or "")

    def test_existing_max_age_is_preserved(self):
        response = _FakeResponse()
        response.headers["Access-Control-Max-Age"] = "10"
        apply_base_headers(response, "https://a", ("https://a",))
        assert response.headers["Access-Control-Max-Age"] == "10"
