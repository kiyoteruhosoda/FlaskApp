"""後方互換シム: 実体は
:mod:`bounded_contexts.storage.infrastructure.filesystem` へ移動した。

パス解決ストレージサービスは storage bounded context の infrastructure 層へ
集約された。抽象（``...filesystem.contract``）と具象実装
（``...filesystem.local`` / ``...filesystem.backends``）へ分割されている。既存の
``from core.storage_service import ...`` を壊さないよう、公開・内部名を再公開する。
新規コードは context 側を直接 import すること。
"""

from __future__ import annotations

from bounded_contexts.storage.infrastructure.filesystem import (  # noqa: F401
    AzureBlobStorageService,
    ExternalRestStorageService,
    LocalFilesystemStorageService,
    PathPart,
    ResolvedPath,
    StorageArea,
    StorageSelector,
    StorageService,
)
from bounded_contexts.storage.infrastructure.filesystem.contract import _StorageSpec  # noqa: F401
from bounded_contexts.storage.infrastructure.filesystem.local import (  # noqa: F401
    _KNOWN_SPECS,
    _LocalStorageArea,
)
from bounded_contexts.storage.infrastructure.filesystem.backends import (  # noqa: F401
    _UnimplementedStorageService,
)
