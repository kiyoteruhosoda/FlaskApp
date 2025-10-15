#!/usr/bin/env python
"""
ローカルインポート機能のテスト用スクリプト
"""

import base64
import os
import sys
import shutil
import subprocess
from pathlib import Path
import tempfile
import zipfile
import pytest

# プロジェクトルートを追加
sys.path.insert(0, '/home/kyon/myproject')

from core.tasks.local_import import import_single_file, local_import_task, scan_import_directory


ffmpeg_missing = shutil.which("ffmpeg") is None


@pytest.fixture
def app(tmp_path):
    """Create a minimal app with temp dirs/database."""
    db_path = tmp_path / "test.db"
    tmp_dir = tmp_path / "tmp"
    orig_dir = tmp_path / "orig"
    play_dir = tmp_path / "play"
    thumbs_dir = tmp_path / "thumbs"
    import_dir = tmp_path / "import"
    tmp_dir.mkdir()
    orig_dir.mkdir()
    play_dir.mkdir()
    thumbs_dir.mkdir()
    import_dir.mkdir()

    env = {
        "SECRET_KEY": "test",
        "DATABASE_URI": f"sqlite:///{db_path}",
        "FPV_TMP_DIR": str(tmp_dir),
        "FPV_NAS_ORIGINALS_DIR": str(orig_dir),
        "FPV_NAS_PLAY_DIR": str(play_dir),
        "FPV_NAS_THUMBS_DIR": str(thumbs_dir),
        "LOCAL_IMPORT_DIR": str(import_dir),
        "FPV_DL_SIGN_KEY": base64.urlsafe_b64encode(b"1" * 32).decode(),
    }
    prev = {k: os.environ.get(k) for k in env}
    os.environ.update(env)

    import importlib
    import webapp.config as config_module
    importlib.reload(config_module)
    import webapp as webapp_module
    importlib.reload(webapp_module)
    from webapp.config import Config
    Config.SQLALCHEMY_ENGINE_OPTIONS = {}
    from webapp import create_app
    app = create_app()
    app.config.update(TESTING=True)
    from webapp.extensions import db
    with app.app_context():
        db.create_all()

    yield app
    
    del sys.modules["webapp.config"]
    del sys.modules["webapp"]
    for k, v in prev.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


@pytest.fixture
def db_session(app):
    """Database session fixture."""
    from webapp.extensions import db
    with app.app_context():
        yield db.session


@pytest.fixture
def temp_dir(tmp_path):
    """Temporary directory fixture."""
    return tmp_path


def _make_video(path: Path, size: str = "640x360", *, duration: str = "1") -> None:
    """Generate a small MP4 video file for testing.

    ffmpegが利用できない環境でもテストが実行できるように、
    フォールバックとしてダミーの動画ファイルを生成する。
    """

    path.parent.mkdir(parents=True, exist_ok=True)

    if ffmpeg_missing:
        # シンプルなヘッダー付きMP4っぽいデータを書き込む
        path.write_bytes(
            b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42mp41"
            + os.urandom(128)
        )
        return

    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"testsrc=size={size}:rate=24",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=1000:sample_rate=48000",
        "-t",
        duration,
        "-shortest",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        str(path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)

def create_test_files(import_dir: str) -> list:
    """テスト用のファイルを作成"""
    test_files = []
    
    # テスト画像ファイル（簡単なバイナリデータ）
    test_image_data = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xdb\x00\x00\x00\x00IEND\xaeB`\x82'
    
    # ファイル作成
    files_to_create = [
        ('20240815_143052.jpg', test_image_data),
        ('IMG_20240816_120000.jpg', test_image_data),
        ('VID_20240817_150000.mp4', b'dummy video data'),
        ('test_file.txt', b'not supported file'),  # サポート外拡張子
    ]
    
    for filename, data in files_to_create:
        file_path = os.path.join(import_dir, filename)
        with open(file_path, 'wb') as f:
            f.write(data)
        test_files.append(file_path)
        print(f"作成: {file_path}")
    
    return test_files

def test_scan_directory():
    """ディレクトリスキャンのテスト"""
    print("\n=== ディレクトリスキャンのテスト ===")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        test_files = create_test_files(temp_dir)
        
        # スキャン実行
        scanned_files = scan_import_directory(temp_dir)
        
        print(f"スキャン結果: {len(scanned_files)}件")
        for file in scanned_files:
            print(f"  - {os.path.basename(file)}")
        
        # サポート外ファイルが除外されていることを確認
        txt_files = [f for f in scanned_files if f.endswith('.txt')]
        assert len(txt_files) == 0, "txt ファイルは除外されるべき"
        
    print("✓ ディレクトリスキャンのテスト完了")


def test_scan_directory_extracts_zip(tmp_path):
    """ZIPファイル内のサポートファイルが展開されることをテスト"""
    import_dir = tmp_path

    png_data = (b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde'
                b'\x00\x00\x00\x0cIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xdb\x00\x00\x00\x00IEND\xaeB`\x82')

    file1 = import_dir / "1.png"
    file3 = import_dir / "3.png"
    file1.write_bytes(png_data)
    file3.write_bytes(png_data)

    zip_path = import_dir / "2.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("4.png", png_data)
        zf.writestr("nested/5.png", png_data)
        zf.writestr("6.txt", b"nope")

    scanned_files = scan_import_directory(str(import_dir))

    basenames = sorted(Path(path).name for path in scanned_files)
    assert basenames == ["1.png", "3.png", "4.png", "5.png"]

    assert not zip_path.exists(), "ZIPファイルは展開後に削除されるべき"

    for path in scanned_files:
        assert os.path.exists(path)

