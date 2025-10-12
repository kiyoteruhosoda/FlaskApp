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
import math
from pathlib import Path
import shutil
import subprocess
from typing import Any, Dict, List, Optional, cast

from core.db import db
from core.models.photo_models import Media, MediaPlayback
from core.storage_paths import ensure_directory, first_existing_storage_path
from core.logging_config import setup_task_logging
from core.settings import ApplicationSettings, settings
from .thumbs_generate import thumbs_generate

# transcode専用ロガーを取得（両方のログハンドラーが設定済み）
logger = setup_task_logging("celery.task.transcode")


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _orig_dir() -> Path:
    base = first_existing_storage_path("FPV_NAS_ORIGINALS_DIR")
    if not base:
        base = "/tmp/fpv_orig"
    return Path(base)


def _play_dir() -> Path:
    base = first_existing_storage_path("FPV_NAS_PLAY_DIR")
    if not base:
        base = "/tmp/fpv_play"
    return ensure_directory(base)


def _tmp_dir(*, config: ApplicationSettings = settings) -> Path:
    tmp = config.tmp_directory
    tmp.mkdir(parents=True, exist_ok=True)
    return tmp


def _summarise_ffmpeg_error(stderr: str) -> Optional[str]:
    """Extract a human readable summary line from *stderr* output."""

    if not stderr:
        return None

    candidates = [line.strip() for line in stderr.splitlines() if line.strip()]
    priority = ("not divisible", "error", "failed", "invalid")
    for keyword in priority:
        for line in reversed(candidates):
            if keyword in line.lower():
                return line

    if candidates:
        return candidates[-1]
    return None


def _normalise_rel_path(rel_path: Optional[str], *, suffix: Optional[str] = None) -> Optional[str]:
    """Return a sanitised POSIX-style relative path.

    The helper normalises path separators, removes empty/``.`` segments, and
    drops any ``..`` components.  When *suffix* is provided the returned path is
    forced to use that suffix irrespective of the original extension.
    """

    if not rel_path:
        return None

    normalised = rel_path.replace("\\", "/")
    candidate = Path(normalised)

    parts: List[str] = []
    parent_traversal = False
    for part in candidate.parts:
        if part in {"", "."}:
            continue
        if part == "..":
            parent_traversal = True
            continue
        parts.append(part)

    if not parts:
        return None

    cleaned = Path(*parts)
    if suffix:
        if cleaned.suffix:
            cleaned = cleaned.with_suffix(suffix)
        else:
            cleaned = cleaned.with_name(cleaned.name + suffix)

    result = cleaned.as_posix()

    if parent_traversal:
        logger.warning(
            "Relative path contained parent traversal and was sanitised",  # pragma: no cover - defensive logging
            extra={
                "event": "transcode.relpath.sanitised",
                "original": rel_path,
                "sanitised": result,
            },
        )

    return result


def _coerce_int(value: object) -> Optional[int]:
    """Best-effort conversion of *value* to ``int``."""

    if value is None:
        return None
    if isinstance(value, bool):  # pragma: no cover - defensive guard
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if math.isnan(value):  # pragma: no cover - defensive guard
            return None
        return int(value)
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return None
        lowered = cleaned.lower()
        if lowered in {"n/a", "na", "nan", "none", "null"}:
            return None
        try:
            if "." in cleaned:
                return int(float(cleaned))
            return int(cleaned)
        except ValueError:
            return None
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return None


def _coerce_duration_ms(value: object) -> Optional[int]:
    """Convert ffprobe duration field to milliseconds."""

    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(float(value) * 1000)
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned or cleaned.lower() in {"n/a", "na", "nan"}:
            return None
        try:
            return int(float(cleaned) * 1000)
        except ValueError:
            return None
    return None


def _poster_tmp_path(playback_id: int) -> Path:
    """Return a temporary path for poster generation."""

    return _tmp_dir() / f"pb_{playback_id}_poster.jpg"


