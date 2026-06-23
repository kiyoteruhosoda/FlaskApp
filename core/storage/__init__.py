"""後方互換シム: 実体は
:mod:`bounded_contexts.storage.infrastructure.filesystem` へ移動した。

パス解決ストレージサービス（``StorageService`` / ``StorageArea`` /
``LocalFilesystemStorageService`` 等）は storage bounded context の
infrastructure 層に属する。既存の ``from core.storage import ...`` を壊さない
よう再公開する。新規コードは context 側を直接 import すること。
"""

from bounded_contexts.storage.infrastructure.filesystem import *  # noqa: F401,F403


def __getattr__(name):  # PEP 562: __all__ 外の名前も遅延委譲する
    import importlib

    module = importlib.import_module(
        "bounded_contexts.storage.infrastructure.filesystem"
    )
    try:
        return getattr(module, name)
    except AttributeError as exc:  # pragma: no cover
        raise AttributeError(
            f"module {__name__!r} has no attribute {name!r}"
        ) from exc
