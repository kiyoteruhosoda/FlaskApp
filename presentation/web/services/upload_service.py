"""後方互換シム: 実体は :mod:`shared.application.upload_service` へ移動した。

ファイルアップロード・コミット処理は presentation 固有ではなく、複数の
bounded context（wiki など）と presentation 層の双方から利用される application
サービスである。既存の ``from presentation.web.services.upload_service import ...``
を壊さないよう再公開する。新規コードは ``shared.application.upload_service`` を
直接 import すること。
"""

from shared.application.upload_service import *  # noqa: F401,F403


def __getattr__(name):  # PEP 562: __all__ 外の名前（_helpers 等）も遅延委譲する
    import importlib

    module = importlib.import_module("shared.application.upload_service")
    try:
        return getattr(module, name)
    except AttributeError as exc:  # pragma: no cover
        raise AttributeError(
            f"module {__name__!r} has no attribute {name!r}"
        ) from exc
