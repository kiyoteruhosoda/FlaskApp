"""`rebuild_media_from_originals`（originals 直接再構築）のテスト。"""
import os
from pathlib import Path

import pytest
from PIL import Image

from shared.kernel.database.db import db


@pytest.fixture
def app(tmp_path):
    os.environ["SECRET_KEY"] = "test"
    os.environ["DATABASE_URI"] = f"sqlite:///{tmp_path / 'test.db'}"
    os.environ["GOOGLE_CLIENT_ID"] = "cid"
    os.environ["GOOGLE_CLIENT_SECRET"] = "sec"
    from presentation.web.bootstrap.config import BaseApplicationSettings

    BaseApplicationSettings.SQLALCHEMY_ENGINE_OPTIONS = {}
    from presentation.web import create_app

    app = create_app()
    app.config.update(TESTING=True)
    with app.app_context():
        db.create_all()
    yield app


def _make_jpeg(path: Path, color) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (64, 64), color).save(path, format="JPEG")


@pytest.fixture
def originals(tmp_path):
    root = tmp_path / "originals"
    _make_jpeg(root / "2025/01/01/a.jpg", (200, 10, 10))
    _make_jpeg(root / "2025/01/02/b.jpg", (10, 200, 10))
    (root / "notes.txt").write_text("ignore me")  # 非対応拡張子は無視
    return root


def test_creates_media_for_each_original(app, originals):
    from bounded_contexts.photonest.tasks.local_import import rebuild_media_from_originals
    from bounded_contexts.photonest.infrastructure.photo_models import Media

    with app.app_context():
        stats = rebuild_media_from_originals(originals_dir=str(originals))
        assert stats["scanned"] == 2  # txt は除外
        assert stats["created"] == 2
        assert stats["errors"] == 0

        rels = {m.local_rel_path for m in Media.query.all()}
        assert rels == {"2025/01/01/a.jpg", "2025/01/02/b.jpg"}
        # メタデータが入っていること
        m = Media.query.filter_by(local_rel_path="2025/01/01/a.jpg").first()
        assert m.hash_sha256 and len(m.hash_sha256) == 64
        assert m.width == 64 and m.height == 64
        assert m.source_type == "local" and m.google_media_id is None


def test_idempotent_on_rerun(app, originals):
    from bounded_contexts.photonest.tasks.local_import import rebuild_media_from_originals
    from bounded_contexts.photonest.infrastructure.photo_models import Media

    with app.app_context():
        rebuild_media_from_originals(originals_dir=str(originals))
        stats = rebuild_media_from_originals(originals_dir=str(originals))
        assert stats["created"] == 0
        assert stats["skipped"] == 2
        assert Media.query.count() == 2


def test_dry_run_makes_no_changes(app, originals):
    from bounded_contexts.photonest.tasks.local_import import rebuild_media_from_originals
    from bounded_contexts.photonest.infrastructure.photo_models import Media

    with app.app_context():
        stats = rebuild_media_from_originals(originals_dir=str(originals), dry_run=True)
        assert stats["created"] == 2
        assert Media.query.count() == 0


def test_missing_root_returns_zero(app, tmp_path):
    from bounded_contexts.photonest.tasks.local_import import rebuild_media_from_originals

    with app.app_context():
        stats = rebuild_media_from_originals(originals_dir=str(tmp_path / "nope"))
        assert stats == {
            "scanned": 0,
            "created": 0,
            "skipped": 0,
            "refreshed": 0,
            "errors": 0,
        }
