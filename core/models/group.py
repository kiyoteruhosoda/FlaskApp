"""後方互換シム: 実体は :mod:`shared.infrastructure.models.group` へ移動した。

ORM モデルを所有 context／共有 infrastructure へ集約。既存の import を
壊さないよう再公開する。新規コードは正本を直接 import すること。
"""

from shared.infrastructure.models.group import *  # noqa: F401,F403


def __getattr__(name):  # PEP 562: __all__ 外の名前も遅延委譲する
    import importlib

    module = importlib.import_module("shared.infrastructure.models.group")
    try:
        return getattr(module, name)
    except AttributeError as exc:  # pragma: no cover
        raise AttributeError(
            f"module {__name__!r} has no attribute {name!r}"
        ) from exc
