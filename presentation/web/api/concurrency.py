"""後方互換シム: 実体は :mod:`shared.application.concurrency` へ移動した。

並行実行制限ユーティリティは特定の presentation 層ではなく共有 application 層に
属する（複数 bounded context から利用される）。既存の
``from presentation.web.api.concurrency import ...`` を壊さないよう再公開する。
新規コードは ``shared.application.concurrency`` を直接 import すること。
"""

from shared.application.concurrency import *  # noqa: F401,F403


def __getattr__(name):  # PEP 562: __all__ 外の名前も遅延委譲する
    import importlib

    module = importlib.import_module("shared.application.concurrency")
    try:
        return getattr(module, name)
    except AttributeError as exc:  # pragma: no cover
        raise AttributeError(
            f"module {__name__!r} has no attribute {name!r}"
        ) from exc
