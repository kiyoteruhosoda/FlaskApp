"""Local import application services.

モジュールの初期化時に重い依存関係を読み込まないよう、
必要なクラス・関数は遅延読み込みで公開する。
DDD のレイヤードアーキテクチャに沿い、
他モジュールからの利用時にのみインフラ層へ依存する。"""

from __future__ import annotations

from importlib import import_module
from typing import Any, Dict, Tuple

__all__ = (
    "ImportDirectoryScanner",
    "LocalImportFileImporter",
    "LocalImportQueueProcessor",
    "LocalImportTaskLogger",
    "LocalImportUseCase",
    "PlaybackError",
    "build_thumbnail_task_snapshot",
)

_MODULE_MAP: Dict[str, Tuple[str, str]] = {
    "ImportDirectoryScanner": ("scanner", "ImportDirectoryScanner"),
    "LocalImportFileImporter": ("file_importer", "LocalImportFileImporter"),
    "LocalImportQueueProcessor": ("queue", "LocalImportQueueProcessor"),
    "LocalImportTaskLogger": ("logger", "LocalImportTaskLogger"),
    "LocalImportUseCase": ("use_case", "LocalImportUseCase"),
    "PlaybackError": ("file_importer", "PlaybackError"),
    "build_thumbnail_task_snapshot": ("results", "build_thumbnail_task_snapshot"),
}


def __getattr__(name: str) -> Any:
    """Resolve public attributes on demand to avoid circular imports."""

    try:
        module_name, attribute = _MODULE_MAP[name]
    except KeyError as exc:  # pragma: no cover - Python runtime raises AttributeError
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc

    module = import_module(f".{module_name}", __name__)
    return getattr(module, attribute)


def __dir__() -> Tuple[str, ...]:
    """Provide module attributes for ``dir()`` introspection."""

    return tuple(sorted(__all__))
