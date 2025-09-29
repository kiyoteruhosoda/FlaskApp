from __future__ import annotations

"""Thumbnail generation task for media items.

This module implements a condensed version of the specification in
``T-WKR-2``.  The implementation focuses on the essential control flow so that
works in tests without requiring a full Celery deployment or heavy multimedia
dependencies.  The worker is idempotent and supports both image and video
sources.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
import contextlib

from core.db import db
from core.utils import open_image_compat, register_heif_support

register_heif_support()

from PIL import Image, ImageOps

from core.models.photo_models import Media, MediaPlayback
from core.storage_paths import (
    ensure_directory,
    first_existing_storage_path,
)


PLAYBACK_NOT_READY_NOTES = "playback not ready"


class PlaybackNotReadyError(RuntimeError):
    """Raised when video playback assets are not ready for thumbnail generation."""

# Target thumbnail sizes (long side)
SIZES = [256, 512, 1024, 2048]
MIN_VIDEO_POSTER_LONG_SIDE = 720


@dataclass
class _SourceResolution:
    image: Image.Image
    rel_name: Path
    notes: str | None = None


# ---------------------------------------------------------------------------
# Result helpers
# ---------------------------------------------------------------------------


def _playback_not_ready(
    *, reason: str, extra: Optional[Dict[str, object]] = None
) -> Dict[str, object]:
    """Return a standard response when playback assets are not yet available."""

    blockers = {"reason": reason}
    if extra:
        blockers.update(extra)

    return {
        "ok": True,
        "generated": [],
        "skipped": SIZES.copy(),
        "notes": PLAYBACK_NOT_READY_NOTES,
        "paths": {},
        "retry_blockers": blockers,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _thumb_base_dir() -> Path:
    """Return thumbnail base directory creating it if necessary."""

    base = first_existing_storage_path("FPV_NAS_THUMBS_DIR")
    if not base:
        base = "/tmp/fpv_thumbs"
    return ensure_directory(base)


def _orig_dir() -> Path:
    base = first_existing_storage_path("FPV_NAS_ORIGINALS_DIR")
    if not base:
        base = "/tmp/fpv_orig"
    return Path(base)


def _play_dir() -> Path:
    base = first_existing_storage_path("FPV_NAS_PLAY_DIR")
    if not base:
        base = "/tmp/fpv_play"
    return Path(base)


def _replace_suffix(path: Path, suffix: str) -> Path:
    if path.suffix:
        return path.with_suffix(suffix)
    return path.with_name(path.name + suffix)


def _select_playback(media_id: int) -> MediaPlayback | None:
    """Return the newest completed playback prioritising the std1080p preset."""

    preferred = (
        MediaPlayback.query.filter_by(
            media_id=media_id, preset="std1080p", status="done"
        )
        .order_by(MediaPlayback.id.desc())
        .first()
    )
    if preferred:
        return preferred

    return (
        MediaPlayback.query.filter_by(media_id=media_id, status="done")
        .order_by(MediaPlayback.id.desc())
        .first()
    )


def _load_poster_image(pb: MediaPlayback) -> tuple[Image.Image, str] | None:
    """Return poster image and rel path if it can be loaded from disk."""

    if not pb.poster_rel_path:
        return None

    poster_path = _play_dir() / pb.poster_rel_path
    if not poster_path.exists():
        return None

    try:
        with Image.open(poster_path) as poster:
            poster = ImageOps.exif_transpose(poster)
            return poster.convert("RGB"), pb.poster_rel_path
    except OSError:
        return None


def _poster_long_side(poster: Image.Image | None) -> int:
    if not poster:
        return 0
    return max(poster.size)


def _extract_frame_from_video(video_path: Path, *, offset_seconds: float = 1.0) -> Image.Image | None:
    """Extract a frame from *video_path* using ``imageio`` if available."""

    try:  # pragma: no cover - optional dependency path
        import imageio.v2 as imageio  # type: ignore
    except Exception:  # pragma: no cover - optional dependency path
        return None

    try:
        reader = imageio.get_reader(str(video_path))
    except Exception:
        return None

    with contextlib.closing(reader):
        try:
            meta = reader.get_meta_data()
            fps = max(float(meta.get("fps", 1.0)), 0.001)
        except Exception:
            fps = 1.0

        frame_index = max(int(fps * offset_seconds), 0)
        try:
            frame = reader.get_data(frame_index)
        except Exception:
            try:
                frame = reader.get_data(0)
            except Exception:
                return None

    return Image.fromarray(frame)


def _attempt_frame_extraction(paths: Iterable[Tuple[Path, str]]) -> tuple[Image.Image, str] | None:
    """Return the first successfully extracted frame from *paths*."""

    for path, label in paths:
        if not path.exists():
            continue

        frame = _extract_frame_from_video(path)
        if frame:
            return frame, label

    return None


def _resolve_video_source(media: Media, rel_name: Path) -> tuple[_SourceResolution | None, Dict[str, object] | None]:
    """Resolve a base image for video thumbnails with graceful fallbacks."""

    pb = _select_playback(media.id)
    if not pb:
        return None, _playback_not_ready(
            reason="completed playback missing"
        )

    poster_result = _load_poster_image(pb)
    poster_img = poster_result[0] if poster_result else None
    candidate_paths: list[tuple[Path, str]] = []
    if pb.rel_path:
        candidate_paths.append((_play_dir() / pb.rel_path, "playback"))
    if media.local_rel_path:
        candidate_paths.append((_orig_dir() / media.local_rel_path, "original"))

    poster_quality = _poster_long_side(poster_img)
    if poster_img and poster_quality >= MIN_VIDEO_POSTER_LONG_SIDE:
        return _SourceResolution(
            image=poster_img,
            rel_name=_replace_suffix(rel_name, ".jpg"),
            notes=None,
        ), None

    frame_result = _attempt_frame_extraction(candidate_paths)
    if frame_result:
        frame, source_label = frame_result
        frame_img = ImageOps.exif_transpose(frame).convert("RGB")
        if _poster_long_side(frame_img) > poster_quality:
            note = f"frame extracted from {source_label}"
            if poster_img and poster_quality:
                note += f" (poster long side {poster_quality}px)"
            return _SourceResolution(
                image=frame_img,
                rel_name=_replace_suffix(rel_name, ".jpg"),
                notes=note,
            ), None

    if poster_img:
        note = None
        if poster_quality and poster_quality < MIN_VIDEO_POSTER_LONG_SIDE:
            note = (
                f"poster long side {poster_quality}px below threshold "
                f"{MIN_VIDEO_POSTER_LONG_SIDE}px"
            )
        return _SourceResolution(
            image=poster_img,
            rel_name=_replace_suffix(rel_name, ".jpg"),
            notes=note,
        ), None

    return None, _playback_not_ready(
        reason="unable to extract video frame",
        extra={"sources_checked": [label for _path, label in candidate_paths]},
    )


def _resolve_photo_source(media: Media, rel_name: Path) -> tuple[_SourceResolution | None, Dict[str, object] | None]:
    """Resolve a base image for photo thumbnails."""

    if not media.local_rel_path:
        return None, {
            "ok": False,
            "generated": [],
            "skipped": [],
            "notes": "source missing",
            "paths": {},
        }

    src_path = _orig_dir() / media.local_rel_path
    if not src_path.exists():
        return None, {
            "ok": False,
            "generated": [],
            "skipped": [],
            "notes": "source missing",
            "paths": {},
        }

    with open_image_compat(src_path) as opened:
        opened = ImageOps.exif_transpose(opened)
        has_alpha = opened.mode in ("RGBA", "LA") or (
            opened.mode == "P" and "transparency" in opened.info
        )
        img = opened.convert("RGBA" if has_alpha else "RGB")

    out_ext = ".png" if has_alpha else ".jpg"
    return _SourceResolution(
        image=img,
        rel_name=_replace_suffix(rel_name, out_ext),
        notes=None,
    ), None


def _resolve_source(media: Media, rel_name: Path) -> tuple[_SourceResolution | None, Dict[str, object] | None]:
    if media.is_video:
        return _resolve_video_source(media, rel_name)
    return _resolve_photo_source(media, rel_name)


# ---------------------------------------------------------------------------
# Main task implementation
# ---------------------------------------------------------------------------


def thumbs_generate(*, media_id: int, force: bool = False) -> Dict[str, object]:
    """Generate thumbnails for a media item.

    The return value is a JSON serialisable dictionary with ``generated`` and
    ``skipped`` size lists as described in the specification.
    """

    m = Media.query.get(media_id)
    if not m:
        return {
            "ok": False,
            "generated": [],
            "skipped": [],
            "notes": "not_found",
            "paths": {},
        }

    if m.is_deleted:
        # Deleted media are a successful no-op
        return {
            "ok": True,
            "generated": [],
            "skipped": SIZES.copy(),
            "notes": None,
            "paths": {},
        }

    base_dir = _thumb_base_dir()
    generated: List[int] = []
    skipped: List[int] = []
    notes: str | None = None
    paths: Dict[int, str] = {}

    # ------------------------------------------------------------------
    # Determine base image
    # ------------------------------------------------------------------
    base_rel = m.thumbnail_rel_path or m.local_rel_path
    if not base_rel:
        return {
            "ok": False,
            "generated": [],
            "skipped": [],
            "notes": "source missing",
            "paths": {},
        }

    rel_name = Path(base_rel)

    source, error_response = _resolve_source(m, rel_name)
    if error_response:
        return error_response
    assert source is not None

    img = source.image
    rel_name = source.rel_name
    notes = source.notes or notes

    # ------------------------------------------------------------------
    # Generate thumbnails for each size
    # ------------------------------------------------------------------
    for size in SIZES:
        dest = base_dir / str(size) / rel_name
        if dest.exists() and not force:
            skipped.append(size)
            paths[size] = dest.as_posix()
            continue

        long_side = max(img.size)
        if long_side < size:
            skipped.append(size)
            continue

        dest.parent.mkdir(parents=True, exist_ok=True)
        scale = size / float(long_side)
        new_size = (int(img.size[0] * scale), int(img.size[1] * scale))
        resized = img.resize(new_size, Image.Resampling.LANCZOS)
        tmp = dest.with_suffix(dest.suffix + ".tmp")
        if dest.suffix.lower() == ".jpg":
            resized.save(tmp, "JPEG", quality=85, progressive=True)
        else:
            resized.save(tmp, "PNG")
        tmp.replace(dest)
        generated.append(size)
        paths[size] = dest.as_posix()

    new_rel = rel_name.as_posix()
    if m.thumbnail_rel_path != new_rel:
        m.thumbnail_rel_path = new_rel
        db.session.add(m)
        db.session.commit()

    return {
        "ok": True,
        "generated": generated,
        "skipped": skipped,
        "notes": notes,
        "paths": paths,
    }
