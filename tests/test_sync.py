import json
from datetime import datetime
from pathlib import Path
import json
from typing import List

from sqlalchemy import create_engine, event, insert, select, func

from fpv.sync import run_sync
from fpv.config import PhotoNestConfig
from fpv import google
from fpv.schema import metadata, google_account, job_sync, media, media_playback


def _setup_engine(with_account: bool = True):
    engine = create_engine("sqlite:///:memory:", future=True)

    @event.listens_for(engine, "connect")
    def _connect(dbapi_connection, connection_record):
        dbapi_connection.create_function(
            "UTC_TIMESTAMP", 0, lambda: datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        )

    metadata.create_all(engine)

    if with_account:
        with engine.begin() as conn:
            conn.execute(
                insert(google_account).values(
                    id=1,
                    account_email="test@example.com",
                    oauth_token_json="{}",
                    status="active",
                )
            )
    return engine


def _collect_events(output: str) -> List[str]:
    lines = [l for l in output.splitlines() if l.strip()]
    return [json.loads(l)["event"] for l in lines]


def test_run_sync_dry_run(monkeypatch, capsys, tmp_path):
    engine = _setup_engine(with_account=True)
    monkeypatch.setattr("fpv.sync.get_engine", lambda: engine)
    cfg = PhotoNestConfig(
        db_url="",
        nas_orig_dir=str(tmp_path / "orig"),
        nas_play_dir=str(tmp_path / "play"),
        nas_thumbs_dir=str(tmp_path / "thumb"),
        tmp_dir=str(tmp_path / "tmp"),
        transcode_workers=1,
        transcode_crf=20,
        max_retries=3,
        google_client_id="cid",
        google_client_secret="sec",
        oauth_key="x" * 32,
        strict_path_check=False,
    )
    monkeypatch.setattr("fpv.sync.PhotoNestConfig.from_env", lambda: cfg)
    code = run_sync()
    assert code == 0
    events = _collect_events(capsys.readouterr().out)
    assert events[0] == "sync.account.begin"
    assert events.count("sync.dryrun.item") == 3
    assert events[-1] == "sync.done"
    with engine.begin() as conn:
        row = conn.execute(select(job_sync.c.stats_json)).first()
        assert json.loads(row[0]) == {"listed": 3, "new": 0, "dup": 0, "failed": 0}


def test_run_sync_download_and_dedup(monkeypatch, tmp_path, capsys):
    engine = _setup_engine(with_account=True)
    monkeypatch.setattr("fpv.sync.get_engine", lambda: engine)

    cfg = PhotoNestConfig(
        db_url="",
        nas_orig_dir=str(tmp_path / "orig"),
        nas_play_dir=str(tmp_path / "play"),
        nas_thumbs_dir=str(tmp_path / "thumb"),
        tmp_dir=str(tmp_path / "tmp"),
        transcode_workers=1,
        transcode_crf=20,
        max_retries=3,
        google_client_id="cid",
        google_client_secret="sec",
        oauth_key="x" * 32,
        strict_path_check=False,
    )
    monkeypatch.setattr("fpv.sync.PhotoNestConfig.from_env", lambda: cfg)

    monkeypatch.setattr(google, "refresh_access_token", lambda enc, key, cid, cs: ("tok", {"expires_in": 3600}))

    def fake_list_media_items_once(token, page_size=50, page_token=None):
        return {
            "mediaItems": [
                {
                    "id": "1",
                    "mimeType": "image/jpeg",
                    "filename": "a.jpg",
                    "baseUrl": "http://img1",
                    "mediaMetadata": {
                        "creationTime": "2024-01-01T00:00:00Z",
                        "width": "10",
                        "height": "10",
                    },
                },
                {
                    "id": "2",
                    "mimeType": "image/jpeg",
                    "filename": "b.jpg",
                    "baseUrl": "http://img2",
                    "mediaMetadata": {
                        "creationTime": "2024-01-01T00:00:00Z",
                        "width": "10",
                        "height": "10",
                    },
                },
                {
                    "id": "3",
                    "mimeType": "video/mp4",
                    "filename": "c.mp4",
                    "baseUrl": "http://vid1",
                    "mediaMetadata": {
                        "creationTime": "2024-01-01T00:00:00Z",
                        "width": "10",
                        "height": "10",
                    },
                },
            ]
        }

    monkeypatch.setattr(google, "list_media_items_once", fake_list_media_items_once)

    def fake_download_to_tmp(url, tmp_dir: Path, timeout: float = 60.0):
        if "vid" in url:
            data = b"video"
            name = "video.tmp"
            ctype = "video/mp4"
        else:
            data = b"image"
            name = "image.tmp"
            ctype = "image/jpeg"
        tmp = Path(tmp_dir) / name
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_bytes(data)
        return tmp, len(data), ctype

    monkeypatch.setattr("fpv.sync.download_to_tmp", fake_download_to_tmp)

    code = run_sync(dry_run=False, max_pages=1)
    assert code == 0

    # two files saved (one image, one video)
    files = [p for p in (tmp_path / "orig").rglob("*") if p.is_file()]
    assert len(files) == 2

    with engine.begin() as conn:
        m_count = conn.execute(select(func.count()).select_from(media)).scalar()
        assert m_count == 2
        mp_count = conn.execute(select(func.count()).select_from(media_playback)).scalar()
        assert mp_count == 1
        row = conn.execute(select(job_sync.c.stats_json)).first()
        stats = json.loads(row[0])
        assert stats["listed"] == 3
        assert stats["new"] == 2
        assert stats["dup"] == 1
        assert stats["failed"] == 0
