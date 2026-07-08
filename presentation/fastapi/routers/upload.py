"""アップロード API（FastAPI）。

Flask-Smorest 版 ``presentation/web/api/upload.py`` を移植。

注意: Flask 版はサーバーサイドセッションで ``upload_session_id`` を管理していたが、
FastAPI 版では Cookie ベースのセッション ID を使用する。
クライアントは ``X-Upload-Session`` ヘッダーまたはクッキーで ID を渡すこと。
"""
from __future__ import annotations

import logging
from uuid import uuid4

from fastapi import APIRouter, Cookie, Depends, File, Form, HTTPException, Request, Response, UploadFile, status
from sqlalchemy.orm import Session

from shared.application.authenticated_principal import AuthenticatedPrincipal
from shared.kernel.database.session import get_db
from presentation.fastapi.dependencies.auth import get_current_principal

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/upload", tags=["upload"])


def _get_or_create_upload_session_id(
    request: Request,
    response: Response,
    upload_session: str | None = Cookie(None, alias="upload_session_id"),
) -> str:
    """Cookie から upload_session_id を取得、なければ新規生成してセットする。"""
    session_id = (
        request.headers.get("X-Upload-Session")
        or upload_session
    )
    if not session_id:
        session_id = uuid4().hex
        response.set_cookie(
            "upload_session_id",
            session_id,
            httponly=True,
            samesite="lax",
            secure=True,
        )
    return session_id


@router.post("/prepare")
async def api_upload_prepare(
    request: Request,
    response: Response,
    file: UploadFile = File(...),
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
    upload_session: str | None = Cookie(None, alias="upload_session_id"),
):
    """ファイルをアップロード準備（一時保存）する。"""
    from presentation.fastapi.services.upload_service import (
        UploadError,
        UploadTooLargeError,
        UnsupportedFormatError,
        prepare_upload,
    )

    upload_session_id = _get_or_create_upload_session_id(request, response, upload_session)

    try:
        prepared = prepare_upload(file, upload_session_id)
    except UploadTooLargeError as exc:
        raise HTTPException(status_code=400, detail={"error": "file_too_large", "message": str(exc)})
    except UnsupportedFormatError as exc:
        raise HTTPException(status_code=400, detail={"error": "unsupported_format", "message": str(exc)})
    except UploadError as exc:
        raise HTTPException(status_code=400, detail={"error": "upload_failed", "message": str(exc)})

    return {
        "tempFileId": prepared.temp_file_id,
        "fileName": prepared.file_name,
        "fileSize": prepared.file_size,
        "status": prepared.status,
        "analysisResult": prepared.analysis_result,
    }


@router.post("/commit")
async def api_upload_commit(
    request: Request,
    response: Response,
    body: dict,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
    upload_session: str | None = Cookie(None, alias="upload_session_id"),
):
    """準備済みファイルを確定（永続化）する。"""
    from presentation.fastapi.services.upload_service import (
        UploadError,
        commit_uploads,
        has_pending_uploads,
    )
    from bounded_contexts.wiki.application.use_cases import WikiMediaUploadUseCase
    from bounded_contexts.wiki.domain.exceptions import WikiOperationError

    files = body.get("files")
    if not isinstance(files, list) or not files:
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_payload", "message": "No files specified"},
        )

    upload_session_id = (
        request.headers.get("X-Upload-Session")
        or upload_session
    )
    if not upload_session_id:
        raise HTTPException(
            status_code=400,
            detail={"error": "session_not_found", "message": "No prepared files found"},
        )

    temp_ids: list[str] = []
    for file_entry in files:
        if not isinstance(file_entry, dict):
            continue
        temp_id = file_entry.get("tempFileId") or file_entry.get("temp_file_id")
        if temp_id:
            temp_ids.append(str(temp_id))

    if not temp_ids:
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_payload", "message": "No files specified"},
        )

    destination = body.get("destination")
    media_payload: list[dict] = []

    try:
        if destination == "wiki":
            if not principal.can("wiki:write"):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={"error": "forbidden", "message": "Permission denied"},
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
            results = commit_uploads(upload_session_id, int(principal.user_id), temp_ids)
    except UploadError as exc:
        raise HTTPException(status_code=400, detail={"error": "upload_failed", "message": str(exc)})
    except WikiOperationError as exc:
        raise HTTPException(status_code=400, detail={"error": "upload_failed", "message": str(exc)})

    success_count = sum(1 for item in results if item.get("status") == "success")
    if success_count and not has_pending_uploads(upload_session_id):
        response.delete_cookie("upload_session_id")

    response_body = {"uploaded": results}
    if destination == "wiki":
        response_body["media"] = media_payload
    return response_body
