"""後方互換シム: 実体は :mod:`shared.kernel.logging.logging_config` へ移動した。

タスク向けロギング設定 (``setup_task_logging`` / ``structured_task_logger`` 等) は
DDD のカーネル層に集約する。既存の ``from core.logging_config import ...`` を
壊さないよう委譲する。
"""

from shared.kernel.logging.logging_config import *  # noqa: F401,F403


def __getattr__(name):  # PEP 562: 公開されていない名前も遅延委譲する
    import importlib

    module = importlib.import_module("shared.kernel.logging.logging_config")
    try:
        return getattr(module, name)
    except AttributeError as exc:  # pragma: no cover - 通常は到達しない
        raise AttributeError(
            f"module {__name__!r} has no attribute {name!r}"
        ) from exc
