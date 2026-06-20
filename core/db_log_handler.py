"""後方互換シム: 実体は :mod:`shared.kernel.logging.db_log_handler` へ移動した。

DB ログハンドラ (:class:`DBLogHandler` / :class:`WorkerDBLogHandler`) は DDD の
カーネル層に集約する。既存の ``from core.db_log_handler import DBLogHandler``
等を壊さないよう委譲する。
"""

from shared.kernel.logging.db_log_handler import *  # noqa: F401,F403


def __getattr__(name):  # PEP 562: 公開されていない名前も遅延委譲する
    import importlib

    module = importlib.import_module("shared.kernel.logging.db_log_handler")
    try:
        return getattr(module, name)
    except AttributeError as exc:  # pragma: no cover - 通常は到達しない
        raise AttributeError(
            f"module {__name__!r} has no attribute {name!r}"
        ) from exc
