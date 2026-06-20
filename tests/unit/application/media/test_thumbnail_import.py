"""インポート時のサムネイル生成テスト."""

import os
from pathlib import Path

import pytest
from PIL import Image


@pytest.fixture
def app(tmp_path):
    originals = tmp_path / "originals"
    thumbs = tmp_path / "thumbs"
    play = tmp_path / "play"
    for d in (originals, thumbs, play):
        d.mkdir(parents=True, exist_ok=True)

    os.environ["SECRET_KEY"] = "test"
    os.environ["DATABASE_URI"] = f"sqlite:///{tmp_path / 'test.db'}"
    os.environ["MEDIA_ORIGINALS_DIRECTORY"] = str(originals)
    os.environ["MEDIA_THUMBNAILS_DIRECTORY"] = str(thumbs)
    os.environ["MEDIA_PLAYBACK_DIRECTORY"] = str(play)

    from webapp.config import BaseApplicationSettings

    BaseApplicationSettings.SQLALCHEMY_ENGINE_OPTIONS = {}
    from webapp import create_app

    app = create_app()
    app.config.update(
        TESTING=True,
        MEDIA_ORIGINALS_DIRECTORY=str(originals),
        MEDIA_THUMBNAILS_DIRECTORY=str(thumbs),
        MEDIA_PLAYBACK_DIRECTORY=str(play),
    )
    from webapp.extensions import db

    with app.app_context():
        db.create_all()
    yield app


def test_thumbnail_generation(app):
    """インポートされた画像からサムネイルが生成されることを検証する."""
    from core.tasks.picker_import import enqueue_thumbs_generate
    from core.models.photo_models import Media
    from webapp.extensions import db

    with app.app_context():
        orig_dir = Path(app.config["MEDIA_ORIGINALS_DIRECTORY"])
        thumbs_dir = Path(app.config["MEDIA_THUMBNAILS_DIRECTORY"])

        rel_path = "2025/08/28/test_import.jpg"
        test_file = orig_dir / rel_path
        test_file.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (2000, 1500), color=(255, 0, 0)).save(test_file)

        media = Media(
            google_media_id="test_import_123",
            account_id=1,
            local_rel_path=rel_path,
            hash_sha256="test_hash_123",
            bytes=test_file.stat().st_size,
            mime_type="image/jpeg",
            width=2000,
            height=1500,
            is_video=False,
        )
        db.session.add(media)
        db.session.commit()

        enqueue_thumbs_generate(media.id)

        # サムネイルファイルが少なくとも1つ作成されること
        generated = list(thumbs_dir.rglob("*.jpg"))
        assert generated, "サムネイルが1つも生成されていない"
