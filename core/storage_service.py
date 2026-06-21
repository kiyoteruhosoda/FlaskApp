"""後方互換シム: 実体は :mod:`core.storage` パッケージへ移動した。

ストレージサービスは抽象（``core.storage.contract``）と具象実装
（``core.storage.local`` / ``core.storage.backends``）へ分割された。既存の
``from core.storage_service import ...`` を壊さないよう、公開・内部名を再公開する。
"""

from __future__ import annotations

from core.storage import (  # noqa: F401
    AzureBlobStorageService,
    ExternalRestStorageService,
    LocalFilesystemStorageService,
    PathPart,
    ResolvedPath,
    StorageArea,
    StorageSelector,
    StorageService,
)
from core.storage.contract import _StorageSpec  # noqa: F401
from core.storage.local import _KNOWN_SPECS, _LocalStorageArea  # noqa: F401
from core.storage.backends import _UnimplementedStorageService  # noqa: F401