def test_local_import_task_with_session(app, db_session, temp_dir):
    """ローカルインポートタスクでPickerSessionとPickerSelectionが作成されることをテスト"""
    
    from core.models.picker_session import PickerSession
    from core.models.photo_models import PickerSelection
    
    # app fixtureで設定されたディレクトリを使用
    import_dir = Path(app.config['LOCAL_IMPORT_DIR'])
    originals_dir = Path(app.config['FPV_NAS_ORIGINALS_DIR'])
    
    # テスト用ファイルを作成
    test_video = import_dir / "test_video.mp4"
    test_image = import_dir / "test_image.jpg"
    
    # 簡単なテストファイルを作成
    test_video.write_text("dummy video content")
    
    # 簡単なJPEGファイルを作成（最小限のヘッダー）
    with open(test_image, 'wb') as f:
        f.write(b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb\x00C\x00')
    
    print(f"Found files: {list(import_dir.glob('*'))}")
    
    # Flaskアプリケーションコンテキスト内でタスクを実行
    with app.app_context():
        result = local_import_task()
        
    print(f"Import result: {result}")
    
    # セッションが作成されていることを確認
    assert result["session_id"] is not None
    
    session = PickerSession.query.filter_by(session_id=result["session_id"]).first()
    assert session is not None
    assert session.status in ["processing", "completed", "imported"]
    
    # PickerSelectionレコードが作成されていることを確認
    selections = PickerSelection.query.filter_by(session_id=session.id).all()
    print(f"Created selections: {len(selections)}")
    
    # 少なくとも1つのファイルが処理されていることを確認
    assert len(selections) > 0
    
    # ローカルファイル情報が正しく設定されていることを確認
    for selection in selections:
        assert selection.local_filename is not None
        assert selection.local_file_path is not None
        assert selection.google_media_id is not None


def test_import_single_file_video_recoverable_failure(app, monkeypatch):
    """セッション経由の取り込みでは ffmpeg 不足を警告として扱う。"""

    import_dir = Path(app.config["LOCAL_IMPORT_DIR"])
    originals_dir = Path(app.config["FPV_NAS_ORIGINALS_DIR"])

    test_video = import_dir / "recoverable.mp4"
    test_video.write_text("dummy video content")

    from core.tasks import media_post_processing

    def fake_enqueue(*args, **kwargs):
        return {"ok": False, "note": "ffmpeg_missing"}

    monkeypatch.setattr(media_post_processing, "enqueue_media_playback", fake_enqueue)

    with app.app_context():
        result = import_single_file(
            str(test_video), str(import_dir), str(originals_dir), session_id="local_import_test"
        )

    assert result["success"] is True
    assert any(
        "ffmpeg_missing" in warning for warning in result.get("warnings", [])
    )
    assert not test_video.exists()


def test_local_import_video_generates_playback_from_originals(app, monkeypatch):
    """動画取り込み時にオリジナル格納先からPlaybackが生成されることを検証。"""

    from core.models.photo_models import Media, MediaPlayback
    from core.tasks import media_post_processing, transcode as transcode_module

    import_dir = Path(app.config["LOCAL_IMPORT_DIR"])
    originals_dir = Path(app.config["FPV_NAS_ORIGINALS_DIR"])
    play_dir = Path(app.config["FPV_NAS_PLAY_DIR"])
    tmp_dir = Path(os.environ["FPV_TMP_DIR"])

    for child in import_dir.iterdir():
        if child.is_file():
            child.unlink()

    src_video = import_dir / "import_test.mp4"
    _make_video(src_video)
    assert src_video.exists()

    originals_root = originals_dir.resolve()
    tmp_root = tmp_dir.resolve()
    probe_called_paths: list[Path] = []

    def wrapped_probe(path: Path):
        resolved = path.resolve()
        try:
            resolved.relative_to(originals_root)
        except ValueError:
            try:
                resolved.relative_to(tmp_root)
            except ValueError:
                pytest.fail(f"unexpected probe path: {resolved}")
        else:
            probe_called_paths.append(resolved)

        return {
            "format": {
                "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
                "duration": "1.5",
                "bit_rate": "900000",
            },
            "streams": [
                {"codec_type": "video", "codec_name": "h264", "width": 640, "height": 360},
                {"codec_type": "audio", "codec_name": "aac", "codec_long_name": "AAC"},
            ],
        }

    monkeypatch.setattr(transcode_module, "_probe", wrapped_probe)

    def fake_enqueue_media_playback(media_id: int, **kwargs):
        from webapp.extensions import db

        pb = MediaPlayback.query.filter_by(media_id=media_id, preset="std1080p").first()
        if not pb:
            media = Media.query.get(media_id)
            assert media is not None
            rel_path = str(Path(media.local_rel_path).with_suffix(".mp4"))
            pb = MediaPlayback(media_id=media_id, preset="std1080p", rel_path=rel_path, status="pending")
            db.session.add(pb)
            db.session.commit()

        if pb.status in {"done", "processing"}:
            return {"ok": pb.status == "done", "note": f"already_{pb.status}", "playback_status": pb.status}

        result = transcode_module.transcode_worker(media_playback_id=pb.id)
        db.session.refresh(pb)
        return result

    monkeypatch.setattr(media_post_processing, "enqueue_media_playback", fake_enqueue_media_playback)

    with app.app_context():
        result = local_import_task()
        assert result["success"] >= 1

        media_records = Media.query.all()
        assert len(media_records) == 1
        media = media_records[0]
        playback_records = MediaPlayback.query.filter_by(media_id=media.id).all()
        assert len(playback_records) == 1
        playback = playback_records[0]

        original_path = originals_dir / media.local_rel_path
        playback_path = play_dir / playback.rel_path

        assert original_path.exists()
        assert playback_path.exists()
        assert playback.status == "done"

    assert not src_video.exists()
    assert any(p.is_relative_to(originals_root) for p in probe_called_paths)


def test_local_import_duplicate_sets_google_media_id(app):
    """重複検出時でも Selection に media リンク情報が保存されることを確認"""

    from features.photonest.application.local_import.queue import LocalImportQueueProcessor
    from core.models.picker_session import PickerSession
    from core.models.photo_models import Media, MediaItem, PickerSelection
    from webapp.extensions import db

    class DummyLogger:
        def info(self, *args, **kwargs):
            pass

        def warning(self, *args, **kwargs):
            pass

        def error(self, *args, **kwargs):
            pass

        def commit_with_error_logging(self, *args, **kwargs):
            pass

    class DummyImporter:
        def __init__(self, media):
            self._media = media

        def import_file(self, *args, **kwargs):
            return {
                "success": False,
                "status": "duplicate",
                "reason": "Duplicate file detected",
                "media_id": self._media.id,
                "media_google_id": self._media.google_media_id,
            }

    with app.app_context():
        session = PickerSession(session_id="local-dup-test", status="processing")
        db.session.add(session)
        db.session.commit()

        media_item = MediaItem(id="existing-media", type="PHOTO", filename="dup.jpg")
        media = Media(google_media_id="existing-media", filename="dup.jpg", source_type="local")
        db.session.add_all([media_item, media])
        db.session.commit()

        import_dir = Path(app.config["LOCAL_IMPORT_DIR"])
        originals_dir = app.config["FPV_NAS_ORIGINALS_DIR"]
        file_path = import_dir / "dup.jpg"
        file_path.write_bytes(b"dummy")

        selection = PickerSelection(
            session_id=session.id,
            status="enqueued",
            local_file_path=str(file_path),
            local_filename="dup.jpg",
            attempts=0,
        )
        db.session.add(selection)
        db.session.commit()

        processor = LocalImportQueueProcessor(
            db=db,
            logger=DummyLogger(),
            importer=DummyImporter(media),
            cancel_requested=lambda _session, task_instance=None: False,
        )

        result = {"details": [], "success": 0, "failed": 0, "skipped": 0, "errors": [], "processed": 0}
        processed = processor.process(
            session,
            import_dir=str(import_dir),
            originals_dir=originals_dir,
            result=result,
            active_session_id=session.session_id,
            celery_task_id=None,
            duplicate_regeneration="regenerate",
        )

        assert processed == 1
        updated = db.session.get(PickerSelection, selection.id)
        assert updated.status == "dup"
        assert updated.google_media_id == media.google_media_id


if __name__ == "__main__":
    print("ローカルインポート機能のテスト")
    print("=" * 50)
    
    test_scan_directory()
    
    print("\n" + "=" * 50)
    print("すべてのテストが完了しました！")
    print("\n使用方法:")
    print("1. 環境変数 LOCAL_IMPORT_DIR に取り込み元ディレクトリを設定")
    print("2. 環境変数 FPV_NAS_ORIGINALS_DIR に保存先ディレクトリを設定")
    print("3. Web管理画面 (/photo-view/settings) からインポート実行")
    print("4. または Celery タスクから実行: local_import_task_celery.delay()")
