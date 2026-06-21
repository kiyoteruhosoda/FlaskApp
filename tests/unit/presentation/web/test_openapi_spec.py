"""`presentation/web/openapi_spec.py` の単体テスト。

OpenAPI のサーバ URL 算出はプロキシ配下やサブパス公開時のドキュメント正しさに
直結するため、URL 正規化・結合の純粋関数と、リクエスト依存の算出ロジックの
両方を境界条件まで検証する。リクエスト依存部はモジュールの ``request`` /
``settings`` を差し替えることで、アプリ生成や DB に依存せず検証する。
"""

import types

import pytest

from presentation.web import openapi_spec
from presentation.web.openapi_spec import (
    build_base_url,
    calculate_openapi_server_urls,
    combine_base_and_prefix,
    ensure_openapi_success_responses,
    normalize_openapi_prefix,
    normalize_script_root,
    strip_openapi_path_prefix,
)


class _FakeSpec:
    """apispec の ``_paths`` だけを模した最小スタブ。"""

    def __init__(self, paths):
        self._paths = paths


class _FakeRequest:
    def __init__(self, *, host="", host_url="", url_root="", scheme="http",
                 script_root="", headers=None, environ=None):
        self.host = host
        self.host_url = host_url
        self.url_root = url_root
        self.scheme = scheme
        self.script_root = script_root
        self.headers = headers or {}
        self.environ = environ or {}


@pytest.fixture
def patch_request(monkeypatch):
    def _apply(request_obj, scheme_setting=None):
        monkeypatch.setattr(openapi_spec, "request", request_obj)
        monkeypatch.setattr(
            openapi_spec,
            "settings",
            types.SimpleNamespace(preferred_url_scheme=scheme_setting),
        )

    return _apply


class TestNormalizeOpenapiPrefix:
    @pytest.mark.parametrize(
        "value,expected",
        [
            (None, ""),
            ("", ""),
            ("   ", ""),
            ("api", "/api"),
            ("/api/", "/api"),
            ("/api/v1///", "/api/v1"),
        ],
    )
    def test_normalization(self, value, expected):
        assert normalize_openapi_prefix(value) == expected


class TestNormalizeScriptRoot:
    @pytest.mark.parametrize(
        "value,expected",
        [
            (None, ""),
            ("", ""),
            ("app", "/app"),
            ("/app/", "/app"),
        ],
    )
    def test_normalization(self, value, expected):
        assert normalize_script_root(value) == expected


class TestBuildBaseUrl:
    def test_without_script_root(self):
        assert build_base_url("https", "example.com", "") == "https://example.com"

    def test_with_script_root(self):
        assert build_base_url("https", "example.com", "/app") == "https://example.com/app"

    def test_root_script_root_is_ignored(self):
        assert build_base_url("http", "h", "/") == "http://h"


class TestCombineBaseAndPrefix:
    def test_appends_prefix(self):
        assert combine_base_and_prefix("https://h", "/api") == "https://h/api"

    def test_no_prefix_returns_base(self):
        assert combine_base_and_prefix("https://h/", "") == "https://h"

    def test_does_not_double_apply_prefix(self):
        assert combine_base_and_prefix("https://h/api", "/api") == "https://h/api"

    def test_root_base_returns_prefix(self):
        assert combine_base_and_prefix("/", "/api") == "/api"


class TestStripOpenapiPathPrefix:
    def test_strips_common_prefix(self):
        spec = _FakeSpec({"/api/users": {"get": {}}, "/api/items": {"post": {}}})
        strip_openapi_path_prefix(spec, "/api")
        assert set(spec._paths.keys()) == {"/users", "/items"}

    def test_prefix_exactly_equals_path_becomes_root(self):
        spec = _FakeSpec({"/api": {"get": {}}})
        strip_openapi_path_prefix(spec, "/api")
        assert list(spec._paths.keys()) == ["/"]

    def test_paths_without_prefix_are_untouched(self):
        spec = _FakeSpec({"/api/x": {}, "/health": {}})
        strip_openapi_path_prefix(spec, "/api")
        assert set(spec._paths.keys()) == {"/x", "/health"}

    def test_no_prefix_is_noop(self):
        spec = _FakeSpec({"/api/x": {}})
        strip_openapi_path_prefix(spec, "")
        assert list(spec._paths.keys()) == ["/api/x"]

    def test_missing_paths_attribute_is_safe(self):
        strip_openapi_path_prefix(object(), "/api")  # no _paths -> no error


class TestEnsureOpenapiSuccessResponses:
    def test_adds_default_200_when_missing(self):
        spec = _FakeSpec({"/x": {"get": {"responses": {"400": {}}}}})
        ensure_openapi_success_responses(spec)
        assert "200" in spec._paths["/x"]["get"]["responses"]

    def test_keeps_existing_success_response(self):
        spec = _FakeSpec({"/x": {"get": {"responses": {"201": {"description": "ok"}}}}})
        ensure_openapi_success_responses(spec)
        responses = spec._paths["/x"]["get"]["responses"]
        assert "200" not in responses
        assert responses["201"]["description"] == "ok"

    def test_creates_responses_block_when_absent(self):
        spec = _FakeSpec({"/x": {"get": {}}})
        ensure_openapi_success_responses(spec)
        assert "200" in spec._paths["/x"]["get"]["responses"]

    def test_none_spec_is_safe(self):
        ensure_openapi_success_responses(None)


class TestCalculateOpenapiServerUrls:
    def test_builds_url_from_host_and_prefix(self, patch_request):
        patch_request(_FakeRequest(host="example.com", scheme="https"))
        assert calculate_openapi_server_urls("/api") == ["https://example.com/api"]

    def test_configured_scheme_listed_first(self, patch_request):
        # 設定スキームを先頭に、リクエストのスキームも候補として列挙する。
        patch_request(
            _FakeRequest(host="example.com", scheme="http"),
            scheme_setting="https",
        )
        assert calculate_openapi_server_urls("") == [
            "https://example.com",
            "http://example.com",
        ]

    def test_honours_x_forwarded_proto(self, patch_request):
        patch_request(
            _FakeRequest(
                host="example.com",
                scheme="http",
                headers={"X-Forwarded-Proto": "https"},
            )
        )
        urls = calculate_openapi_server_urls("/api")
        assert "https://example.com/api" in urls

    def test_honours_forwarded_header_proto(self, patch_request):
        patch_request(
            _FakeRequest(
                host="example.com",
                scheme="http",
                headers={"Forwarded": 'proto=https;host=example.com'},
            )
        )
        urls = calculate_openapi_server_urls("/api")
        assert "https://example.com/api" in urls

    def test_includes_script_root(self, patch_request):
        patch_request(
            _FakeRequest(host="example.com", scheme="https", script_root="/app")
        )
        assert calculate_openapi_server_urls("/api") == ["https://example.com/app/api"]

    def test_falls_back_to_host_url_when_host_missing(self, patch_request):
        patch_request(
            _FakeRequest(host="", host_url="https://fallback.example/", scheme="https")
        )
        assert calculate_openapi_server_urls("/api") == ["https://fallback.example/api"]

    def test_fallback_to_prefix_when_no_host(self, patch_request):
        patch_request(_FakeRequest(host="", scheme="https"))
        assert calculate_openapi_server_urls("/api") == ["/api"]

    def test_fallback_to_root_when_no_host_and_no_prefix(self, patch_request):
        patch_request(_FakeRequest(host="", scheme="https"))
        assert calculate_openapi_server_urls("") == ["/"]
