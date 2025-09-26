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
from typing import Dict, List
import os

from core.db import db
from core.utils import open_image_compat, register_heif_support

register_heif_support()

from PIL import Image, ImageOps

from core.models.photo_models import Media, MediaPlayback
from core.storage_paths import (
    ensure_directory,
    first_existing_storage_path,
)

# Target thumbnail sizes (long side)
SIZES = [256, 512, 1024, 2048]


@dataclass
class _ThumbResult:
    generated: List[int]
    skipped: List[int]
    notes: str | None = None


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

    def _replace_suffix(path: Path, suffix: str) -> Path:
        if path.suffix:
            return path.with_suffix(suffix)
        return path.with_name(path.name + suffix)

    if m.is_video:
        pb = (
            MediaPlayback.query.filter_by(
                media_id=m.id, preset="std1080p", status="done"
            )
            .order_by(MediaPlayback.id.desc())
            .first()
        )
        if not pb:
            return {
                "ok": True,
                "generated": [],
                "skipped": SIZES.copy(),
                "notes": "playback not ready",
                "paths": {},
            }

        if pb.poster_rel_path:
            poster_path = _play_dir() / pb.poster_rel_path
            if not poster_path.exists():
                return {
                    "ok": True,
                    "generated": [],
                    "skipped": SIZES.copy(),
                    "notes": "playback not ready",
                    "paths": {},
                }
            img = Image.open(poster_path)
            img = ImageOps.exif_transpose(img)
        else:  # pragma: no cover - optional dependency path
            video_path = _play_dir() / pb.rel_path
            try:  # Use imageio if available
                import imageio.v2 as imageio  # type: ignore

                reader = imageio.get_reader(str(video_path))
                meta = reader.get_meta_data()
                fps = meta.get("fps", 1)
                idx = int(fps * 1)
                try:
                    frame = reader.get_data(idx)
                except Exception:
                    frame = reader.get_data(0)
                img = Image.fromarray(frame)
            except Exception:
                return {
                    "ok": True,
                    "generated": [],
                    "skipped": SIZES.copy(),
                    "notes": "playback not ready",
                    "paths": {},
                }
        img = img.convert("RGB")
        out_ext = ".jpg"
        rel_name = _replace_suffix(rel_name, out_ext)
    else:
        src_path = _orig_dir() / m.local_rel_path
        if not src_path.exists():
            return {
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
        rel_name = _replace_suffix(rel_name, out_ext)

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
