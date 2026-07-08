"""アルバム管理 API（FastAPI）。

Flask-Smorest 版 ``presentation/web/api/routes.py`` のアルバム関連エンドポイントを移植。
- ``GET    /api/albums`` — アルバム一覧
- ``GET    /api/albums/{album_id}`` — アルバム詳細
- ``POST   /api/albums`` — アルバム作成
- ``PUT    /api/albums/{album_id}`` — アルバム更新
- ``PUT    /api/albums/{album_id}/media/order`` — アルバム内メディア並び替え
- ``PUT    /api/albums/order`` — アルバム間並び替え
- ``DELETE /api/albums/{album_id}`` — アルバム削除
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from shared.application.authenticated_principal import AuthenticatedPrincipal
from shared.kernel.database.session import get_db
from presentation.fastapi.dependencies.auth import (
    get_current_principal,
    require_permission,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["albums"])


# ---------------------------------------------------------------------------
# シリアライザ
# ---------------------------------------------------------------------------


def _serialize_tag(tag) -> dict:
    return {"id": tag.id, "name": tag.name, "attr": tag.attr}


def _serialize_album_summary(
    album,
    *,
    media_count: int = 0,
    fallback_cover_id: Optional[int] = None,
    available_media_ids: Optional[list[int]] = None,
) -> dict:
    available_set = set(available_media_ids or [])
    computed_count = media_count if media_count is not None else len(available_set)
    cover_id = album.cover_media_id

    if computed_count == 0:
        cover_id = None
    elif available_set and (cover_id not in available_set):
        cover_id = None
    if cover_id is None:
        cover_id = fallback_cover_id

    created_at = (
        album.created_at.isoformat().replace("+00:00", "Z") if album.created_at else None
    )
    updated_at = (
        album.updated_at.isoformat().replace("+00:00", "Z") if album.updated_at else None
    )
    return {
        "id": album.id,
        "title": album.name,
        "description": album.description,
        "visibility": album.visibility,
        "coverImageId": cover_id,
        "coverMediaId": cover_id,
        "mediaCount": int(computed_count or 0),
        "createdAt": created_at,
        "lastModified": updated_at,
        "displayOrder": album.display_order,
    }


def _resolve_best_thumbnail_url(media, db: Session) -> Optional[str]:
    """利用可能な最大サイズのサムネイル URL を返す（無ければ None）。"""
    try:
        from presentation.fastapi.services.storage_helpers import (
            _resolve_storage_file,
            _thumbnail_rel_path_candidates,
        )
        from bounded_contexts.storage import StorageDomain
    except Exception:
        return None

    rel_candidates = _thumbnail_rel_path_candidates(media)
    if not rel_candidates:
        return None

    for size in (2048, 1024, 512):
        for rel_path in rel_candidates:
            try:
                resolved = _resolve_storage_file(
                    StorageDomain.MEDIA_THUMBNAILS,
                    str(size),
                    rel_path.as_posix(),
                )
                if resolved.exists:
                    return f"/api/media/{media.id}/thumbnail?size={size}"
            except Exception:
                continue
    return None


def _serialize_album_detail(album, media_rows, db: Session) -> dict:
    media_items: list[dict] = []
    fallback_cover_id: Optional[int] = None
    media_ids: list[int] = []

    for media, sort_index in media_rows:
        if fallback_cover_id is None:
            fallback_cover_id = media.id
        media_ids.append(media.id)
        tags = sorted(media.tags, key=lambda t: (t.name or "").lower())
        thumbnail_url = f"/api/media/{media.id}/thumbnail?size=512"
        full_url = _resolve_best_thumbnail_url(media, db) or thumbnail_url
        media_items.append(
            {
                "id": media.id,
                "filename": media.filename,
                "shotAt": (
                    media.shot_at.isoformat().replace("+00:00", "Z")
                    if media.shot_at
                    else None
                ),
                "thumbnailUrl": thumbnail_url,
                "fullUrl": full_url,
                "sortIndex": sort_index,
                "tags": [_serialize_tag(t) for t in tags],
            }
        )

    summary = _serialize_album_summary(
        album,
        media_count=len(media_items),
        fallback_cover_id=fallback_cover_id,
        available_media_ids=media_ids,
    )
    summary["coverMediaId"] = summary.get("coverMediaId")
    summary["media"] = media_items
    summary["mediaIds"] = [item["id"] for item in media_items]
    return summary


def _get_album_media_rows(album_id: int, db: Session):
    from bounded_contexts.photonest.infrastructure.album import SqlAlchemyAlbumRepository

    return SqlAlchemyAlbumRepository(db).media_rows(album_id)


def _album_service(db: Session):
    from bounded_contexts.photonest.application.album import AlbumApplicationService
    from bounded_contexts.photonest.infrastructure.album import SqlAlchemyAlbumRepository

    return AlbumApplicationService(SqlAlchemyAlbumRepository(db))


def _album_error_to_http(error) -> HTTPException:
    from bounded_contexts.photonest.application.album.errors import AlbumApplicationError

    detail: dict = {"error": error.code, "message": error.message}
    detail.update(error.details)
    return HTTPException(status_code=error.status, detail=detail)


# ---------------------------------------------------------------------------
# エンドポイント
# ---------------------------------------------------------------------------


@router.get("/albums")
async def api_albums_list(
    q: str = Query("", description="タイトルの部分一致フィルタ"),
    page: int = Query(1, ge=1),
    pageSize: int = Query(24, ge=1, le=200),
    order: str = Query("desc"),
    cursor: Optional[str] = Query(None),
    principal: AuthenticatedPrincipal = Depends(require_permission("media:view", "album:view")),
    db: Session = Depends(get_db),
):
    """アルバム一覧をページングして返す。"""
    from bounded_contexts.photonest.infrastructure.photo_models import Album, album_item

    stats_subquery = (
        db.query(
            album_item.c.album_id.label("album_id"),
            func.count(album_item.c.media_id).label("media_count"),
            func.min(album_item.c.media_id).label("first_media_id"),
        )
        .group_by(album_item.c.album_id)
        .subquery()
    )

    query = (
        db.query(Album, stats_subquery.c.media_count, stats_subquery.c.first_media_id)
        .outerjoin(stats_subquery, Album.id == stats_subquery.c.album_id)
    )

    if q:
        query = query.filter(Album.name.ilike(f"%{q}%"))

    custom_order = order.lower() == "custom"
    if custom_order:
        order_cols = [
            case((Album.display_order.is_(None), 1), else_=0).asc(),
            Album.display_order.asc(),
            Album.created_at.desc(),
            Album.id.desc(),
        ]
        query = query.order_by(*order_cols)
    elif order.lower() == "asc":
        query = query.order_by(Album.created_at.asc(), Album.id.asc())
    else:
        query = query.order_by(Album.created_at.desc(), Album.id.desc())

    total = db.query(func.count(Album.id)).scalar() or 0
    rows = query.offset((page - 1) * pageSize).limit(pageSize).all()

    items = [
        _serialize_album_summary(
            row[0],
            media_count=row[1] or 0,
            fallback_cover_id=row[2],
        )
        for row in rows
    ]

    return {
        "items": items,
        "total": total,
        "page": page,
        "pageSize": pageSize,
    }


@router.get("/albums/{album_id}")
async def api_album_detail(
    album_id: int,
    principal: AuthenticatedPrincipal = Depends(require_permission("media:view", "album:view")),
    db: Session = Depends(get_db),
):
    """アルバム詳細情報を返す。"""
    from bounded_contexts.photonest.infrastructure.photo_models import Album

    album = db.get(Album, album_id)
    if not album:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "not_found", "message": "Album not found."},
        )

    media_rows = _get_album_media_rows(album_id, db)
    detail = _serialize_album_detail(album, media_rows, db)
    return {"album": detail}


@router.post("/albums", status_code=status.HTTP_201_CREATED)
async def api_album_create(
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_permission("album:create")),
    db: Session = Depends(get_db),
):
    """アルバムを新規作成する。"""
    from bounded_contexts.photonest.application.album import (
        AlbumApplicationError,
        CreateAlbumCommand,
    )

    payload = await request.json()
    command = CreateAlbumCommand(
        name=payload.get("name"),
        description=payload.get("description"),
        visibility=payload.get("visibility"),
        media_ids=payload.get("mediaIds"),
        cover_media_id=payload.get("coverMediaId"),
    )

    try:
        album = _album_service(db).create(command)
    except AlbumApplicationError as err:
        raise _album_error_to_http(err)

    detail = _serialize_album_detail(album, _get_album_media_rows(album.id, db), db)
    return {"album": detail, "created": True}


@router.put("/albums/order")
async def api_albums_reorder(
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_permission("album:edit")),
    db: Session = Depends(get_db),
):
    """アルバムの表示順序を更新する。"""
    from bounded_contexts.photonest.application.album import (
        AlbumApplicationError,
        ReorderAlbumsCommand,
    )

    payload = await request.json()
    command = ReorderAlbumsCommand(album_ids=payload.get("albumIds"))

    try:
        normalized_ids, updated = _album_service(db).reorder_albums(command)
    except AlbumApplicationError as err:
        raise _album_error_to_http(err)

    return {"updated": updated, "albumIds": normalized_ids}


@router.put("/albums/{album_id}")
async def api_album_update(
    album_id: int,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_permission("album:edit")),
    db: Session = Depends(get_db),
):
    """アルバム情報を更新する。"""
    from bounded_contexts.photonest.application.album import (
        AlbumApplicationError,
        UpdateAlbumCommand,
    )
    from bounded_contexts.photonest.application.album.commands import UNSET

    payload = await request.json()
    command = UpdateAlbumCommand(
        album_id=album_id,
        name=payload.get("name"),
        description=payload.get("description"),
        visibility=payload.get("visibility"),
        media_ids=payload.get("mediaIds"),
        cover_media_id=payload.get("coverMediaId") if "coverMediaId" in payload else UNSET,
    )

    try:
        album, has_changes = _album_service(db).update(command)
    except AlbumApplicationError as err:
        raise _album_error_to_http(err)

    detail = _serialize_album_detail(album, _get_album_media_rows(album.id, db), db)
    return {"album": detail, "updated": has_changes}


@router.put("/albums/{album_id}/media/order")
async def api_album_media_reorder(
    album_id: int,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_permission("album:edit")),
    db: Session = Depends(get_db),
):
    """アルバム内のメディア表示順を更新する。"""
    from bounded_contexts.photonest.application.album import (
        AlbumApplicationError,
        ReorderAlbumMediaCommand,
    )

    payload = await request.json()
    command = ReorderAlbumMediaCommand(
        album_id=album_id, media_ids=payload.get("mediaIds")
    )

    try:
        album, updated = _album_service(db).reorder_media(command)
    except AlbumApplicationError as err:
        raise _album_error_to_http(err)

    detail = _serialize_album_detail(album, _get_album_media_rows(album.id, db), db)
    return {"updated": updated, "album": detail}


@router.delete("/albums/{album_id}")
async def api_album_delete(
    album_id: int,
    principal: AuthenticatedPrincipal = Depends(require_permission("album:edit")),
    db: Session = Depends(get_db),
):
    """アルバムを削除する。"""
    from bounded_contexts.photonest.application.album import AlbumApplicationError

    try:
        _album_service(db).delete(album_id)
    except AlbumApplicationError as err:
        raise _album_error_to_http(err)

    return {"result": "deleted"}


__all__ = ["router"]
