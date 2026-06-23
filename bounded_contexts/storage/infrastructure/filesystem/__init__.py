"""ストレージアクセスを統制するサービス群.

抽象（contract）と具象実装（local / backends）を分離して提供する。利用側は
本パッケージから ``StorageService`` 抽象や各実装をインポートする。
"""

from __future__ import annotations

from .contract import (
    PathPart,
    ResolvedPath,
    StorageArea,
    StorageSelector,
    StorageService,
)
from .local import LocalFilesystemStorageService
from .backends import (
    AzureBlobStorageService,
    ExternalRestStorageService,
)

__all__ = [
    "PathPart",
    "StorageSelector",
    "ResolvedPath",
    "StorageArea",
    "StorageService",
    "LocalFilesystemStorageService",
    "AzureBlobStorageService",
    "ExternalRestStorageService",
]
