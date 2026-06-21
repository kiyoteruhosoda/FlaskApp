"""テスト用 Flask クライアント.

``create_app()`` 内に定義されていたテストクライアントを切り出す。テストでは
ホストが未指定でも ``localhost`` を補い、``url_for`` 等が安定して動作するように
``SERVER_NAME`` / ``HTTP_HOST`` / ``base_url`` を ``localhost`` に固定する。
"""

from __future__ import annotations

from contextlib import contextmanager

from flask.testing import FlaskClient


class HostPreservingClient(FlaskClient):
    """ホスト未指定時に ``localhost`` を補うテストクライアント."""

    def __init__(self, *args, **kwargs):  # type: ignore[override]
        super().__init__(*args, **kwargs)
        self.environ_base.setdefault("SERVER_NAME", "localhost")
        self.environ_base.setdefault("HTTP_HOST", "localhost")

    def open(self, *args, **kwargs):  # type: ignore[override]
        if not kwargs.get("base_url"):
            kwargs["base_url"] = "http://localhost"
        return super().open(*args, **kwargs)

    @contextmanager
    def session_transaction(self, *args, **kwargs):  # type: ignore[override]
        kwargs.setdefault("base_url", "http://localhost")
        with super().session_transaction(*args, **kwargs) as sess:
            yield sess
