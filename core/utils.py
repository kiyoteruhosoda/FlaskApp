"""Utility helpers for the application."""

import json
import logging
import importlib
import importlib.util
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Final, Iterator
from zoneinfo import ZoneInfo

from flask import current_app

from core.settings import settings
from PIL import Image, UnidentifiedImageError

_HEIF_PLUGIN_NAME: Final[str] = "pillow_heif"
_HEIF_REGISTERED: bool = False

_EXIF_OFFSET_TAGS: dict[str, tuple[str, ...]] = {
    "DateTimeOriginal": ("OffsetTimeOriginal", "OffsetTime"),
    "CreateDate": (
        "OffsetTimeDigitized",
        "OffsetTimeOriginal",
        "OffsetTime",
    ),
    "DateTimeDigitized": ("OffsetTimeDigitized", "OffsetTime"),
    "DateTime": ("OffsetTime",),
}


def register_heif_support() -> bool:
    """Register HEIF/HEIC format support if the Pillow plugin is available."""

    global _HEIF_REGISTERED
    if _HEIF_REGISTERED:
        return True

    spec = importlib.util.find_spec(_HEIF_PLUGIN_NAME)
    if spec is None:
        return False

    module = importlib.import_module(_HEIF_PLUGIN_NAME)
    register = getattr(module, "register_heif_opener", None)
    if callable(register):
        register()
        _HEIF_REGISTERED = True
        return True

    return False


@contextmanager
def open_image_compat(path: str | Path) -> Iterator[Image.Image]:
    """Open an image file handling HEIC/HEIF without Pillow plugin support.

    This helper first attempts to open the file via :func:`PIL.Image.open`.
    When Pillow cannot identify the file (for example because the HEIF plugin
    was not registered), it falls back to :mod:`pillow_heif` so that HEIC files
    can still be processed.  The returned image object is automatically closed
    when the context exits.
    """

    image_obj: Image.Image | None = None

    try:
        image_obj = Image.open(path)
    except UnidentifiedImageError:
        try:
            from pillow_heif import open_heif  # type: ignore
        except ImportError:
            raise

        heif_file = open_heif(str(path))
        image_obj = heif_file.to_pillow()
        # ``heif_file`` instances do not provide ``close`` and are managed by
        # the library, so we only manage the Pillow image here.

    try:
        yield image_obj
    finally:
        if image_obj is not None:
            try:
                image_obj.close()
            except Exception:
                pass


def greet(name: str) -> str:
    """Return a friendly greeting."""
    return f"Hello {name}"


def log_status_change(obj: Any, old: str | None, new: str) -> None:
    """Log a status transition for ``obj``.

    Parameters
    ----------
    obj:
        The model instance whose status changed.  Its class name and ``id``
        attribute (if present) are recorded.
    old:
        Previous status value.  May be ``None`` if unknown.
    new:
        New status value.
    """

    logger = getattr(current_app, "logger", logging.getLogger(__name__))
    logger.info(
        json.dumps(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "model": obj.__class__.__name__,
                "id": getattr(obj, "id", None),
                "from": old,
                "to": new,
            },
            ensure_ascii=False,
        ),
        extra={"event": "status.change"},
    )


def get_file_date_from_name(filename: str) -> datetime | None:
    """
    ファイル名から撮影日時を抽出
    対応フォーマット:
    - IMG_20240815_143052.jpg
    - 20240815_143052.jpg
    - VID_20240815_143052.mp4
    """
    import re
    
    # パターン1: IMG_YYYYMMDD_HHMMSS または VID_YYYYMMDD_HHMMSS
    pattern1 = r'(?:IMG_|VID_)?(\d{8})_(\d{6})'
    match = re.search(pattern1, filename)
    
    if match:
        date_str = match.group(1)  # YYYYMMDD
        time_str = match.group(2)  # HHMMSS
        
        try:
            dt = datetime.strptime(f"{date_str}{time_str}", "%Y%m%d%H%M%S")
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    
    # パターン2: YYYYMMDD_HHMMSS
    pattern2 = r'(\d{8})_(\d{6})'
    match = re.search(pattern2, filename)
    
    if match:
        date_str = match.group(1)  # YYYYMMDD
        time_str = match.group(2)  # HHMMSS
        
        try:
            dt = datetime.strptime(f"{date_str}{time_str}", "%Y%m%d%H%M%S")
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    
    return None


def _default_app_timezone() -> timezone:
    """Return the application's default timezone.

    The function prefers the Flask ``BABEL_DEFAULT_TIMEZONE`` configuration
    value when available and falls back to the corresponding environment
    variable.  If neither yields a valid zoneinfo identifier ``UTC`` is used.
    """

    tz_name = settings.babel_default_timezone

    if tz_name:
        try:
            return ZoneInfo(tz_name)
        except Exception:
            pass

    return timezone.utc


def _extract_offset_timezone(tag: str, exif_data: dict) -> timezone | None:
    """Return a timezone derived from EXIF offset tags if available.

    EXIF 2.31 introduces dedicated offset tags that accompany the primary
    timestamp fields.  When those are present we should respect their value
    instead of falling back to the application default timezone.
    """

    for offset_tag in _EXIF_OFFSET_TAGS.get(tag, ()):  # pragma: no branch
        if offset_tag not in exif_data:
            continue

        raw_value = exif_data[offset_tag]

        if isinstance(raw_value, bytes):
            try:
                offset_str = raw_value.decode("utf-8", errors="ignore")
            except Exception:
                continue
        else:
            offset_str = str(raw_value) if not isinstance(raw_value, str) else raw_value

        offset_str = offset_str.strip().strip("\x00")
        if not offset_str:
            continue

        if len(offset_str) == 6 and offset_str[3] == ":":
            normalized = offset_str[:3] + offset_str[4:]
        else:
            normalized = offset_str

        try:
            tz_info = datetime.strptime(normalized, "%z").tzinfo
        except ValueError:
            continue

        if tz_info is not None:
            return tz_info

    return None


def get_file_date_from_exif(exif_data: dict) -> datetime | None:
    """
    EXIFデータから撮影日時を抽出
    """
    if not exif_data:
        return None
    
    # 撮影日時のタグを確認（優先順位順）
    date_tags = ['DateTimeOriginal', 'CreateDate', 'DateTime', 'DateTimeDigitized']

    default_tz = _default_app_timezone()
    
    for tag in date_tags:
        if tag not in exif_data:
            continue

        raw_value = exif_data[tag]

        if isinstance(raw_value, bytes):
            # HEIC/HEIF などで EXIF がバイト列として提供される場合があるため、
            # UTF-8（ASCII 互換）でデコードして処理する。
            try:
                date_str = raw_value.decode("utf-8", errors="ignore")
            except Exception:
                continue
        else:
            date_str = str(raw_value) if not isinstance(raw_value, str) else raw_value

        date_str = date_str.strip().strip("\x00")
        if not date_str:
            continue

        # EXIF日時フォーマット: "YYYY:MM:DD HH:MM:SS"
        try:
            dt = datetime.strptime(date_str, "%Y:%m:%d %H:%M:%S")
            tz_info = _extract_offset_timezone(tag, exif_data) or default_tz
            localized = dt.replace(tzinfo=tz_info)
            return localized.astimezone(timezone.utc)
        except ValueError:
            pass

        # ISO8601 形式等にもフォールバックしておく。
        normalized = date_str.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(normalized)
        except ValueError:
            continue

        if dt.tzinfo is None:
            tz_info = _extract_offset_timezone(tag, exif_data) or default_tz
            dt = dt.replace(tzinfo=tz_info)
        return dt.astimezone(timezone.utc)

    return None
