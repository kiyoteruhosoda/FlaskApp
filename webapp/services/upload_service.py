"""ファイルアップロード関連のユーティリティ"""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional
from uuid import uuid4

from flask import current_app
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename


class UploadError(Exception):
    """アップロード関連の基本例外"""


class UploadTooLargeError(UploadError):
    """ファイルサイズ制限を超過した場合の例外"""


class UnsupportedFormatError(UploadError):
    """対応していないファイル形式の例外"""


class PreparedFileNotFoundError(UploadError):
    """準備済みファイルが存在しない場合の例外"""


@dataclass
class PreparedUpload:
    """一時保存されたファイルのメタデータ"""

    temp_file_id: str
    file_name: str
    file_size: int
    status: str
    analysis_result: dict


_IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".bmp",
    ".tif",
    ".tiff",
    ".webp",
    ".heic",
    ".heif",
}
_VIDEO_EXTENSIONS = {
    ".mp4",
    ".mov",
    ".m4v",
    ".avi",
    ".mkv",
    ".webm",
}
_ALLOWED_EXTENSIONS = _IMAGE_EXTENSIONS | _VIDEO_EXTENSIONS
_ALLOWED_MIME_PREFIXES = ("image/", "video/")


def _ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _tmp_base_dir() -> Path:
    return Path(current_app.config.get("UPLOAD_TMP_DIR", "/app/data/tmp/upload"))


def _destination_base_dir() -> Path:
    return Path(current_app.config.get("UPLOAD_DESTINATION_DIR", "/app/data/uploads"))


def _max_upload_size() -> int:
    return int(current_app.config.get("UPLOAD_MAX_SIZE", 100 * 1024 * 1024))


def _determine_session_dir(session_id: str) -> Path:
    base = _tmp_base_dir()
    target = base / session_id
    _ensure_directory(target)
    return target


def _sanitize_filename(filename: str) -> str:
    sanitized = secure_filename(filename or "uploaded")
    return sanitized or "uploaded"


def _save_stream(file: FileStorage, destination: Path) -> int:
    max_size = _max_upload_size()
    total = 0
    stream = file.stream

    if hasattr(stream, "seek") and stream.seekable():
        stream.seek(0)

    with destination.open("wb") as fh:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > max_size:
                fh.close()
                destination.unlink(missing_ok=True)
                raise UploadTooLargeError("File exceeds the allowed size limit")
            fh.write(chunk)

    if hasattr(stream, "seek") and stream.seekable():
        stream.seek(0)

    return total


def _detect_format(filename: str) -> str:
    suffix = (Path(filename).suffix or "").lower()
    if suffix in _IMAGE_EXTENSIONS:
        return "IMAGE"
    if suffix in _VIDEO_EXTENSIONS:
        return "VIDEO"
    if suffix == ".csv":
        return "CSV"
    if suffix == ".tsv":
        return "TSV"
    if suffix == ".json":
        return "JSON"
    if suffix == ".txt":
        return "TEXT"
    return "UNKNOWN"


