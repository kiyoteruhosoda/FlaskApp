from __future__ import annotations

from flask import jsonify, request, session

from . import bp
from .routes import get_current_user, login_or_jwt_required
from ..services.upload_service import (
    UploadError,
    UploadTooLargeError,
    UnsupportedFormatError,
    prepare_upload,
    commit_uploads,
)


def _get_or_create_upload_session_id() -> str:
    upload_session_id = session.get("upload_session_id")
    if not upload_session_id:
        from uuid import uuid4

        upload_session_id = uuid4().hex
        session["upload_session_id"] = upload_session_id
    return upload_session_id


@bp.post("/upload/prepare")
@login_or_jwt_required
def api_upload_prepare():
    file = request.files.get("file")
    if not file:
        return jsonify({"error": "file_required"}), 400

    upload_session_id = _get_or_create_upload_session_id()

    try:
        prepared = prepare_upload(file, upload_session_id)
    except UploadTooLargeError as exc:
        return jsonify({"error": "file_too_large", "message": str(exc)}), 400
    except UnsupportedFormatError as exc:
        return jsonify({"error": "unsupported_format", "message": str(exc)}), 400
    except UploadError as exc:
        return jsonify({"error": "upload_failed", "message": str(exc)}), 400

    response_payload = {
        "tempFileId": prepared.temp_file_id,
        "fileName": prepared.file_name,
        "fileSize": prepared.file_size,
        "status": prepared.status,
        "analysisResult": prepared.analysis_result,
    }

    return jsonify(response_payload)


@bp.post("/upload/commit")
@login_or_jwt_required
def api_upload_commit():
    payload = request.get_json(silent=True) or {}
    files = payload.get("files")

    if not isinstance(files, list) or not files:
        return jsonify({"error": "invalid_payload", "message": "No files specified"}), 400

    upload_session_id = session.get("upload_session_id")
    if not upload_session_id:
        return jsonify({"error": "session_not_found", "message": "No prepared files found"}), 400

    user = get_current_user()
    if not user or not getattr(user, "id", None):
        return jsonify({"error": "authentication_required"}), 401

    temp_ids: list[str] = []
    for file_entry in files:
        if not isinstance(file_entry, dict):
            continue
        temp_id = file_entry.get("tempFileId") or file_entry.get("temp_file_id")
        if temp_id:
            temp_ids.append(str(temp_id))

    if not temp_ids:
        return jsonify({"error": "invalid_payload", "message": "No files specified"}), 400

    try:
        results = commit_uploads(upload_session_id, getattr(user, "id", None), temp_ids)
    except UploadError as exc:
        return jsonify({"error": "upload_failed", "message": str(exc)}), 400

    success_count = sum(1 for item in results if item.get("status") == "success")

    if success_count:
        session.pop("upload_session_id", None)

    return jsonify({"uploaded": results})
