from __future__ import annotations

import pytest

from shared.kernel.settings.settings import ApplicationSettings
from bounded_contexts.storage.infrastructure.filesystem import (
    AzureBlobStorageService,
    ExternalRestStorageService,
    LocalFilesystemStorageService,
)
from bounded_contexts.storage import StorageBackendType
from bounded_contexts.storage.application import filesystem_factory
from bounded_contexts.storage.application.filesystem_factory import (
    create_storage_service,
    get_storage_service,
)


def _make_service(config: dict[str, str] | None = None) -> LocalFilesystemStorageService:
    config = config or {}
    return LocalFilesystemStorageService(
        config_resolver=config.get,
        env_resolver=lambda key: None,
    )


def test_local_service_resolve_existing_path(tmp_path):
    base_dir = tmp_path / "play"
    base_dir.mkdir()
    playback_file = base_dir / "video.mp4"
    playback_file.write_text("test")

    service = _make_service({"MEDIA_PLAYBACK_DIRECTORY": str(base_dir)})

    resolution = service.resolve_path("MEDIA_PLAYBACK_DIRECTORY", "video.mp4")

    assert resolution.base_path == str(base_dir)
    assert resolution.absolute_path == str(playback_file)
    assert resolution.exists is True


def test_local_service_resolve_handles_invalid_parts():
    service = _make_service({"MEDIA_LOCAL_IMPORT_DIRECTORY": "/tmp/local_import"})

    resolution = service.resolve_path("MEDIA_LOCAL_IMPORT_DIRECTORY", None)  # type: ignore[arg-type]

    assert resolution.base_path is None
    assert resolution.absolute_path is None
    assert resolution.exists is False


def test_local_service_resolve_without_parts_returns_base(tmp_path):
    base_dir = tmp_path / "thumbs"
    base_dir.mkdir()

    service = _make_service()
    service.set_defaults("MEDIA_THUMBNAILS_DIRECTORY", (str(base_dir),))

    resolution = service.resolve_path("MEDIA_THUMBNAILS_DIRECTORY")

    assert resolution.base_path == str(base_dir)
    assert resolution.absolute_path == str(base_dir)
    assert resolution.exists is True


def test_settings_storage_backend_defaults_to_local():
    settings = ApplicationSettings(env={})

    service = get_storage_service(settings)

    assert isinstance(service, LocalFilesystemStorageService)


def test_filesystem_factory_custom_backend():
    """filesystem_factory の register_backend でカスタムファクトリが使われること."""
    settings = ApplicationSettings(env={"STORAGE_BACKEND": "external_rest"})
    created: list[str] = []

    original_factory = filesystem_factory._factories.get(StorageBackendType.EXTERNAL_REST)

    def custom_factory(config_resolver, env_resolver):
        created.append("called")
        return LocalFilesystemStorageService(
            config_resolver=config_resolver,
            env_resolver=env_resolver,
        )

    filesystem_factory.register_backend(StorageBackendType.EXTERNAL_REST, custom_factory)

    try:
        service = get_storage_service(settings)
        assert isinstance(service, LocalFilesystemStorageService)
        assert created
    finally:
        if original_factory is not None:
            filesystem_factory.register_backend(StorageBackendType.EXTERNAL_REST, original_factory)
        elif StorageBackendType.EXTERNAL_REST in filesystem_factory._factories:
            del filesystem_factory._factories[StorageBackendType.EXTERNAL_REST]


def test_settings_storage_backend_invalid_value():
    settings = ApplicationSettings(env={"STORAGE_BACKEND": "invalid"})

    with pytest.raises(ValueError):
        _ = settings.storage_backend


def test_settings_storage_backend_azure_blob_placeholder():
    settings = ApplicationSettings(env={"STORAGE_BACKEND": "azure_blob"})

    service = get_storage_service(settings)

    assert isinstance(service, AzureBlobStorageService)

    with pytest.raises(NotImplementedError):
        service.exists("anything")


def test_settings_storage_backend_external_rest_placeholder():
    settings = ApplicationSettings(env={"STORAGE_BACKEND": "external_rest"})

    service = get_storage_service(settings)

    assert isinstance(service, ExternalRestStorageService)

    with pytest.raises(NotImplementedError):
        service.exists("anything")