def _poster_rel_path(playback: MediaPlayback) -> str:
    """Return poster relative path for a playback output."""

    cleaned_rel = _normalise_rel_path(playback.rel_path)
    base = Path(cleaned_rel) if cleaned_rel else Path(f"pb_{playback.id}")
    if base.suffix:
        poster = base.with_suffix(".jpg")
    else:
        poster = base.with_name(base.name + ".jpg")
    return poster.as_posix()


def _is_passthrough_candidate(media: Media, probe: Dict[str, Any]) -> bool:
    """Return ``True`` when *media* can be copied directly for playback."""

    suffix = Path(media.local_rel_path or "").suffix.lower()
    if suffix != ".mp4":
        return False

    fmt = (probe.get("format", {}) or {})
    format_name = str(fmt.get("format_name", "")).lower()
    if "mp4" not in format_name:
        return False

    streams: List[Dict[str, Any]] = list(probe.get("streams", []) or [])
    vstreams = [s for s in streams if (s.get("codec_type") or "").lower() == "video"]
    astreams = [s for s in streams if (s.get("codec_type") or "").lower() == "audio"]
    if not vstreams or not astreams:
        return False

    v = vstreams[0]
    a = astreams[0]
    vcodec = str(v.get("codec_name", "")).lower()
    acodec = str(a.get("codec_name", "")).lower()
    if vcodec != "h264":
        return False
    if acodec not in {"aac", "mp4a"}:
        return False

    try:
        width = int(v.get("width") or 0)
        height = int(v.get("height") or 0)
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return False

    if width <= 0 or height <= 0:
        return False

    if width > 1920 or height > 1080:
        return False

    return True


def _generate_poster(playback: MediaPlayback, video_path: Path) -> Optional[str]:
    """Generate a JPEG poster frame for *playback* returning the relative path."""

    poster_tmp = _poster_tmp_path(playback.id)
    poster_rel = _poster_rel_path(playback)
    poster_dest = _play_dir() / poster_rel
    poster_dest.parent.mkdir(parents=True, exist_ok=True)

    if shutil.which("ffmpeg") is None:
        logger.error(
            "ffmpeg not found; skipping poster generation for playback %s",
            playback.id,
            extra={
                "event": "transcode.poster.ffmpeg_missing",
                "playback_id": playback.id,
                "media_id": playback.media_id,
            },
        )
        return None

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
# Poster backfill utilities
# ---------------------------------------------------------------------------


def backfill_playback_posters(*, limit: Optional[int] = None) -> Dict[str, object]:
    """Generate posters for completed playbacks that pre-date poster support."""

    processed = 0
    updated = 0
    skipped = 0
    errors = 0

    query = (
        MediaPlayback.query.filter(
            MediaPlayback.status == "done",
            MediaPlayback.poster_rel_path.is_(None),
            MediaPlayback.rel_path.isnot(None),
        )
        .order_by(MediaPlayback.id.asc())
    )
    playbacks: List[MediaPlayback]
    if limit is not None:
        playbacks = query.limit(limit).all()
    else:
        playbacks = query.all()

    for pb in playbacks:
        processed += 1
        rel_path = _normalise_rel_path(pb.rel_path, suffix=".mp4")
        if not rel_path:
            skipped += 1
            continue

        if rel_path != pb.rel_path:
            pb.rel_path = rel_path

        video_path = _play_dir() / rel_path
        if not video_path.exists():
            skipped += 1
            logger.warning(
                "Playback file missing while backfilling poster",
                extra={
                    "event": "transcode.poster.backfill_missing",
                    "playback_id": pb.id,
                    "media_id": pb.media_id,
                    "video_path": str(video_path),
                },
            )
            continue

        poster_rel = _generate_poster(pb, video_path)
        if not poster_rel:
            errors += 1
            continue

        pb.poster_rel_path = poster_rel
        pb.updated_at = datetime.now(timezone.utc)
        updated += 1
        db.session.flush()

        try:
            thumbs_generate(media_id=pb.media_id, force=True)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "Thumbnail generation failed during poster backfill: %s",
                exc,
                extra={
                    "event": "transcode.poster.backfill_thumb_failed",
                    "playback_id": pb.id,
                    "media_id": pb.media_id,
                },
            )

    db.session.commit()

    return {
        "processed": processed,
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
        "notes": None,
    }


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

        rel_path = _normalise_rel_path(m.local_rel_path, suffix=".mp4")
        if not rel_path:
            rel_path = f"media_{m.id}.mp4"
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


