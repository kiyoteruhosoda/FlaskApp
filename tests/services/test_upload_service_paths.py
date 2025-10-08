from pathlib import Path

import pytest

from webapp.services.upload_service import (
    UploadError,
    _destination_base_dir,
    _tmp_base_dir,
)


def test_tmp_and_destination_dir_fallback(monkeypatch, app_context, tmp_path):
    app = app_context
    forbidden_root = tmp_path / "forbidden"
    app.config["UPLOAD_TMP_DIR"] = str(forbidden_root / "tmp")
    app.config["UPLOAD_DESTINATION_DIR"] = str(forbidden_root / "dest")

    original_mkdir = Path.mkdir

    def fake_mkdir(self, mode=0o777, parents=False, exist_ok=False):
        if str(self).startswith(str(forbidden_root)):
            raise PermissionError("denied")
        return original_mkdir(self, mode=mode, parents=parents, exist_ok=exist_ok)

    monkeypatch.setattr(Path, "mkdir", fake_mkdir)

    with app.test_request_context():
        tmp_dir = _tmp_base_dir()
        dest_dir = _destination_base_dir()

    instance_path = Path(app.instance_path)

    assert tmp_dir.is_relative_to(instance_path)
    assert dest_dir.is_relative_to(instance_path)
    assert (tmp_dir).exists()
    assert (dest_dir).exists()


def test_tmp_dir_raises_when_no_candidate_writable(monkeypatch, app_context):
    app = app_context
    app.config["UPLOAD_TMP_DIR"] = "/surely/forbidden"

    def always_fail(self, mode=0o777, parents=False, exist_ok=False):
        raise PermissionError("denied")

    monkeypatch.setattr(Path, "mkdir", always_fail)

    with app.test_request_context():
        with pytest.raises(UploadError):
            _tmp_base_dir()
