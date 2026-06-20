"""後方互換シム: 実体は :mod:`shared.kernel.logging.lifecycle_logging` へ移動した。

サーバーライフサイクルのログ出力 (``register_lifecycle_logging``) は DDD の
カーネル層に集約する。既存の
``from core.lifecycle_logging import register_lifecycle_logging`` を壊さないよう
委譲する。
"""

from shared.kernel.logging.lifecycle_logging import *  # noqa: F401,F403


def __getattr__(name):  # PEP 562: 公開されていない名前も遅延委譲する
    import importlib

    module = importlib.import_module("shared.kernel.logging.lifecycle_logging")
    try:
        return getattr(module, name)
    except AttributeError as exc:  # pragma: no cover - 通常は到達しない
        raise AttributeError(
            f"module {__name__!r} has no attribute {name!r}"
        ) from exc
