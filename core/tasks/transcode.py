from __future__ import annotations

"""Video transcoding queue and worker tasks.

This module implements a lightweight approximation of specification
``T-WKR-3``.  It provides two callable functions that can be used in tests
without requiring a full Celery deployment:

``transcode_queue_scan``
    Scan the ``media`` table for video items lacking playback files and
    create/update :class:`MediaPlayback` rows with ``preset='std1080p'``.

``transcode_worker``
    Perform the actual ffmpeg based transcoding for a queued playback
    record.  The worker is intentionally compact but validates the output
    and updates the database in a manner compatible with the tests.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
from typing import Dict, List, Optional

from core.db import db
from core.models.photo_models import Media, MediaPlayback
from .thumbs_generate import thumbs_generate

# transcode専用ロガーを取得（両方のログハンドラーが設定済み）
logger = logging.getLogger('celery.task.transcode')

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _orig_dir() -> Path:
    return Path(os.environ.get("FPV_NAS_ORIGINALS_DIR", "/tmp/fpv_orig"))


def _play_dir() -> Path:
    return Path(
        os.environ.get("FPV_NAS_PLAY_CONTAINER_DIR")
        or os.environ.get("FPV_NAS_PLAY_DIR", "/tmp/fpv_play")
    )


def _tmp_dir() -> Path:
    tmp = Path(os.environ.get("FPV_TMP_DIR", "/tmp/fpv_tmp"))
    tmp.mkdir(parents=True, exist_ok=True)
    return tmp


def _poster_tmp_path(playback_id: int) -> Path:
    """Return a temporary path for poster generation."""

    return _tmp_dir() / f"pb_{playback_id}_poster.jpg"


def _poster_rel_path(playback: MediaPlayback) -> str:
    """Return poster relative path for a playback output."""

    base = Path(playback.rel_path) if playback.rel_path else Path(f"pb_{playback.id}")
    if base.suffix:
        poster = base.with_suffix(".jpg")
    else:
        poster = base.with_name(base.name + ".jpg")
    return poster.as_posix()


def _generate_poster(playback: MediaPlayback, video_path: Path) -> Optional[str]:
    """Generate a JPEG poster frame for *playback* returning the relative path."""

    poster_tmp = _poster_tmp_path(playback.id)
    poster_rel = _poster_rel_path(playback)
    poster_dest = _play_dir() / poster_rel
    poster_dest.parent.mkdir(parents=True, exist_ok=True)

    commands = [
        [
            "ffmpeg",
            "-y",
            "-ss",
            "00:00:01.000",
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            str(poster_tmp),
        ],
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            str(poster_tmp),
        ],
    ]

    for cmd in commands:
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode == 0 and poster_tmp.exists():
            break
    else:  # pragma: no cover - extremely unlikely when ffmpeg succeeds above
        logger.warning(
            "Poster generation failed for playback %s",
            playback.id,
            extra={
                "event": "transcode.poster.failed",
                "playback_id": playback.id,
                "media_id": playback.media_id,
            },
        )
        poster_tmp.unlink(missing_ok=True)
        return None

    try:
        shutil.move(str(poster_tmp), poster_dest)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(
            "Poster move failed for playback %s: %s",
            playback.id,
            exc,
            extra={
                "event": "transcode.poster.move_failed",
                "playback_id": playback.id,
                "media_id": playback.media_id,
            },
        )
        poster_tmp.unlink(missing_ok=True)
        return None

    return poster_rel


# ---------------------------------------------------------------------------
# Queue scan
# ---------------------------------------------------------------------------


def transcode_queue_scan() -> Dict[str, object]:
    """Detect media requiring playback generation.

    The function follows the contract described in the specification and
    returns a JSON serialisable dictionary with ``queued`` and ``skipped``
    counts.  Only minimal error handling is implemented as required for
    the unit tests.
    """

    queued = 0
    skipped = 0
    now = datetime.now(timezone.utc)

    medias: List[Media] = (
        Media.query.filter_by(is_video=True, has_playback=False, is_deleted=False)
        .order_by(Media.id.desc())
        .all()
    )

    for m in medias:
        src_path = _orig_dir() / m.local_rel_path
        if not src_path.exists():
            skipped += 1
            continue

        pb = (
            MediaPlayback.query.filter_by(media_id=m.id, preset="std1080p")
            .order_by(MediaPlayback.id.desc())
            .first()
        )
        if pb and pb.status in {"pending", "processing", "done"}:
            skipped += 1
            continue

        rel_path = str(Path(m.local_rel_path).with_suffix(".mp4"))
        if pb:
            pb.status = "pending"
            pb.rel_path = rel_path
            pb.error_msg = None
            pb.updated_at = now
        else:
            pb = MediaPlayback(
                media_id=m.id,
                preset="std1080p",
                rel_path=rel_path,
                status="pending",
                created_at=now,
                updated_at=now,
            )
            db.session.add(pb)
        queued += 1

    db.session.commit()
    return {"queued": queued, "skipped": skipped, "notes": None}


# ---------------------------------------------------------------------------
# Worker implementation
# ---------------------------------------------------------------------------


def _probe(path: Path) -> Dict[str, object]:
    """Return ffprobe information for *path* as a dictionary."""

    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_streams",
        "-show_format",
        "-of",
        "json",
        str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip())
    return json.loads(proc.stdout)


@dataclass
class _WorkResult:
    ok: bool
    duration_ms: int
    width: int
    height: int
    note: str | None = None


# --- main worker -----------------------------------------------------------


def transcode_worker(*, media_playback_id: int) -> Dict[str, object]:
    """Transcode a queued playback item using ffmpeg."""

    pb = MediaPlayback.query.get(media_playback_id)
    if not pb:
        return {
            "ok": False,
            "duration_ms": 0,
            "width": 0,
            "height": 0,
            "note": "not_found",
        }

    if pb.status == "done":
        return {
            "ok": True,
            "duration_ms": pb.duration_ms or 0,
            "width": pb.width or 0,
            "height": pb.height or 0,
            "note": "already_done",
        }

    if pb.status == "processing":
        return {
            "ok": False,
            "duration_ms": 0,
            "width": 0,
            "height": 0,
            "note": "already_running",
        }

    m = pb.media
    src_path = _orig_dir() / m.local_rel_path
    if not src_path.exists():
        error_details = {
            "playback_id": pb.id,
            "media_id": pb.media_id,
            "expected_path": str(src_path),
            "media_rel_path": m.local_rel_path
        }
        logger.error(
            f"変換対象ファイルが見つからない: playback_id={pb.id}, path={src_path}",
            extra={
                "event": "transcode.input.missing",
                "error_details": json.dumps(error_details)
            }
        )
        pb.status = "error"
        pb.error_msg = "missing_input"
        pb.updated_at = datetime.now(timezone.utc)
        db.session.commit()
        return {
            "ok": False,
            "duration_ms": 0,
            "width": 0,
            "height": 0,
            "note": "missing_input",
        }

    pb.status = "processing"
    pb.updated_at = datetime.now(timezone.utc)
    db.session.commit()

    out_rel = pb.rel_path or str(Path(m.local_rel_path).with_suffix(".mp4"))
    pb.rel_path = out_rel
    tmp_dir = _tmp_dir()
    tmp_out = tmp_dir / f"pb_{pb.id}.mp4"

    crf = int(os.environ.get("FPV_TRANSCODE_CRF", "20"))
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(src_path),
        "-vf",
        "scale='min(1920,iw)':'min(1080,ih)':force_original_aspect_ratio=decrease",
        "-c:v",
        "libx264",
        "-crf",
        str(crf),
        "-preset",
        "veryfast",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-ac",
        "2",
        "-movflags",
        "+faststart",
        str(tmp_out),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        error_details = {
            "playback_id": pb.id,
            "media_id": pb.media_id,
            "input_path": str(src_path),
            "output_path": str(tmp_out),
            "ffmpeg_command": " ".join(cmd),
            "return_code": proc.returncode,
            "stderr": proc.stderr,
            "stdout": proc.stdout
        }
        logger.error(
            f"FFmpeg変換失敗: playback_id={pb.id}, media_id={pb.media_id} - return_code={proc.returncode}",
            extra={
                "event": "transcode.ffmpeg.failed",
                "error_details": json.dumps(error_details)
            }
        )
        pb.status = "error"
        pb.error_msg = proc.stderr[-1000:]
        pb.updated_at = datetime.now(timezone.utc)
        db.session.commit()
        return {
            "ok": False,
            "duration_ms": 0,
            "width": 0,
            "height": 0,
            "note": "ffmpeg_error",
        }

    try:
        info = _probe(tmp_out)
    except Exception as exc:  # pragma: no cover - defensive
        error_details = {
            "playback_id": pb.id,
            "media_id": pb.media_id,
            "output_path": str(tmp_out),
            "error_type": type(exc).__name__,
            "error_message": str(exc)
        }
        logger.error(
            f"FFmpeg変換後のプローブ失敗: playback_id={pb.id}, media_id={pb.media_id} - {exc}",
            extra={
                "event": "transcode.probe.failed",
                "error_details": json.dumps(error_details)
            },
            exc_info=True
        )
        pb.status = "error"
        pb.error_msg = str(exc)[:1000]
        pb.updated_at = datetime.now(timezone.utc)
        db.session.commit()
        return {
            "ok": False,
            "duration_ms": 0,
            "width": 0,
            "height": 0,
            "note": "probe_error",
        }

    vstreams = [s for s in info.get("streams", []) if s.get("codec_type") == "video"]
    astreams = [s for s in info.get("streams", []) if s.get("codec_type") == "audio"]
    if not vstreams or not astreams:
        error_details = {
            "playback_id": pb.id,
            "media_id": pb.media_id,
            "output_path": str(tmp_out),
            "video_streams_count": len(vstreams),
            "audio_streams_count": len(astreams),
            "all_streams": info.get("streams", [])
        }
        logger.error(
            f"変換されたファイルに必要なストリームが不足: playback_id={pb.id}, video={len(vstreams)}, audio={len(astreams)}",
            extra={
                "event": "transcode.missing_stream",
                "error_details": json.dumps(error_details)
            }
        )
        pb.status = "error"
        pb.error_msg = "missing_stream"
        pb.updated_at = datetime.now(timezone.utc)
        db.session.commit()
        tmp_out.unlink(missing_ok=True)
        return {
            "ok": False,
            "duration_ms": 0,
            "width": 0,
            "height": 0,
            "note": "missing_stream",
        }

    v = vstreams[0]
    width = int(v.get("width", 0))
    height = int(v.get("height", 0))
    duration = float(info.get("format", {}).get("duration", 0.0))
    bitrate = int(info.get("format", {}).get("bit_rate", 0))

    dest_path = _play_dir() / out_rel
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.move(str(tmp_out), dest_path)
        logger.info(
            f"変換ファイル移動成功: playback_id={pb.id} - {tmp_out} -> {dest_path}",
            extra={
                "event": "transcode.file.moved",
                "playback_id": pb.id,
                "media_id": pb.media_id,
                "source_path": str(tmp_out),
                "dest_path": str(dest_path)
            }
        )
    except Exception as e:
        error_details = {
            "playback_id": pb.id,
            "media_id": pb.media_id,
            "source_path": str(tmp_out),
            "dest_path": str(dest_path),
            "error_type": type(e).__name__,
            "error_message": str(e)
        }
        logger.error(
            f"変換ファイル移動失敗: playback_id={pb.id} - {tmp_out} -> {dest_path} - {e}",
            extra={
                "event": "transcode.file.move.failed",
                "error_details": json.dumps(error_details)
            },
            exc_info=True
        )
        pb.status = "error"
        pb.error_msg = f"file_move_error: {str(e)}"
        pb.updated_at = datetime.now(timezone.utc)
        db.session.commit()
        tmp_out.unlink(missing_ok=True)
        return {
            "ok": False,
            "duration_ms": 0,
            "width": 0,
            "height": 0,
            "note": "file_move_error",
        }

    poster_rel = _generate_poster(pb, dest_path)

    pb.width = width
    pb.height = height
    pb.v_codec = "h264"
    pb.a_codec = "aac"
    pb.v_bitrate_kbps = int(bitrate / 1000) if bitrate else None
    pb.duration_ms = int(duration * 1000)
    pb.status = "done"
    pb.poster_rel_path = poster_rel
    pb.updated_at = datetime.now(timezone.utc)
    m.has_playback = True
    db.session.commit()

    if poster_rel:
        try:
            thumbs_generate(media_id=m.id, force=True)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "Thumbnail generation failed after playback %s: %s",
                pb.id,
                exc,
                extra={
                    "event": "transcode.poster.thumb_failed",
                    "playback_id": pb.id,
                    "media_id": pb.media_id,
                },
            )

    return {
        "ok": True,
        "duration_ms": pb.duration_ms,
        "width": width,
        "height": height,
        "note": None,
    }