def transcode_worker(*, media_playback_id: int, force: bool = False) -> Dict[str, object]:
    """Transcode a queued playback item using ffmpeg."""

    if force:
        logger.debug(
            "Force flag received by transcode_worker; proceeding with standard processing.",
            extra={"event": "transcode.force.flag", "media_playback_id": media_playback_id},
        )

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

    out_rel = _normalise_rel_path(pb.rel_path, suffix=".mp4")
    if not out_rel:
        out_rel = _normalise_rel_path(m.local_rel_path, suffix=".mp4")
    if not out_rel:
        out_rel = f"pb_{pb.id}.mp4"
    pb.rel_path = out_rel
    tmp_dir = _tmp_dir()
    tmp_out = tmp_dir / f"pb_{pb.id}.mp4"

    src_probe: Optional[Dict[str, Any]] = None
    try:
        src_probe = _probe(src_path)
    except Exception:  # pragma: no cover - best effort for passthrough detection
        src_probe = None

    passthrough = bool(src_probe and _is_passthrough_candidate(m, src_probe))

    if passthrough:
        try:
            shutil.copy2(src_path, tmp_out)
            logger.info(
                "MP4 passthrough copy completed for playback %s",
                pb.id,
                extra={
                    "event": "transcode.passthrough.copied",
                    "playback_id": pb.id,
                    "media_id": pb.media_id,
                    "source_path": str(src_path),
                    "temp_path": str(tmp_out),
                },
            )
        except Exception as exc:
            logger.warning(
                "MP4 passthrough copy failed for playback %s: %s",
                pb.id,
                exc,
                extra={
                    "event": "transcode.passthrough.copy_failed",
                    "playback_id": pb.id,
                    "media_id": pb.media_id,
                    "source_path": str(src_path),
                    "temp_path": str(tmp_out),
                },
                exc_info=True,
            )
            tmp_out.unlink(missing_ok=True)
            passthrough = False

    if not passthrough:
        crf = settings.transcode_crf
        video_filter = (
            "scale='min(1920,iw)':'min(1080,ih)':force_original_aspect_ratio=decrease,"
            "pad='ceil(iw/2)*2':'ceil(ih/2)*2'"
        )

        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(src_path),
            "-vf",
            video_filter,
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
                "stdout": proc.stdout,
            }
            error_summary = _summarise_ffmpeg_error(proc.stderr)
            if not error_summary:
                error_summary = f"ffmpeg exited with code {proc.returncode}"
            logger.error(
                f"FFmpeg変換失敗: playback_id={pb.id}, media_id={pb.media_id} - return_code={proc.returncode}",
                extra={
                    "event": "transcode.ffmpeg.failed",
                    "error_details": json.dumps(error_details),
                },
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
                "error": error_summary,
                "error_details": error_details,
            }

    info: Optional[Dict[str, Any]] = None
    probe_exc: Optional[Exception] = None
    try:
        info = _probe(tmp_out)
    except Exception as exc:  # pragma: no cover - defensive
        probe_exc = exc

    if info is None:
        if passthrough and src_probe:
            info = src_probe
            logger.info(
                "Fallback to source probe metadata for playback %s",
                pb.id,
                extra={
                    "event": "transcode.probe.fallback_source",
                    "playback_id": pb.id,
                    "media_id": pb.media_id,
                    "output_path": str(tmp_out),
                },
            )
        else:
            error_details = {
                "playback_id": pb.id,
                "media_id": pb.media_id,
                "output_path": str(tmp_out),
            }
            if probe_exc is not None:
                error_details.update(
                    error_type=type(probe_exc).__name__,
                    error_message=str(probe_exc),
                )
            logger.error(
                f"FFmpeg変換後のプローブ失敗: playback_id={pb.id}, media_id={pb.media_id} - {probe_exc}",
                extra={
                    "event": "transcode.probe.failed",
                    "error_details": json.dumps(error_details),
                },
                exc_info=True,
            )
            pb.status = "error"
            pb.error_msg = (str(probe_exc) if probe_exc else "probe_failed")[:1000]
            pb.updated_at = datetime.now(timezone.utc)
            db.session.commit()
            return {
                "ok": False,
                "duration_ms": 0,
                "width": 0,
                "height": 0,
                "note": "probe_error",
            }

    info = cast(Dict[str, Any], info)

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
    width = _coerce_int(v.get("width")) or (m.width or 0)
    height = _coerce_int(v.get("height")) or (m.height or 0)
    duration_ms_value = _coerce_duration_ms(info.get("format", {}).get("duration"))
    if duration_ms_value is None:
        duration_ms_value = m.duration_ms
    bitrate_bps = _coerce_int(info.get("format", {}).get("bit_rate"))

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
                "dest_path": str(dest_path),
                "passthrough": passthrough,
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

    if not dest_path.exists():
        error_details = {
            "playback_id": pb.id,
            "media_id": pb.media_id,
            "expected_path": str(dest_path),
            "passthrough": passthrough,
        }
        logger.error(
            f"再生ファイル配置確認失敗: playback_id={pb.id} - {dest_path} が存在しません",
            extra={
                "event": "transcode.file.missing_after_move",
                "error_details": json.dumps(error_details),
            },
        )
        pb.status = "error"
        pb.error_msg = "missing_output"
        pb.updated_at = datetime.now(timezone.utc)
        db.session.commit()
        return {
            "ok": False,
            "duration_ms": 0,
            "width": 0,
            "height": 0,
            "note": "missing_output",
        }

    playback_size = None
    try:
        playback_size = dest_path.stat().st_size
    except OSError:
        playback_size = None

    logger.info(
        f"再生ファイル配置確認済み: playback_id={pb.id} - path={dest_path} size={playback_size}",
        extra={
            "event": "transcode.file.verified",
            "playback_id": pb.id,
            "media_id": pb.media_id,
            "dest_path": str(dest_path),
            "size": playback_size,
        },
    )

    poster_rel = _generate_poster(pb, dest_path)

    poster_path = (_play_dir() / poster_rel) if poster_rel else None
    if poster_path and not poster_path.exists():
        logger.error(
            f"ポスター配置確認失敗: playback_id={pb.id} - {poster_path} が存在しません",
            extra={
                "event": "transcode.poster.missing_after_move",
                "playback_id": pb.id,
                "media_id": pb.media_id,
                "poster_path": str(poster_path),
            },
        )
        poster_rel = None
        poster_path = None
    elif poster_path:
        poster_size = None
        try:
            poster_size = poster_path.stat().st_size
        except OSError:
            poster_size = None
        logger.info(
            f"ポスター生成完了: playback_id={pb.id} - path={poster_path} size={poster_size}",
            extra={
                "event": "transcode.poster.saved",
                "playback_id": pb.id,
                "media_id": pb.media_id,
                "poster_path": str(poster_path),
                "size": poster_size,
            },
        )

    pb.width = width
    pb.height = height
    vcodec_name = str(v.get("codec_name") or "").lower()
    acodec_name = str(astreams[0].get("codec_name") or "").lower()
    if acodec_name == "mp4a":
        acodec_name = "aac"
    pb.v_codec = vcodec_name or "h264"
    pb.a_codec = acodec_name or "aac"
    pb.v_bitrate_kbps = int(bitrate_bps / 1000) if bitrate_bps else None
    pb.duration_ms = int(duration_ms_value) if duration_ms_value is not None else None
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

    note_value = "passthrough" if passthrough else None

    return {
        "ok": True,
        "duration_ms": pb.duration_ms,
        "width": width,
        "height": height,
        "note": note_value,
        "output_path": str(dest_path),
        "poster_path": str(poster_path) if poster_path else None,
    }
