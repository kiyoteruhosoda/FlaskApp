"""ローカルインポートで利用するメディアメタデータ関連のユーティリティ。"""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from PIL import Image
from PIL.ExifTags import TAGS

from core.utils import open_image_compat, register_heif_support

register_heif_support()


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

        if source_key in {"creation_time", "com.apple.quicktime.creationdate"}:
            metadata.setdefault("creation_time_source", source_key)
            metadata.setdefault("creation_time", str(candidate))

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
                for key in ("creation_time", "com.apple.quicktime.creationdate", "date"):
                    if _assign_shot_at(stream_tags.get(key), key):
                        break

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
    "extract_exif_data",
    "extract_video_metadata",
    "generate_filename",
    "get_image_dimensions",
    "get_relative_path",
    "parse_ffprobe_datetime",
]