def _analyze_text_file(path: Path) -> dict:
    line_count = 0
    non_empty = 0
    with path.open("r", encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            line_count += 1
            if line.strip():
                non_empty += 1
    return {"lineCount": line_count, "recordCount": non_empty}


def _analyze_json_file(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="ignore")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {"format": "JSON", "recordCount": 0, "valid": False}

    if isinstance(data, list):
        record_count = len(data)
    elif isinstance(data, dict):
        record_count = len(data)
    else:
        record_count = 1

    return {"format": "JSON", "recordCount": record_count, "valid": True}


def _build_analysis(path: Path, filename: str) -> dict:
    detected_format = _detect_format(filename)
    if detected_format == "CSV" or detected_format == "TSV" or detected_format == "TEXT":
        stats = _analyze_text_file(path)
        stats.setdefault("recordCount", stats.get("lineCount", 0))
        stats["format"] = detected_format
        return stats
    if detected_format == "JSON":
        stats = _analyze_json_file(path)
        stats.setdefault("format", "JSON")
        return stats
    return {"format": detected_format}


def prepare_upload(file: FileStorage, session_id: str) -> PreparedUpload:
    if not file or not getattr(file, "filename", None):
        raise UploadError("No file uploaded")

    original_name = file.filename
    suffix = (Path(original_name).suffix or "").lower()
    mimetype = (file.mimetype or "").lower()

    if suffix not in _ALLOWED_EXTENSIONS:
        raise UnsupportedFormatError("Unsupported file format")

    if mimetype and not any(mimetype.startswith(prefix) for prefix in _ALLOWED_MIME_PREFIXES):
        raise UnsupportedFormatError("Unsupported file format")

    session_dir = _determine_session_dir(session_id)
    temp_file_id = uuid4().hex
    temp_path = session_dir / temp_file_id

    file_size = _save_stream(file, temp_path)

    analysis_result = _build_analysis(temp_path, original_name)
    analysis_result.setdefault("format", _detect_format(original_name))

    metadata = {
        "temp_file_id": temp_file_id,
        "file_name": original_name,
        "file_size": file_size,
        "status": "analyzed",
        "analysis_result": analysis_result,
    }

    metadata_path = session_dir / f"{temp_file_id}.json"
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")

    return PreparedUpload(
        temp_file_id=temp_file_id,
        file_name=original_name,
        file_size=file_size,
        status="analyzed",
        analysis_result=analysis_result,
    )


def _load_metadata(session_dir: Path, temp_file_id: str) -> dict:
    metadata_path = session_dir / f"{temp_file_id}.json"
    if not metadata_path.exists():
        raise PreparedFileNotFoundError("Prepared file metadata not found")
    text = metadata_path.read_text(encoding="utf-8")
    return json.loads(text)


def _delete_metadata(session_dir: Path, temp_file_id: str) -> None:
    metadata_path = session_dir / f"{temp_file_id}.json"
    metadata_path.unlink(missing_ok=True)


def _generate_destination_path(dest_dir: Path, filename: str) -> Path:
    sanitized = _sanitize_filename(filename)
    candidate = dest_dir / sanitized
    if not candidate.exists():
        return candidate

    stem = candidate.stem
    suffix = candidate.suffix
    counter = 1
    while True:
        numbered = dest_dir / f"{stem}_{counter}{suffix}"
        if not numbered.exists():
            return numbered
        counter += 1


def commit_uploads(session_id: str, user_id: Optional[int], temp_file_ids: Iterable[str]) -> list[dict]:
    if not user_id:
        raise UploadError("User information is required to commit uploads")

    session_dir = _determine_session_dir(session_id)
    destination_dir = _destination_base_dir() / str(user_id)
    _ensure_directory(destination_dir)
    try:
        destination_dir_resolved = destination_dir.resolve()
    except OSError:
        destination_dir_resolved = destination_dir

    results = []

    for temp_file_id in temp_file_ids:
        try:
            metadata = _load_metadata(session_dir, temp_file_id)
        except PreparedFileNotFoundError:
            results.append({
                "tempFileId": temp_file_id,
                "status": "error",
                "message": "File not found or already committed",
            })
            continue

        temp_path = session_dir / temp_file_id
        if not temp_path.exists():
            _delete_metadata(session_dir, temp_file_id)
            results.append({
                "tempFileId": temp_file_id,
                "status": "error",
                "message": "File not found or already committed",
            })
            continue

        destination_path = _generate_destination_path(destination_dir, metadata.get("file_name", "uploaded"))

        try:
            moved_target = shutil.move(str(temp_path), str(destination_path))
        except FileNotFoundError:
            results.append({
                "tempFileId": temp_file_id,
                "status": "error",
                "message": "File not found or already committed",
            })
            continue
        except OSError as exc:
            current_app.logger.exception(
                "upload.commit.move_failed",
                extra={
                    "temp_file_id": temp_file_id,
                    "destination": str(destination_path),
                    "error": str(exc),
                },
            )
            results.append({
                "tempFileId": temp_file_id,
                "status": "error",
                "message": "Failed to store file",
            })
            continue

        if moved_target:
            try:
                moved_to = Path(moved_target)
            except TypeError:
                moved_to = destination_path
        else:
            moved_to = destination_path

        actual_destination = moved_to if moved_to.is_absolute() else destination_dir / moved_to

        if not actual_destination.exists():
            current_app.logger.error(
                "upload.commit.destination_missing",
                extra={
                    "temp_file_id": temp_file_id,
                    "destination": str(actual_destination),
                },
            )
            results.append({
                "tempFileId": temp_file_id,
                "status": "error",
                "message": "Failed to store file",
            })
            continue

        resolved_destination = actual_destination.resolve()

        try:
            resolved_destination.relative_to(destination_dir_resolved)
        except ValueError:
            current_app.logger.error(
                "upload.commit.unexpected_destination",
                extra={
                    "temp_file_id": temp_file_id,
                    "expected_dir": str(destination_dir_resolved),
                    "actual_path": str(resolved_destination),
                },
            )
            try:
                shutil.move(str(resolved_destination), str(temp_path))
            except OSError:
                pass
            results.append({
                "tempFileId": temp_file_id,
                "status": "error",
                "message": "Failed to store file",
            })
            continue

        destination_path = resolved_destination

        _delete_metadata(session_dir, temp_file_id)

        results.append({
            "tempFileId": temp_file_id,
            "status": "success",
            "fileName": metadata.get("file_name"),
            "storedPath": str(destination_path),
        })

    _cleanup_session_dir_if_empty(session_dir)

    return results


def has_pending_uploads(session_id: str) -> bool:
    session_dir = _tmp_base_dir() / session_id
    try:
        next(session_dir.iterdir())
    except StopIteration:
        return False
    except FileNotFoundError:
        return False
    return True


def _cleanup_session_dir_if_empty(session_dir: Path) -> None:
    try:
        next(session_dir.iterdir())
    except StopIteration:
        try:
            session_dir.rmdir()
        except OSError:
            pass
    except FileNotFoundError:
        pass


__all__ = [
    "PreparedUpload",
    "UploadError",
    "UploadTooLargeError",
    "UnsupportedFormatError",
    "PreparedFileNotFoundError",
    "prepare_upload",
    "commit_uploads",
    "has_pending_uploads",
]
