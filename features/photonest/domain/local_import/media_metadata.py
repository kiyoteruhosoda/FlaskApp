"""ローカルインポートで利用するメディアメタデータ関連のユーティリティ。"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import math
import statistics
import subprocess
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from PIL import Image
from PIL.ExifTags import TAGS

from core.utils import open_image_compat, register_heif_support

logger = logging.getLogger(__name__)

register_heif_support()

try:  # Pillow 9.1+ provides the Resampling enum
    _RESAMPLE_LANCZOS = Image.Resampling.LANCZOS  # type: ignore[attr-defined]
except AttributeError:  # pragma: no cover - fallback for older Pillow
    _RESAMPLE_LANCZOS = Image.LANCZOS  # type: ignore[attr-defined]


def calculate_file_hash(file_path: str) -> str:
    """ファイルのSHA-256ハッシュを計算"""

    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def get_image_dimensions(file_path: str) -> Tuple[Optional[int], Optional[int], Optional[int]]:
    """画像の幅、高さ、向きを取得"""

    try:
        with open_image_compat(file_path) as img:
            width, height = img.size

            # EXIF orientationを取得
            orientation = None
            exif_dict = {}

            getexif = getattr(img, "getexif", None)
            if callable(getexif):
                try:
                    exif = getexif()
                except Exception:
                    exif = None
                if exif:
                    exif_dict = dict(exif.items())

            if not exif_dict and hasattr(img, "_getexif"):
                try:
                    raw = img._getexif()
                    if raw:
                        exif_dict = raw
                except Exception:
                    exif_dict = {}

            if not exif_dict:
                exif_bytes = (getattr(img, "info", {}) or {}).get("exif")
                if isinstance(exif_bytes, (bytes, bytearray)) and hasattr(Image, "Exif"):
                    try:
                        exif_reader = Image.Exif()
                        exif_reader.load(exif_bytes)
                        exif_dict = dict(exif_reader.items())
                    except Exception:
                        exif_dict = {}

            for tag, value in exif_dict.items():
                if TAGS.get(tag) == "Orientation":
                    orientation = value
                    break

            return width, height, orientation
    except Exception:
        return None, None, None


def extract_exif_data(file_path: str) -> Dict:
    """EXIFデータを抽出"""

    exif_data = {}
    try:
        with open_image_compat(file_path) as img:
            exif_dict = {}

            getexif = getattr(img, "getexif", None)
            if callable(getexif):
                try:
                    exif = getexif()
                except Exception:
                    exif = None
                if exif:
                    exif_dict = dict(exif.items())

            if not exif_dict and hasattr(img, "_getexif"):
                try:
                    raw = img._getexif()
                    if raw:
                        exif_dict = raw
                except Exception:
                    exif_dict = {}

            if not exif_dict:
                exif_bytes = (getattr(img, "info", {}) or {}).get("exif")
                if isinstance(exif_bytes, (bytes, bytearray)) and hasattr(Image, "Exif"):
                    try:
                        exif_reader = Image.Exif()
                        exif_reader.load(exif_bytes)
                        exif_dict = dict(exif_reader.items())
                    except Exception:
                        exif_dict = {}

            if exif_dict:
                for tag, value in exif_dict.items():
                    decoded_tag = TAGS.get(tag, tag)
                    exif_data[decoded_tag] = value

    except Exception:
        return {}

    return exif_data


def _parse_ffprobe_datetime(raw: str) -> Optional[datetime]:
    if not raw:
        return None

    normalized = raw.strip()

    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"

    if len(normalized) > 5 and normalized[-5] in {"+", "-"} and normalized[-3] != ":":
        normalized = f"{normalized[:-2]}:{normalized[-2:]}"

    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        try:
            dt = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)

    return dt


def parse_ffprobe_datetime(raw: str) -> Optional[datetime]:
    """ffprobe文字列をUTCのdatetimeへ正規化する公開関数。"""

    return _parse_ffprobe_datetime(raw)


def extract_video_metadata(file_path: str) -> Dict:
    """動画ファイルからメタデータを抽出（ffprobeを使用）"""

    metadata: Dict[str, Any] = {}

    def _assign_shot_at(candidate: Any, source_key: str) -> bool:
        if not candidate:
            return False

        parsed = _parse_ffprobe_datetime(str(candidate))
        if not parsed:
            return False

        metadata["shot_at"] = parsed
        metadata["shot_at_raw"] = str(candidate)
        metadata.setdefault("shot_at_source", source_key)

        if source_key == "creation_time":
            metadata["creation_time"] = str(candidate)
        elif (
            source_key == "com.apple.quicktime.creationdate"
            and "creation_time" not in metadata
        ):
            metadata["creation_time"] = str(candidate)

        return True

    try:
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(file_path),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode == 0:
            info = json.loads(proc.stdout)

            # ビデオストリーム情報を取得
            streams = info.get("streams", [])
            video_streams = [s for s in streams if s.get("codec_type") == "video"]
            if video_streams:
                v_stream = video_streams[0]
                # FPSを取得
                if "r_frame_rate" in v_stream:
                    fps_str = v_stream["r_frame_rate"]
                    if "/" in fps_str:
                        num, den = fps_str.split("/")
                        if den != "0":
                            metadata["fps"] = float(num) / float(den)
                    else:
                        metadata["fps"] = float(fps_str)

                # 幅・高さを取得
                metadata["width"] = v_stream.get("width")
                metadata["height"] = v_stream.get("height")

                # ストリームタグから作成日時を確認
                stream_tags = v_stream.get("tags") or {}
                stream_creation_time = stream_tags.get("creation_time")
                if stream_creation_time:
                    metadata["stream_creation_time"] = stream_creation_time

                for key in ("creation_time", "com.apple.quicktime.creationdate", "date"):
                    if _assign_shot_at(stream_tags.get(key), key):
                        break

                if (
                    stream_creation_time
                    and "creation_time" not in metadata
                ):
                    metadata["creation_time"] = stream_creation_time

            # フォーマット情報から時間を取得
            format_info = info.get("format", {})
            if "duration" in format_info:
                metadata["duration_ms"] = int(float(format_info["duration"]) * 1000)

            # フォーマットタグに作成日時が含まれていれば利用
            format_tags = format_info.get("tags") or {}
            if "shot_at" not in metadata:
                for key in ("creation_time", "com.apple.quicktime.creationdate", "date"):
                    if _assign_shot_at(format_tags.get(key), key):
                        break

    except (subprocess.CalledProcessError, FileNotFoundError, json.JSONDecodeError, ValueError):
        # ffprobeが使えない場合やエラーの場合は空のメタデータを返す
        pass

    return metadata


def _dct_2d(values: list[list[float]]) -> list[list[float]]:
    rows = len(values)
    cols = len(values[0]) if values else 0
    if rows == 0 or cols == 0:
        return []

    cos_rows = [
        [math.cos(math.pi * (2 * i + 1) * u / (2 * rows)) for i in range(rows)]
        for u in range(rows)
    ]
    cos_cols = [
        [math.cos(math.pi * (2 * j + 1) * v / (2 * cols)) for j in range(cols)]
        for v in range(cols)
    ]

    result: list[list[float]] = [[0.0 for _ in range(cols)] for _ in range(rows)]
    for u in range(rows):
        alpha_u = math.sqrt(1.0 / rows) if u == 0 else math.sqrt(2.0 / rows)
        for v in range(cols):
            alpha_v = math.sqrt(1.0 / cols) if v == 0 else math.sqrt(2.0 / cols)
            total = 0.0
            for i in range(rows):
                row_cos = cos_rows[u][i]
                for j in range(cols):
                    total += values[i][j] * row_cos * cos_cols[v][j]
            result[u][v] = alpha_u * alpha_v * total
    return result


def _phash_from_image(image: Image.Image) -> Optional[str]:
    try:
        resized = image.convert("L").resize((32, 32), resample=_RESAMPLE_LANCZOS)
    except Exception:  # pragma: no cover - unexpected image errors
        return None

    try:
        pixels = list(resized.getdata())
    finally:
        resized.close()

    matrix = [
        [float(pixels[row * 32 + col]) for col in range(32)] for row in range(32)
    ]
    dct_matrix = _dct_2d(matrix)
    if len(dct_matrix) < 8:
        return None

    top_left = [row[:8] for row in dct_matrix[:8]]
    coefficients = [value for row in top_left for value in row]
    if not coefficients:
        return None

    if len(coefficients) > 1:
        reference = statistics.median(coefficients[1:])
    else:
        reference = coefficients[0]

    bits = 0
    for value in coefficients:
        bits = (bits << 1) | (1 if value >= reference else 0)

    return f"{bits:016x}"


def _extract_video_frame(file_path: str, sample_time: float) -> Optional[Image.Image]:
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{sample_time:.3f}",
        "-i",
        str(file_path),
        "-vframes",
        "1",
        "-f",
        "image2pipe",
        "-vcodec",
        "png",
        "-",
    ]

    try:
        proc = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except FileNotFoundError:  # pragma: no cover - ffmpeg absent in environment
        logger.warning("ffmpeg が見つからないため動画フレームの抽出に失敗しました: %s", file_path)
        return None

    if proc.returncode != 0 or not proc.stdout:
        logger.warning(
            "ffmpeg による動画フレーム抽出に失敗しました (returncode=%s, stderr=%s): %s",
            proc.returncode,
            proc.stderr.decode("utf-8", errors="ignore") if proc.stderr else "",
            file_path,
        )
        return None

    buffer = io.BytesIO(proc.stdout)
    try:
        image = Image.open(buffer)
        image.load()
        return image
    except Exception as exc:  # pragma: no cover - corrupt frame output
        logger.warning(
            "抽出した動画フレームのデコードに失敗しました (%s): %s",
            exc,
            file_path,
            exc_info=True,
        )
        return None
    finally:
        buffer.close()


def calculate_perceptual_hash(
    file_path: str,
    *,
    is_video: bool,
    duration_ms: Optional[int],
) -> Optional[str]:
    """pHash を計算して16進文字列として返す。"""

    if is_video:
        duration_seconds = (duration_ms or 0) / 1000.0
        if duration_seconds <= 0:
            duration_seconds = 0.0
        sample_time = min(10.0, duration_seconds / 2 if duration_seconds else 0.0)
        frame = _extract_video_frame(file_path, sample_time)
        if frame is None:
            logger.warning("動画の pHash 計算に必要なフレーム取得に失敗しました: %s", file_path)
            return None
        try:
            return _phash_from_image(frame)
        finally:
            frame.close()

    try:
        with open_image_compat(file_path) as image:
            return _phash_from_image(image)
    except Exception as exc:  # pragma: no cover - unexpected I/O errors
        logger.warning(
            "画像の pHash 計算に失敗しました (%s): %s",
            exc,
            file_path,
            exc_info=True,
        )
        return None


def generate_filename(shot_at: datetime, file_extension: str, file_hash: str) -> str:
    """
    ファイル名を生成
    フォーマット: YYYYMMDD_HHMMSS_local_hash8.ext
    """

    date_str = shot_at.strftime("%Y%m%d_%H%M%S")
    hash8 = file_hash[:8]
    return f"{date_str}_local_{hash8}{file_extension}"


def get_relative_path(shot_at: datetime, filename: str) -> str:
    """相対パスを生成 (YYYY/MM/DD/filename)"""

    year = shot_at.strftime("%Y")
    month = shot_at.strftime("%m")
    day = shot_at.strftime("%d")
    return f"{year}/{month}/{day}/{filename}"


__all__ = [
    "calculate_file_hash",
    "calculate_perceptual_hash",
    "extract_exif_data",
    "extract_video_metadata",
    "generate_filename",
    "get_image_dimensions",
    "get_relative_path",
    "parse_ffprobe_datetime",
]

