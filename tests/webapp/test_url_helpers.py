"""`webapp.utils.url_helpers` の `determine_external_scheme` をテストする。"""

from __future__ import annotations

import pytest
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from core.settings import settings
from webapp.utils.url_helpers import determine_external_scheme


def _build_request(*, headers: dict[str, str] | None = None, scheme: str = "http") -> Request:
    """指定したヘッダーとスキームで `Request` を生成する。"""

    builder = EnvironBuilder(
        method="GET",
        base_url=f"{scheme}://example.com",
        headers=headers or {},
    )
    environ = builder.get_environ()
    return Request(environ)


@pytest.fixture
def set_preferred_scheme(monkeypatch):
    """`settings.preferred_url_scheme` の値を一時的に差し替えるヘルパー。"""

    def _setter(value: str | None) -> None:
        monkeypatch.setattr(
            type(settings),
            "preferred_url_scheme",
            property(lambda self, _value=value: _value),
        )

    return _setter


def test_forwarded_proto_https_has_priority(set_preferred_scheme) -> None:
    set_preferred_scheme(None)
    request = _build_request(headers={"Forwarded": "for=1.1.1.1;proto=https"})

    assert determine_external_scheme(request) == "https"


def test_forwarded_proto_is_case_insensitive(set_preferred_scheme) -> None:
    set_preferred_scheme(None)
    request = _build_request(headers={"Forwarded": "Proto=HTTPS;Host=example.com"})

    assert determine_external_scheme(request) == "https"


def test_forwarded_proto_allows_http(set_preferred_scheme) -> None:
    set_preferred_scheme(None)
    request = _build_request(headers={"Forwarded": "for=1.2.3.4;proto=http"})

    assert determine_external_scheme(request) == "http"


def test_malformed_forwarded_falls_back_to_x_forwarded_proto(set_preferred_scheme) -> None:
    set_preferred_scheme(None)
    request = _build_request(
        headers={
            "Forwarded": "for=1.1.1.1;proto",  # proto= の形式ではないため無視される
            "X-Forwarded-Proto": "https",
        }
    )

    assert determine_external_scheme(request) == "https"


def test_x_forwarded_proto_used_when_present(set_preferred_scheme) -> None:
    set_preferred_scheme(None)
    request = _build_request(headers={"X-Forwarded-Proto": "https, http"})

    assert determine_external_scheme(request) == "https"


def test_preferred_url_scheme_used_when_no_proxy_headers(set_preferred_scheme) -> None:
    set_preferred_scheme("https")
    request = _build_request(scheme="http")

    assert determine_external_scheme(request) == "https"


def test_preferred_url_scheme_overrides_proxy_headers(set_preferred_scheme) -> None:
    set_preferred_scheme("https")
    request = _build_request(
        scheme="http",
        headers={
            "Forwarded": "for=1.2.3.4;proto=http",
            "X-Forwarded-Proto": "http",
        },
    )

    assert determine_external_scheme(request) == "https"


def test_request_scheme_used_as_next_fallback(set_preferred_scheme) -> None:
    set_preferred_scheme(None)
    request = _build_request(scheme="http")

    assert determine_external_scheme(request) == "http"


def test_default_to_https_when_no_scheme_information(set_preferred_scheme) -> None:
    set_preferred_scheme(None)

    class DummyRequest:
        def __init__(self) -> None:
            self.headers: dict[str, str] = {}
            self.environ: dict[str, str] = {}

    dummy_request = DummyRequest()

    assert determine_external_scheme(dummy_request) == "https"
