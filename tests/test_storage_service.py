from __future__ import annotations

from core.storage_service import LocalFilesystemStorageService


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

    service = _make_service({"FPV_NAS_PLAY_DIR": str(base_dir)})

    resolution = service.resolve_path("FPV_NAS_PLAY_DIR", "video.mp4")

    assert resolution.base_path == str(base_dir)
    assert resolution.absolute_path == str(playback_file)
    assert resolution.exists is True


def test_local_service_resolve_handles_invalid_parts():
    service = _make_service({"LOCAL_IMPORT_DIR": "/tmp/local_import"})

    resolution = service.resolve_path("LOCAL_IMPORT_DIR", None)  # type: ignore[arg-type]

    assert resolution.base_path is None
    assert resolution.absolute_path is None
    assert resolution.exists is False


def test_local_service_resolve_without_parts_returns_base(tmp_path):
    base_dir = tmp_path / "thumbs"
    base_dir.mkdir()

    service = _make_service()
    service.set_defaults("FPV_NAS_THUMBS_DIR", (str(base_dir),))

    resolution = service.resolve_path("FPV_NAS_THUMBS_DIR")

    assert resolution.base_path == str(base_dir)
    assert resolution.absolute_path == str(base_dir)
    assert resolution.exists is True
