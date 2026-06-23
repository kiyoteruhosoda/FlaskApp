"""ストレージサービスのファクトリ.

``shared.kernel.settings._StorageAccessor`` からサービス生成責務を切り出し、
storage context 内に集約する。``settings`` は設定値のみを供給し、
``StorageService`` インスタンスの生成はこのモジュールが担う。
"""

from __future__ import annotations

from typing import Callable, Optional, TYPE_CHECKING
from weakref import WeakKeyDictionary

from shared.kernel.storage_types import StorageBackendType

if TYPE_CHECKING:
    from bounded_contexts.storage.infrastructure.filesystem import StorageService

StorageConfigResolver = Callable[[str], Optional[str]]
StorageFactory = Callable[
    [Optional[StorageConfigResolver], Optional[StorageConfigResolver]],
    "StorageService",
]

_factories: dict[StorageBackendType, StorageFactory] = {}


def register_backend(backend: StorageBackendType, factory: StorageFactory) -> None:
    """Register a factory callable for the given backend type."""
    _factories[backend] = factory


def _local_factory(
    config_resolver: Optional[StorageConfigResolver],
    env_resolver: Optional[StorageConfigResolver],
) -> "StorageService":
    from bounded_contexts.storage.infrastructure.filesystem import LocalFilesystemStorageService
    return LocalFilesystemStorageService(
        config_resolver=config_resolver,
        env_resolver=env_resolver,
    )


def _azure_blob_factory(
    config_resolver: Optional[StorageConfigResolver],
    env_resolver: Optional[StorageConfigResolver],
) -> "StorageService":
    from bounded_contexts.storage.infrastructure.filesystem import AzureBlobStorageService
    return AzureBlobStorageService(
        config_resolver=config_resolver,
        env_resolver=env_resolver,
    )


def _external_rest_factory(
    config_resolver: Optional[StorageConfigResolver],
    env_resolver: Optional[StorageConfigResolver],
) -> "StorageService":
    from bounded_contexts.storage.infrastructure.filesystem import ExternalRestStorageService
    return ExternalRestStorageService(
        config_resolver=config_resolver,
        env_resolver=env_resolver,
    )


register_backend(StorageBackendType.LOCAL, _local_factory)
register_backend(StorageBackendType.AZURE_BLOB, _azure_blob_factory)
register_backend(StorageBackendType.EXTERNAL_REST, _external_rest_factory)


def create_storage_service(
    backend_type: StorageBackendType,
    config_resolver: Optional[StorageConfigResolver],
    env_resolver: Optional[StorageConfigResolver],
) -> "StorageService":
    """Instantiate a StorageService for the given backend type."""
    factory = _factories.get(backend_type)
    if factory is None:
        raise ValueError(f"Storage backend '{backend_type.value}' is not registered")
    return factory(config_resolver, env_resolver)


_service_cache: "WeakKeyDictionary[object, StorageService]" = WeakKeyDictionary()


def get_storage_service(settings: object) -> "StorageService":
    """Return the StorageService for an ApplicationSettings instance.

    The service is cached per ``settings`` instance so that state applied to it
    (e.g. ``set_defaults``) persists across calls within the same process.  This
    mirrors the singleton behaviour of the previous ``settings.storage.service()``
    accessor.
    """
    cached = _service_cache.get(settings)
    if cached is not None:
        return cached

    backend_type = settings.storage_backend  # type: ignore[attr-defined]
    config_resolver = settings.storage.configured  # type: ignore[attr-defined]
    env_resolver = settings.storage.environment  # type: ignore[attr-defined]
    service = create_storage_service(backend_type, config_resolver, env_resolver)
    _service_cache[settings] = service
    return service


def reset_storage_service(settings: object) -> None:
    """Drop the cached StorageService for *settings* (mainly for tests)."""
    _service_cache.pop(settings, None)
