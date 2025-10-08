import os

from core.storage_paths import resolve_storage_file


def test_resolve_storage_file_with_missing_path_parts(monkeypatch):
    """Missing path components should not raise errors."""

    # Ensure that at least one candidate base path is available.
    monkeypatch.setenv("FPV_NAS_PLAY_DIR", os.getcwd())

    base, resolved, exists = resolve_storage_file("FPV_NAS_PLAY_DIR", None)

    assert base is None
    assert resolved is None
    assert exists is False
