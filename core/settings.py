"""後方互換シム: 実体は :mod:`shared.kernel.settings.settings` へ移動した。

DDD のカーネル層 (Shared Kernel) を単一の真実の源とするため、アプリケーション
設定の集約点 :class:`ApplicationSettings` と ``settings`` シングルトンは
``shared.kernel.settings.settings`` に集約する。既存の
``from core.settings import settings, ApplicationSettings`` を壊さないよう
同一オブジェクトを再公開する。
"""

from shared.kernel.settings.settings import *  # noqa: F401,F403


def __getattr__(name):  # PEP 562: __all__ 外の名前も遅延委譲する
    import importlib

    module = importlib.import_module("shared.kernel.settings.settings")
    try:
        return getattr(module, name)
    except AttributeError as exc:  # pragma: no cover - 通常は到達しない
        raise AttributeError(
            f"module {__name__!r} has no attribute {name!r}"
        ) from exc
