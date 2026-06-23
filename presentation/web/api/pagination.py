"""後方互換シム: 実体は :mod:`shared.application.pagination` へ移動した。

ページネーション・カーソル処理は特定の presentation 層ではなく共有
application 層に属する（複数 bounded context から利用される）。既存の
``from presentation.web.api.pagination import ...`` を壊さないよう再公開する。
新規コードは ``shared.application.pagination`` を直接 import すること。
"""

from shared.application.pagination import *  # noqa: F401,F403


def __getattr__(name):  # PEP 562: __all__ 外の名前も遅延委譲する
    import importlib

    module = importlib.import_module("shared.application.pagination")
    try:
        return getattr(module, name)
    except AttributeError as exc:  # pragma: no cover
        raise AttributeError(
            f"module {__name__!r} has no attribute {name!r}"
        ) from exc
