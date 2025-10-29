"""Tests verifying HEIC/HEIF support in local import pipeline."""

import importlib
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from PIL import Image, UnidentifiedImageError
from pillow_heif import register_heif_opener

from core.tasks.local_import import (
    extract_exif_data,
    get_image_dimensions,
    import_single_file,
    scan_import_directory,
)
from core.utils import get_file_date_from_exif


@pytest.fixture(autouse=True)
def _ensure_heif_support() -> None:
    """Register the HEIF plugin for Pillow once per test session."""

    register_heif_opener()


@pytest.fixture
def local_import_app(tmp_path: Path):
    """Create a minimal Flask app configured for local import tests."""

    db_path = tmp_path / "test.db"
    tmp_dir = tmp_path / "tmp"
    orig_dir = tmp_path / "orig"
    import_dir = tmp_path / "import"
    tmp_dir.mkdir()
    orig_dir.mkdir()
    import_dir.mkdir()

    env = {
        "SECRET_KEY": "test",
        "DATABASE_URI": f"sqlite:///{db_path}",
        "MEDIA_TEMP_DIRECTORY": str(tmp_dir),
        "MEDIA_ORIGINALS_DIRECTORY": str(orig_dir),
        "MEDIA_LOCAL_IMPORT_DIRECTORY": str(import_dir),
    }
    prev_env = {key: os.environ.get(key) for key in env}
    os.environ.update(env)

    import webapp.config as config_module
    importlib.reload(config_module)
    import webapp as webapp_module
    importlib.reload(webapp_module)

    from webapp.config import BaseApplicationSettings
    BaseApplicationSettings.SQLALCHEMY_ENGINE_OPTIONS = {}
    from webapp import create_app

    app = create_app()
    app.config.update(TESTING=True)

    from webapp.extensions import db

    with app.app_context():
        db.create_all()

    yield app

    with app.app_context():
        db.session.remove()
        db.drop_all()

    sys.modules.pop("webapp.config", None)
    sys.modules.pop("webapp", None)
    for key, value in prev_env.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def test_scan_directory_handles_heic(tmp_path: Path) -> None:
    """HEICファイルがスキャン対象として検出されることを確認。"""

    heic_path = tmp_path / "sample.heic"
    Image.new("RGB", (12, 8), "blue").save(heic_path)

    scanned = scan_import_directory(str(tmp_path))

    assert str(heic_path) in scanned


def test_get_image_dimensions_for_heic(tmp_path: Path) -> None:
    """HEIC画像から寸法情報を取得できることを確認。"""

    heic_path = tmp_path / "dimensions.heic"
    Image.new("RGB", (64, 48), "green").save(heic_path)

    width, height, orientation = get_image_dimensions(str(heic_path))

    assert (width, height) == (64, 48)
    assert orientation in (None, 1)


def test_heic_dimension_fallback_when_plugin_unavailable(monkeypatch, tmp_path: Path) -> None:
    """HEIC読み込みが失敗してもフォールバックで寸法を取得できることを確認。"""

    heic_path = tmp_path / "fallback.heic"
    Image.new("RGB", (20, 10), "purple").save(heic_path)

    original_open = Image.open

    def _raising_open(path, *args, **kwargs):
        if str(path).endswith(".heic"):
            raise UnidentifiedImageError("mock failure")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Image, "open", _raising_open)

    width, height, orientation = get_image_dimensions(str(heic_path))
    assert (width, height) == (20, 10)
    assert orientation in (None, 1)

    exif = extract_exif_data(str(heic_path))
    assert isinstance(exif, dict)


def test_extract_exif_date_from_heic(monkeypatch, tmp_path: Path) -> None:
    """HEICのEXIFに含まれる撮影日時を抽出できることを確認。"""

    heic_path = tmp_path / "dated.heic"
    image = Image.new("RGB", (16, 16), "white")

    monkeypatch.setenv("BABEL_DEFAULT_TIMEZONE", "Asia/Tokyo")

    if hasattr(Image, "Exif"):
        exif = Image.Exif()
        exif[36867] = "2023:09:01 10:20:30"  # DateTimeOriginal
        image.save(heic_path, exif=exif)
    else:
        pytest.skip("Pillow does not provide Image.Exif helper")

    exif_data = extract_exif_data(str(heic_path))
    assert exif_data.get("DateTimeOriginal")

    shot_at = get_file_date_from_exif(exif_data)
    assert shot_at == datetime(2023, 9, 1, 1, 20, 30, tzinfo=timezone.utc)


def test_extract_exif_date_from_heic_with_offset(monkeypatch, tmp_path: Path) -> None:
    """オフセット情報がある場合はそれを優先してUTCへ変換する。"""

    heic_path = tmp_path / "dated_with_offset.heic"
    image = Image.new("RGB", (16, 16), "white")

    monkeypatch.setenv("BABEL_DEFAULT_TIMEZONE", "Asia/Tokyo")

    if hasattr(Image, "Exif"):
        exif = Image.Exif()
        exif[36867] = "2023:09:01 10:20:30"  # DateTimeOriginal
        exif[36881] = "+02:30"  # OffsetTimeOriginal
        image.save(heic_path, exif=exif)
    else:
        pytest.skip("Pillow does not provide Image.Exif helper")

    exif_data = extract_exif_data(str(heic_path))
    assert exif_data.get("DateTimeOriginal")
    assert exif_data.get("OffsetTimeOriginal") == "+02:30"

    shot_at = get_file_date_from_exif(exif_data)
    assert shot_at == datetime(2023, 9, 1, 7, 50, 30, tzinfo=timezone.utc)


def test_import_single_heic_file(local_import_app) -> None:
    """HEICファイルの取り込みが成功し、メタ情報が保存されることを確認。"""

    from core.models.photo_models import Media

    import_dir = Path(local_import_app.config["MEDIA_LOCAL_IMPORT_DIRECTORY"])
    originals_dir = Path(local_import_app.config["MEDIA_ORIGINALS_DIRECTORY"])

    heic_path = import_dir / "import_target.heic"
    Image.new("RGB", (32, 24), "red").save(heic_path)

    with local_import_app.app_context():
        result = import_single_file(str(heic_path), str(import_dir), str(originals_dir))

        assert result["success"] is True
        assert result["media_id"] is not None

        media = Media.query.get(result["media_id"])

        assert media is not None
        assert media.mime_type == "image/heic"
        assert media.width == 32
        assert media.height == 24

    stored_files = list(originals_dir.rglob("*.heic"))
    assert stored_files
