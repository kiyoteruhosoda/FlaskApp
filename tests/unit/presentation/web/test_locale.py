"""`presentation/web/templating/locale.py` のロケール選択の単体テスト。

表示言語の決定はユーザー体験に直結するため、cookie > Accept-Language > 既定の
優先順位とコンテキスト外フォールバックを検証する。アプリ設定は差し替え、
リクエストは Flask の ``test_request_context`` で再現して DB 非依存とする。
"""

import types

import pytest
from flask import Flask

from presentation.web.templating import locale
from presentation.web.templating.locale import select_locale


@pytest.fixture
def patched_settings(monkeypatch):
    def _apply(languages, default="en"):
        monkeypatch.setattr(
            locale,
            "settings",
            types.SimpleNamespace(
                languages=languages,
                babel_default_locale=default,
            ),
        )

    return _apply


@pytest.fixture
def flask_app():
    return Flask(__name__)


def test_outside_request_context_returns_default(patched_settings):
    patched_settings(["en", "ja"], default="ja")
    assert select_locale() == "ja"


def test_cookie_language_takes_priority(patched_settings, flask_app):
    patched_settings(["en", "ja"])
    with flask_app.test_request_context(
        headers={"Accept-Language": "en"}, environ_base={"HTTP_COOKIE": "lang=ja"}
    ):
        assert select_locale() == "ja"


def test_unknown_cookie_falls_back_to_accept_language(patched_settings, flask_app):
    patched_settings(["en", "ja"])
    with flask_app.test_request_context(
        headers={"Accept-Language": "ja"}, environ_base={"HTTP_COOKIE": "lang=fr"}
    ):
        assert select_locale() == "ja"


def test_falls_back_to_default_when_no_match(patched_settings, flask_app):
    patched_settings(["en", "ja"], default="en")
    with flask_app.test_request_context(headers={"Accept-Language": "fr"}):
        assert select_locale() == "en"


def test_empty_languages_returns_default(patched_settings, flask_app):
    patched_settings([], default="en")
    with flask_app.test_request_context(headers={"Accept-Language": "ja"}):
        assert select_locale() == "en"
