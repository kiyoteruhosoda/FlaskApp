"""後方互換シム: 実体は :mod:`bounded_contexts.photonest.tasks.transcode` へ移動した。

Celery タスク実装を所有 context／共有層へ集約。Celery タスク名は
cli/src/celery/tasks.py で明示されており不変。既存の import を壊さない
よう再公開する。新規コードは正本を直接 import すること。
"""

from bounded_contexts.photonest.tasks.transcode import *  # noqa: F401,F403


def __getattr__(name):  # PEP 562
    import importlib
    module = importlib.import_module("bounded_contexts.photonest.tasks.transcode")
    try:
        return getattr(module, name)
    except AttributeError as exc:  # pragma: no cover
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
