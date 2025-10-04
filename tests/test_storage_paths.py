from core.storage_paths import ensure_preferred_storage_path


def test_ensure_preferred_storage_path_prefers_first_candidate(tmp_path, monkeypatch):
    preferred = tmp_path / "preferred"
    fallback = tmp_path / "fallback"
    fallback.mkdir()

    monkeypatch.setenv("FPV_NAS_PLAY_CONTAINER_DIR", str(preferred))
    monkeypatch.setenv("FPV_NAS_PLAY_DIR", str(fallback))

    resolved = ensure_preferred_storage_path("FPV_NAS_PLAY_DIR")

    assert resolved == preferred
    assert preferred.is_dir()


def test_ensure_preferred_storage_path_uses_fallback_on_error(tmp_path, monkeypatch):
    invalid = tmp_path / "invalid"
    invalid.write_text("conflict")
    fallback = tmp_path / "fallback"

    monkeypatch.setenv("FPV_NAS_THUMBS_CONTAINER_DIR", str(invalid))
    monkeypatch.setenv("FPV_NAS_THUMBS_DIR", str(fallback))

    resolved = ensure_preferred_storage_path("FPV_NAS_THUMBS_DIR")

    assert resolved == fallback
    assert fallback.is_dir()
