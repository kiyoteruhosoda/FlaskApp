from __future__ import annotations

from core import storage_paths


def test_resolve_storage_file_returns_existing_path(tmp_path, monkeypatch):
    base_dir = tmp_path / "play"
    base_dir.mkdir()
    playback_file = base_dir / "video.mp4"
    playback_file.write_text("test")

    monkeypatch.setitem(
        storage_paths._STORAGE_DEFAULTS, "FPV_NAS_PLAY_DIR", (str(base_dir),)
    )

    base, resolved, exists = storage_paths.resolve_storage_file(
        "FPV_NAS_PLAY_DIR", "video.mp4"
    )

    assert base == str(base_dir)
    assert resolved == str(playback_file)
    assert exists is True


def test_resolve_storage_file_handles_missing_path_parts(monkeypatch):
    monkeypatch.setitem(
        storage_paths._STORAGE_DEFAULTS, "TEST_STORAGE_DIR", ("/does/not/matter",)
    )

    base, resolved, exists = storage_paths.resolve_storage_file(
        "TEST_STORAGE_DIR", None  # type: ignore[arg-type]
    )

    assert base is None
    assert resolved is None
    assert exists is False


def test_resolve_storage_file_without_parts_returns_base(tmp_path, monkeypatch):
    base_dir = tmp_path / "thumbs"
    base_dir.mkdir()

    monkeypatch.delenv("FPV_NAS_THUMBS_DIR", raising=False)
    monkeypatch.delenv("FPV_NAS_THUMBS_CONTAINER_DIR", raising=False)

    monkeypatch.setitem(
        storage_paths._STORAGE_DEFAULTS, "FPV_NAS_THUMBS_DIR", (str(base_dir),)
    )

    base, resolved, exists = storage_paths.resolve_storage_file("FPV_NAS_THUMBS_DIR")

    assert base == str(base_dir)
    assert resolved == str(base_dir)
    assert exists is True
