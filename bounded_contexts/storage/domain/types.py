"""Storage境界文脈のドメイン型定義.

実体は ``shared.kernel.storage_types`` に移動済み。
bounded context 内からの既存 import を維持するための再エクスポート。
"""

from shared.kernel.storage_types import (
    StorageBackendType,
    StorageDomain,
    StorageIntent,
    StorageResolution,
)

__all__ = [
    "StorageBackendType",
    "StorageDomain",
    "StorageIntent",
    "StorageResolution",
]
