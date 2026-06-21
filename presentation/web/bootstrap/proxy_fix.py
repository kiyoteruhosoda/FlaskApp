"""リバースプロキシ配下での HTTPS 検出（ProxyFix）.

``create_app()`` 内に定義されていた ``ProxyFix`` のカスタマイズを切り出す。
``X-Forwarded-*`` を信頼してスキーム/ホストを補正しつつ、補正前後のスキームを
デバッグログに残す。
"""

from __future__ import annotations

from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix


class _DebugProxyFix(ProxyFix):
    """補正前後のスキーム等をデバッグログへ出力する ``ProxyFix``."""

    def __init__(self, wsgi_app, logger, **kwargs):
        super().__init__(wsgi_app, **kwargs)
        self._logger = logger

    def __call__(self, environ, start_response):
        self._logger.debug(f"ProxyFix - Original scheme: {environ.get('wsgi.url_scheme')}")
        self._logger.debug(f"ProxyFix - X-Forwarded-Proto: {environ.get('HTTP_X_FORWARDED_PROTO')}")
        self._logger.debug(f"ProxyFix - X-Forwarded-Host: {environ.get('HTTP_X_FORWARDED_HOST')}")
        result = super().__call__(environ, start_response)
        self._logger.debug(f"ProxyFix - Final scheme: {environ.get('wsgi.url_scheme')}")
        return result


def apply_debug_proxy_fix(app: Flask) -> None:
    """アプリの WSGI スタックへデバッグ付き ProxyFix を適用する。"""

    app.wsgi_app = _DebugProxyFix(
        app.wsgi_app, app.logger, x_for=1, x_proto=1, x_host=1, x_prefix=1
    )
