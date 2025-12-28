from __future__ import annotations

from flask import jsonify, request, session

from . import bp
from .openapi import json_request_body
from .routes import get_current_user, login_or_jwt_required
from features.wiki.application.use_cases import WikiMediaUploadUseCase
from features.wiki.domain.exceptions import WikiOperationError

from ..services.upload_service import (
    UploadError,
    UploadTooLargeError,
    UnsupportedFormatError,
    prepare_upload,
    commit_uploads,
    has_pending_uploads,
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
@bp.doc(
    methods=["POST"],
    requestBody=json_request_body(
        "Finalize prepared uploads and persist the temporary files.",
        schema={
            "type": "object",
            "properties": {
                "files": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "tempFileId": {
                                "type": "string",
                                "description": "Identifier returned by /upload/prepare.",
                            },
                            "temp_file_id": {
                                "type": "string",
                                "description": "Alternative snake_case key for the temporary file id.",
                            },
                        },
                        "additionalProperties": True,
                    },
                    "description": "List of prepared file descriptors to commit.",
                },
                "destination": {
                    "type": "string",
                    "description": "Optional destination hint such as 'wiki'.",
                },
            },
            "required": ["files"],
            "additionalProperties": False,
        },
        example={
            "files": [{"tempFileId": "abc123"}, {"temp_file_id": "def456"}],
            "destination": "wiki",
        },
    ),
)
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

    destination = payload.get("destination")
    media_payload: list[dict] = []

    try:
        if destination == "wiki":
            if not hasattr(user, "can") or not user.can("wiki:write"):
                return (
                    jsonify({"error": "forbidden", "message": "Permission denied"}),
                    403,
                )
            wiki_result = WikiMediaUploadUseCase().execute(
                session_id=upload_session_id,
                temp_file_ids=temp_ids,
            )
            results = wiki_result.results
            media_payload = [
                {
                    "id": media.id,
                    "sourceType": media.source_type,
                    "filename": media.filename,
                    "localRelPath": media.local_rel_path,
                    "hashSha256": media.hash_sha256,
                }
                for media in wiki_result.media
            ]
        else:
            results = commit_uploads(upload_session_id, getattr(user, "id", None), temp_ids)
    except UploadError as exc:
        return jsonify({"error": "upload_failed", "message": str(exc)}), 400
    except WikiOperationError as exc:
        return jsonify({"error": "upload_failed", "message": str(exc)}), 400

    success_count = sum(1 for item in results if item.get("status") == "success")

    if success_count and not has_pending_uploads(upload_session_id):
        session.pop("upload_session_id", None)

    response_body = {"uploaded": results}
    if destination == "wiki":
        response_body["media"] = media_payload
    return jsonify(response_body)
