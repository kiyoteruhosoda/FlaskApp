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
import os
from pathlib import Path
import shutil
import subprocess
from typing import Dict, List

from core.db import db
from core.models.photo_models import Media, MediaPlayback


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _orig_dir() -> Path:
    return Path(os.environ.get("FPV_NAS_ORIGINALS_DIR", "/tmp/fpv_orig"))


def _play_dir() -> Path:
    return Path(os.environ.get("FPV_NAS_PLAY_DIR", "/tmp/fpv_play"))


def _tmp_dir() -> Path:
    tmp = Path(os.environ.get("FPV_TMP_DIR", "/tmp/fpv_tmp"))
    tmp.mkdir(parents=True, exist_ok=True)
    return tmp


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
    shutil.move(str(tmp_out), dest_path)

    pb.width = width
    pb.height = height
    pb.v_codec = "h264"
    pb.a_codec = "aac"
    pb.v_bitrate_kbps = int(bitrate / 1000) if bitrate else None
    pb.duration_ms = int(duration * 1000)
    pb.status = "done"
    pb.updated_at = datetime.now(timezone.utc)
    m.has_playback = True
    db.session.commit()

    return {
        "ok": True,
        "duration_ms": pb.duration_ms,
        "width": width,
        "height": height,
        "note": None,
    }
