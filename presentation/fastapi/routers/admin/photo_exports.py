"""管理 API — Photo Exports (`/api/admin/photo-exports`)。

FastAPI 移植版。オリジナル画像・動画を ZIP 形式でダウンロードする。
"""
from __future__ import annotations

import io
import zipfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from shared.application.authenticated_principal import AuthenticatedPrincipal
from shared.kernel.database.session import get_db
from shared.kernel.settings.settings import settings
from presentation.fastapi.dependencies.auth import get_current_principal

router = APIRouter(prefix="/admin/photo-exports", tags=["admin:photo-exports"])


def _require_system_manage(principal: AuthenticatedPrincipal) -> None:
    if not principal.can("system:manage"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "forbidden", "message": "system:manage permission required"},
        )


def _parse_date(raw: str | None, field_name: str) -> Optional[datetime]:
    if not raw or not raw.strip():
        return None
    try:
        return datetime.fromisoformat(raw.strip()).replace(tzinfo=timezone.utc)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": f"invalid_{field_name}"},
        )


def _build_media_query(db: Session, date_from: Optional[datetime], date_to: Optional[datetime]):
    from sqlalchemy import and_, or_
    from bounded_contexts.photonest.infrastructure.photo_models import Media

    not_deleted = or_(Media.is_deleted.is_(False), Media.is_deleted.is_(None))
    conditions = [not_deleted]
    if date_from:
        conditions.append(Media.imported_at >= date_from)
    if date_to:
        conditions.append(Media.imported_at <= date_to)

    return (
        db.query(Media)
        .filter(and_(*conditions))
        .order_by(Media.imported_at.asc(), Media.id.asc())
    )


def _unique_arcname(name: str, seen: set[str]) -> str:
    if name not in seen:
        return name
    stem = Path(name).stem
    suffix = Path(name).suffix
    i = 1
    while True:
        candidate = f"{stem}_{i}{suffix}"
        if candidate not in seen:
            return candidate
        i += 1


@router.get("/preview")
async def api_admin_photo_exports_preview(
    dateFrom: str | None = Query(None),
    dateTo: str | None = Query(None),
    limit: int = Query(500, ge=1, le=5000),
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """エクスポート対象のメディア件数と合計サイズをプレビューする。"""
    _require_system_manage(principal)

    date_from = _parse_date(dateFrom, "date_from")
    date_to = _parse_date(dateTo, "date_to")
    if date_to and date_to.hour == 0 and date_to.minute == 0 and date_to.second == 0:
        date_to = date_to + timedelta(days=1) - timedelta(seconds=1)

    query = _build_media_query(db, date_from, date_to)
    total = query.count()
    capped = query.limit(limit).all()

    total_size = sum(m.file_size or 0 for m in capped)
    return {
        "matchedCount": total,
        "exportCount": len(capped),
        "totalBytes": total_size,
        "limit": limit,
    }


@router.get("/download")
async def api_admin_photo_exports_download(
    dateFrom: str | None = Query(None),
    dateTo: str | None = Query(None),
    limit: int = Query(500, ge=1, le=5000),
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """対象メディアを ZIP にまとめてストリーミングダウンロードする。"""
    _require_system_manage(principal)

    date_from = _parse_date(dateFrom, "date_from")
    date_to = _parse_date(dateTo, "date_to")
    if date_to and date_to.hour == 0 and date_to.minute == 0 and date_to.second == 0:
        date_to = date_to + timedelta(days=1) - timedelta(seconds=1)

    query = _build_media_query(db, date_from, date_to)
    media_list = query.limit(limit).all()

    originals_dir = settings.storage_originals_directory

    def _generate_zip():
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
            seen_names: set[str] = set()
            for media in media_list:
                if not media.local_rel_path:
                    continue
                abs_path = originals_dir / media.local_rel_path
                if not abs_path.exists():
                    continue
                arc_name = _unique_arcname(abs_path.name, seen_names)
                seen_names.add(arc_name)
                zf.write(str(abs_path), arc_name)
        buffer.seek(0)
        yield buffer.read()

    filename = "photo_exports_{}.zip".format(
        datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    )
    return StreamingResponse(
        _generate_zip(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
