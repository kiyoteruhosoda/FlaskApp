"""Storage helper functions extracted from presentation/web/api/routes.py."""
from __future__ import annotations

from dataclasses import dataclass

from bounded_contexts.storage.infrastructure.filesystem import StorageArea, StorageSelector, StorageService
from bounded_contexts.storage import StorageDomain, StorageIntent, StorageResolution
from shared.kernel.settings.settings import settings


_STORAGE_DEFAULTS: dict[str, tuple[str, ...]] = {}


@dataclass
class ResolvedStorageFile:
    selector: StorageSelector
    area: StorageArea
    resolution: StorageResolution


def _storage_service() -> StorageService:
    from bounded_contexts.storage.application.filesystem_factory import get_storage_service
    return get_storage_service(settings)


def _storage_area(selector: StorageSelector) -> StorageArea:
    service = _storage_service()
    if isinstance(selector, StorageDomain):
        return service.for_domain(selector)
    return service.for_key(selector)


def _normalize_storage_defaults(selector: StorageSelector) -> None:
    service = _storage_service()
    if isinstance(selector, StorageDomain):
        area = service.for_domain(selector)
        config_key = area.config_key
    else:
        config_key = selector

    defaults_override = _STORAGE_DEFAULTS.get(config_key)
    if defaults_override is None:
        return

    if isinstance(defaults_override, (list, tuple)):
        normalized = tuple(defaults_override)
    else:
        normalized = (defaults_override,)

    if _STORAGE_DEFAULTS.get(config_key) != normalized:
        _STORAGE_DEFAULTS[config_key] = normalized

    if service.defaults(config_key) != normalized:
        service.set_defaults(config_key, normalized)


def _storage_path_candidates(selector: StorageSelector) -> list[str]:
    _normalize_storage_defaults(selector)
    area = _storage_area(selector)
    return area.candidates()


def _storage_path(selector: StorageSelector) -> str | None:
    _normalize_storage_defaults(selector)
    area = _storage_area(selector)
    return area.first_existing()


def _resolve_storage_file(
    selector: StorageSelector,
    *path_parts: str,
    intent: StorageIntent = StorageIntent.READ,
) -> ResolvedStorageFile:
    _normalize_storage_defaults(selector)
    area = _storage_area(selector)
    resolution = area.resolve(*path_parts, intent=intent)
    return ResolvedStorageFile(selector=selector, area=area, resolution=resolution)


__all__ = [
    "ResolvedStorageFile",
    "_storage_service",
    "_storage_area",
    "_normalize_storage_defaults",
    "_storage_path_candidates",
    "_storage_path",
    "_resolve_storage_file",
]
