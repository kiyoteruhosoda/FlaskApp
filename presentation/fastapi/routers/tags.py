"""タグ管理 API（FastAPI）。

Flask-Smorest 版 ``presentation/web/api/routes.py`` のタグ関連エンドポイントを移植。
- ``GET  /api/tags`` — タグ一覧（インクリメンタル検索対応）
- ``POST /api/tags`` — タグ作成
- ``PUT  /api/tags/{tag_id}`` — タグ更新
- ``PUT  /api/media/{media_id}/tags`` — メディアのタグ一括置換
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from shared.application.authenticated_principal import AuthenticatedPrincipal
from shared.kernel.database.session import get_db
from presentation.fastapi.dependencies.auth import get_current_principal

logger = logging.getLogger(__name__)

router = APIRouter(tags=["tags"])

VALID_TAG_ATTRS = {
    "thing",
    "person",
    "place",
    "event",
    "scene",
    "activity",
    "source",
    "others",
}


def _serialize_tag(tag) -> dict:
    return {"id": tag.id, "name": tag.name, "attr": tag.attr}


@router.get("/tags")
async def api_tags_list(
    q: str = Query("", description="タグ名の部分一致フィルタ"),
    limit: int = Query(20, ge=1, le=100),
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """タグ一覧を返す（インクリメンタル検索対応）。"""
    from bounded_contexts.photonest.infrastructure.photo_models import Tag

    query = db.query(Tag)
    if q:
        like_expr = f"%{q}%"
        query = query.filter(Tag.name.ilike(like_expr))

    tags = query.order_by(Tag.name.asc()).limit(limit).all()
    return {"items": [_serialize_tag(tag) for tag in tags]}


@router.post("/tags", status_code=status.HTTP_201_CREATED)
async def api_tags_create(
    request: Request,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """タグを新規作成する（media:tag-manage 権限が必要）。"""
    from bounded_contexts.photonest.infrastructure.photo_models import Tag

    if not principal.can("media:tag-manage"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "forbidden"},
        )

    payload = await request.json()
    name = (payload.get("name") or "").strip()
    attr = (payload.get("attr") or "").strip()

    if not name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "name_required"},
        )
    if attr not in VALID_TAG_ATTRS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_attr"},
        )

    existing = db.query(Tag).filter(func.lower(Tag.name) == name.lower()).first()
    if existing:
        return {"tag": _serialize_tag(existing), "created": False}

    tag = Tag(name=name, attr=attr, created_by=principal.id)
    db.add(tag)
    db.commit()
    db.refresh(tag)
    return {"tag": _serialize_tag(tag), "created": True}


@router.put("/tags/{tag_id}")
async def api_tags_update(
    tag_id: int,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """既存タグを更新する（media:tag-manage 権限が必要）。"""
    from bounded_contexts.photonest.infrastructure.photo_models import Tag

    if not principal.can("media:tag-manage"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "forbidden"},
        )

    tag = db.get(Tag, tag_id)
    if not tag:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "not_found"},
        )

    payload = await request.json()
    name = payload.get("name")
    attr = payload.get("attr")
    has_changes = False

    if isinstance(name, str):
        stripped = name.strip()
        if not stripped:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "name_required"},
            )
        if stripped.lower() != tag.name.lower():
            duplicate = (
                db.query(Tag)
                .filter(func.lower(Tag.name) == stripped.lower(), Tag.id != tag.id)
                .first()
            )
            if duplicate:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={"error": "duplicate_name"},
                )
            tag.name = stripped
            has_changes = True

    if isinstance(attr, str):
        if attr not in VALID_TAG_ATTRS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "invalid_attr"},
            )
        if attr != tag.attr:
            tag.attr = attr
            has_changes = True

    if has_changes:
        tag.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(tag)

    return {"tag": _serialize_tag(tag), "updated": has_changes}


@router.put("/media/{media_id}/tags")
async def api_media_update_tags(
    media_id: int,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """メディアのタグを一括置換する（media:tag-manage 権限が必要）。"""
    from bounded_contexts.photonest.infrastructure.photo_models import Media, Tag
    from sqlalchemy.orm import joinedload

    if not principal.can("media:tag-manage"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "forbidden"},
        )

    media = (
        db.query(Media)
        .options(joinedload(Media.tags))
        .filter(Media.id == media_id)
        .first()
    )
    if not media or media.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "not_found"},
        )

    payload = await request.json()
    tag_ids = payload.get("tag_ids")
    if tag_ids is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "tag_ids_required"},
        )
    if not isinstance(tag_ids, list):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_tag_ids"},
        )

    normalized_ids: list[int] = []
    seen: set[int] = set()
    for raw_id in tag_ids:
        try:
            value = int(raw_id)
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "invalid_tag_id"},
            )
        if value not in seen:
            seen.add(value)
            normalized_ids.append(value)

    if normalized_ids:
        tags = db.query(Tag).filter(Tag.id.in_(normalized_ids)).all()
        found_ids = {tag.id for tag in tags}
        missing = [tid for tid in normalized_ids if tid not in found_ids]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "unknown_tag", "missing": missing},
            )
    else:
        tags = []

    previous_tag_ids = {tag.id for tag in media.tags}
    new_tag_ids = {tag.id for tag in tags}
    media.tags = tags
    media.updated_at = datetime.now(timezone.utc)
    db.flush()

    removed_tag_ids = previous_tag_ids - new_tag_ids
    if removed_tag_ids:
        _remove_unused_tags(db, removed_tag_ids)

    db.commit()
    db.refresh(media)

    return {
        "tags": [
            _serialize_tag(tag)
            for tag in sorted(media.tags, key=lambda t: (t.name or "").lower())
        ]
    }


def _remove_unused_tags(db: Session, tag_ids: set[int]) -> None:
    """どのメディアにも紐づかなくなったタグを削除する。"""
    if not tag_ids:
        return
    from bounded_contexts.photonest.infrastructure.photo_models import Tag, media_tag
    from sqlalchemy import outerjoin, select, func as sa_func

    unused = (
        db.query(Tag)
        .outerjoin(media_tag, Tag.id == media_tag.c.tag_id)
        .filter(Tag.id.in_(tag_ids))
        .group_by(Tag.id)
        .having(sa_func.count(media_tag.c.media_id) == 0)
        .all()
    )
    for tag in unused:
        db.delete(tag)


__all__ = ["router", "_remove_unused_tags", "_serialize_tag"]
