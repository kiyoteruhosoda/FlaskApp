"""メディア管理 API（FastAPI）。

Flask-Smorest 版 ``presentation/web/api/routes.py`` のメディア関連エンドポイントを移植。
- ``GET    /api/media`` — メディア一覧
- ``GET    /api/media/duplicates`` — 重複候補グループ
- ``GET    /api/media/{media_id}`` — メディア詳細
- ``PATCH  /api/media/{media_id}`` — メタデータ更新
- ``DELETE /api/media/{media_id}`` — ソフト削除
- ``POST   /api/media/bulk-actions`` — 一括操作
- ``GET    /api/media/{media_id}/thumbnail`` — サムネイル画像
- ``POST   /api/media/{media_id}/thumb-url`` — 署名付きサムネイル URL
- ``POST   /api/media/{media_id}/recover`` — メタデータ再取得・復元
- ``POST   /api/media/{media_id}/original-url`` — 署名付きオリジナル URL
- ``POST   /api/media/{media_id}/playback-url`` — 署名付き再生 URL
- ``GET    /api/media/thumbs/{rel}`` — サムネイル fallback ダウンロード
- ``GET    /api/media/playback/{rel}`` — 再生ファイル fallback ダウンロード
- ``GET    /api/media/originals/{rel}`` — オリジナル fallback ダウンロード
- ``GET    /api/dl/{token}`` — 署名付きトークンで保護されたダウンロード
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import mimetypes
import os
import posixpath
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload
from werkzeug.utils import secure_filename

from shared.application.authenticated_principal import AuthenticatedPrincipal
from shared.kernel.database.session import get_db
from shared.kernel.settings.settings import settings
from shared.kernel.time.clock import utc_now_isoformat
from presentation.fastapi.dependencies.auth import get_current_principal

logger = logging.getLogger(__name__)

router = APIRouter(tags=["media"])

# ---------------------------------------------------------------------------
# シリアライザ・ヘルパー
# ---------------------------------------------------------------------------


def _serialize_tag(tag) -> dict:
    return {"id": tag.id, "name": tag.name, "attr": tag.attr}


def _isoformat_utc(value: Optional[datetime]) -> Optional[str]:
    if not value:
        return None
    if value.tzinfo is None:
        normalized = value.replace(tzinfo=timezone.utc)
    else:
        normalized = value.astimezone(timezone.utc)
    return normalized.isoformat().replace("+00:00", "Z")


def _normalize_rel_path(value: Optional[str]) -> Optional[Path]:
    if not value:
        return None
    p = Path(value)
    if p.is_absolute():
        try:
            p = p.relative_to("/")
        except ValueError:
            return None
    if ".." in p.parts:
        return None
    return p


def _thumbnail_rel_path_candidates(media) -> list[Path]:
    candidates: list[Path] = []

    def _append(path: Optional[Path]) -> None:
        if path and path not in candidates:
            candidates.append(path)

    def _replace_suffix(path: Path, suffix: str) -> Path:
        if path.suffix:
            return path.with_suffix(suffix)
        return path.with_name(path.name + suffix)

    thumb_rel = _normalize_rel_path(getattr(media, "thumbnail_rel_path", None))
    _append(thumb_rel)
    local_rel = _normalize_rel_path(media.local_rel_path)
    _append(local_rel)
    if local_rel:
        for suffix in (".avif", ".jpg", ".png"):
            _append(_replace_suffix(local_rel, suffix))
    return candidates


_PLAYBACK_STATUS_PRIORITY = {"done": 3, "processing": 2, "pending": 1, "error": 0}


def _select_preferred_playback(playbacks):
    if not playbacks:
        return None
    base_ts = datetime.min.replace(tzinfo=timezone.utc)

    def _priority(pb):
        s = (pb.status or "").lower()
        return (
            _PLAYBACK_STATUS_PRIORITY.get(s, -1),
            1 if (pb.preset or "").lower() == "std1080p" else 0,
            pb.updated_at or pb.created_at or base_ts,
            pb.id or 0,
        )

    return max(playbacks, key=_priority)


def _build_playback_dict(playback) -> dict:
    def _posix(p):
        n = _normalize_rel_path(p)
        return n.as_posix() if n else None

    return {
        "available": bool(playback and playback.status == "done"),
        "preset": playback.preset if playback else None,
        "rel_path": _posix(playback.rel_path) if playback else None,
        "poster_rel_path": _posix(playback.poster_rel_path) if playback else None,
        "status": playback.status if playback else None,
    }


def _build_exif_dict(exif) -> dict:
    return {
        "camera_make": exif.camera_make if exif else None,
        "camera_model": exif.camera_model if exif else None,
        "lens": exif.lens if exif else None,
        "iso": exif.iso if exif else None,
        "shutter": exif.shutter if exif else None,
        "f_number": float(exif.f_number) if exif and exif.f_number is not None else None,
        "focal_len": float(exif.focal_len) if exif and exif.focal_len is not None else None,
        "gps_lat": float(exif.gps_lat) if exif and exif.gps_lat is not None else None,
        "gps_lng": float(exif.gps_lng) if exif and exif.gps_lng is not None else None,
    }


def _serialize_media_detail(media) -> dict:
    sidecars = [
        {"type": s.type, "rel_path": s.rel_path, "bytes": s.bytes}
        for s in media.sidecars
    ]
    pb = _select_preferred_playback(list(media.playbacks))
    return {
        "id": media.id,
        "google_media_id": media.google_media_id,
        "account_id": media.account_id,
        "local_rel_path": media.local_rel_path,
        "filename": media.filename,
        "source_type": media.source_type,
        "camera_make": media.camera_make,
        "camera_model": media.camera_model,
        "bytes": media.bytes,
        "mime_type": media.mime_type,
        "width": media.width,
        "height": media.height,
        "duration_ms": media.duration_ms,
        "shot_at": _isoformat_utc(media.shot_at),
        "imported_at": _isoformat_utc(media.imported_at),
        "is_video": int(bool(media.is_video)),
        "is_deleted": int(bool(media.is_deleted)),
        "has_playback": int(bool(media.has_playback)),
        "exif": _build_exif_dict(media.exif),
        "sidecars": sidecars,
        "playback": _build_playback_dict(pb),
        "tags": [
            _serialize_tag(t)
            for t in sorted(media.tags, key=lambda t: (t.name or "").lower())
        ],
    }


# ---------------------------------------------------------------------------
# ストレージヘルパー（Flask routes.py 側の実装を再利用）
# ---------------------------------------------------------------------------


def _storage_service():
    from presentation.fastapi.services.storage_helpers import _storage_service as _svc
    return _svc()


def _resolve_storage_file(domain, *parts, intent=None):
    from presentation.fastapi.services.storage_helpers import _resolve_storage_file as _rsf
    if intent is not None:
        return _rsf(domain, *parts, intent=intent)
    return _rsf(domain, *parts)


# ---------------------------------------------------------------------------
# 署名付き URL ヘルパー
# ---------------------------------------------------------------------------


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _sign_payload(payload: dict) -> str:
    canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    key_b64 = settings.media_download_signing_key
    key = _b64url_decode(key_b64) if key_b64 else b""
    sig = hmac.new(key, canonical, hashlib.sha256).digest()
    return f"{_b64url_encode(canonical)}.{_b64url_encode(sig)}"


def _verify_token(token: str):
    try:
        payload_b64, sig_b64 = token.split(".", 1)
        payload_bytes = _b64url_decode(payload_b64)
        if _b64url_encode(payload_bytes) != payload_b64:
            return None, "invalid_token"
        payload = json.loads(payload_bytes)
    except Exception:
        return None, "invalid_token"

    key_b64 = settings.media_download_signing_key
    key = _b64url_decode(key_b64) if key_b64 else b""
    canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    expected_sig = hmac.new(key, canonical, hashlib.sha256).digest()
    sig_bytes = _b64url_decode(sig_b64)
    if _b64url_encode(sig_bytes) != sig_b64:
        return None, "invalid_token"
    if not hmac.compare_digest(expected_sig, sig_bytes):
        return None, "invalid_token"
    if payload.get("exp", 0) < int(time.time()):
        return None, "expired"
    return payload, None


def _cacheable_signed_exp(ttl: int) -> tuple[int, int]:
    now = int(time.time())
    window = max(ttl, 1)
    exp = ((now // window) + 2) * window
    return exp, max(exp - now, 0)


def _build_content_disposition(filename: str) -> str:
    sanitized = (filename or "").replace("\r", " ").replace("\n", " ").strip()
    fallback = secure_filename(sanitized) or "download"
    if sanitized and sanitized != fallback:
        return (
            f'attachment; filename="{fallback}"; '
            f"filename*=UTF-8''{quote(sanitized, safe='')}"
        )
    return f'attachment; filename="{fallback}"'


def _resolve_download_filename(payload: dict, rel: str, abs_path: str, db: Session) -> Optional[str]:
    from bounded_contexts.photonest.infrastructure.photo_models import Media

    filename: Optional[str] = None
    media_id = payload.get("mid")
    if media_id is not None:
        media = db.get(Media, media_id)
        if media and media.filename:
            filename = media.filename

    if not filename:
        rel_name = os.path.basename(rel) if rel else None
        if rel_name:
            filename = rel_name
        else:
            filename = os.path.basename(abs_path) if abs_path else None

    path_ext = os.path.splitext(abs_path)[1] if abs_path else ""
    if filename:
        base, ext = os.path.splitext(filename)
        if payload.get("typ") == "playback" and path_ext:
            if ext.lower() != path_ext.lower():
                filename = base + path_ext
        elif not ext and path_ext:
            filename = base + path_ext
    return filename


def _build_accel_target(prefix: Optional[str], rel: str, token: str) -> Optional[str]:
    if not prefix:
        return None
    normalized = rel.replace(os.sep, "/").lstrip("/")
    if not normalized:
        return None
    base = posixpath.join(prefix.rstrip("/"), normalized)
    if token:
        return f"{base}?token={quote(token, safe='')}"
    return base


# ---------------------------------------------------------------------------
# ファイル配信ヘルパー
# ---------------------------------------------------------------------------


def _build_file_response(
    *,
    payload: dict,
    resolved,
    rel: str,
    content_type: str,
    download_filename: Optional[str],
    accel_target: Optional[str],
    request: Request,
    db: Session,
) -> Response:
    service = _storage_service()
    abs_path = resolved.absolute_path
    size = service.size(abs_path)
    exp_ts = payload.get("exp")
    try:
        ttl = max(int(exp_ts) - int(time.time()), 0) if exp_ts else 0
    except (TypeError, ValueError):
        ttl = 0
    cache_control = f"private, max-age={ttl}"

    headers: dict[str, str] = {
        "Accept-Ranges": "bytes",
        "Cache-Control": cache_control,
        "Content-Length": str(size),
    }
    if download_filename:
        headers["Content-Disposition"] = _build_content_disposition(download_filename)
    if accel_target:
        headers["X-Accel-Redirect"] = accel_target

    range_header = request.headers.get("Range") if request.method != "HEAD" else None
    if range_header:
        m = re.match(r"bytes=(\d+)-(\d*)", range_header)
        if m:
            start = int(m.group(1))
            end = int(m.group(2) or size - 1)
            end = min(end, size - 1)
            length = end - start + 1
            with service.open(abs_path, "rb") as f:
                f.seek(start)
                data = f.read(length)
            range_headers = dict(headers)
            range_headers["Content-Range"] = f"bytes {start}-{end}/{size}"
            range_headers["Content-Length"] = str(length)
            return Response(
                content=data,
                status_code=206,
                headers=range_headers,
                media_type=content_type,
            )

    if request.method == "HEAD":
        return Response(
            content=b"",
            headers=headers,
            media_type=content_type,
        )

    with service.open(abs_path, "rb") as f:
        data = f.read()
    return Response(content=data, headers=headers, media_type=content_type)


# ---------------------------------------------------------------------------
# ソフト削除・ファイル削除ヘルパー
# ---------------------------------------------------------------------------


def _remove_media_files(media, db: Session) -> None:
    from bounded_contexts.photonest.infrastructure.photo_models import MediaPlayback
    from bounded_contexts.storage import StorageDomain
    from bounded_contexts.storage.infrastructure.filesystem import StorageIntent

    service = _storage_service()
    rel_path = _normalize_rel_path(media.local_rel_path)

    def _remove(domain, *parts) -> None:
        try:
            resolved = _resolve_storage_file(domain, *parts, intent=StorageIntent.DELETE)
            abs_path = resolved.absolute_path
            if not abs_path:
                return
            service.remove(abs_path)
        except FileNotFoundError:
            pass
        except Exception as exc:
            logger.warning(
                "Failed to remove file: media_id=%s error=%s", media.id, exc
            )

    if rel_path:
        _remove(StorageDomain.MEDIA_ORIGINALS, rel_path.as_posix())

    thumb_candidates = _thumbnail_rel_path_candidates(media)
    if thumb_candidates:
        for size in (256, 1024, 2048):
            for candidate in thumb_candidates:
                _remove(StorageDomain.MEDIA_THUMBNAILS, str(size), candidate.as_posix())

    for playback in media.playbacks:
        rel = _normalize_rel_path(playback.rel_path)
        if rel:
            _remove(StorageDomain.MEDIA_PLAYBACK, rel.as_posix())
        poster_rel = _normalize_rel_path(playback.poster_rel_path)
        if poster_rel:
            _remove(StorageDomain.MEDIA_PLAYBACK, poster_rel.as_posix())


def _soft_delete_media(media, db: Session, *, now: Optional[datetime] = None) -> None:
    from bounded_contexts.photonest.infrastructure.photo_models import Album, album_item

    if media.is_deleted:
        return

    effective_now = now or datetime.now(timezone.utc)

    associated_albums = (
        db.query(Album)
        .join(album_item, Album.id == album_item.c.album_id)
        .filter(album_item.c.media_id == media.id)
        .all()
    )

    if associated_albums:
        db.execute(album_item.delete().where(album_item.c.media_id == media.id))
        for album in associated_albums:
            if album.cover_media_id == media.id:
                new_cover_id = db.execute(
                    select(album_item.c.media_id)
                    .where(album_item.c.album_id == album.id)
                    .order_by(album_item.c.sort_index.asc(), album_item.c.media_id.asc())
                    .limit(1)
                ).scalar()
                album.cover_media_id = new_cover_id
            else:
                if album.cover_media_id is not None:
                    existing_cover = db.execute(
                        select(album_item.c.media_id)
                        .where(
                            album_item.c.album_id == album.id,
                            album_item.c.media_id == album.cover_media_id,
                        )
                        .limit(1)
                    ).scalar()
                    if existing_cover is None:
                        new_cover_id = db.execute(
                            select(album_item.c.media_id)
                            .where(album_item.c.album_id == album.id)
                            .order_by(
                                album_item.c.sort_index.asc(), album_item.c.media_id.asc()
                            )
                            .limit(1)
                        ).scalar()
                        album.cover_media_id = new_cover_id
            album.updated_at = effective_now

    _remove_media_files(media, db)
    media.is_deleted = True
    media.updated_at = effective_now


def _remove_unused_tags(db: Session, tag_ids: set[int]) -> None:
    if not tag_ids:
        return
    from bounded_contexts.photonest.infrastructure.photo_models import Tag, media_tag
    from sqlalchemy import outerjoin
    from sqlalchemy.sql import functions as sa_func

    unused = (
        db.query(Tag)
        .outerjoin(media_tag, Tag.id == media_tag.c.tag_id)
        .filter(Tag.id.in_(tag_ids))
        .group_by(Tag.id)
        .having(func.count(media_tag.c.media_id) == 0)
        .all()
    )
    for tag in unused:
        db.delete(tag)


def _trigger_thumbnail_regeneration(
    media_id: int, *, reason: str, force: bool = False, principal_id: Optional[int] = None
) -> tuple[bool, Optional[str]]:
    """サムネイル再生成を非同期または同期で実行する。"""
    from bounded_contexts.photonest.tasks.media_post_processing import enqueue_thumbs_generate

    celery_task_id: Optional[str] = None

    try:
        from cli.src.celery.tasks import thumbs_generate_task
    except Exception:
        thumbs_task = None
    else:
        thumbs_task = thumbs_generate_task

    if thumbs_task is not None and not settings.testing:
        try:
            async_result = thumbs_task.apply_async(
                kwargs={"media_id": media_id, "force": force}
            )
            celery_task_id = getattr(async_result, "id", None)
            logger.info(
                "Thumbnail task enqueued: media_id=%s task_id=%s reason=%s",
                media_id,
                celery_task_id,
                reason,
            )
            return True, celery_task_id
        except Exception as exc:
            logger.warning(
                "Failed to enqueue thumbnail task: media_id=%s error=%s", media_id, exc
            )

    try:
        result = enqueue_thumbs_generate(
            media_id,
            request_context={"reason": reason},
            force=force,
        )
        ok = bool(result.get("ok"))
        return ok, celery_task_id
    except Exception as exc:
        logger.warning("Synchronous thumbnail generation failed: %s", exc)
        return False, celery_task_id


# ---------------------------------------------------------------------------
# メディア一覧
# ---------------------------------------------------------------------------


@router.get("/media")
async def api_media_list(
    page: int = Query(1, ge=1),
    pageSize: int = Query(200, ge=1, le=500),
    cursor: Optional[str] = Query(None),
    order: str = Query("desc"),
    include_deleted: int = Query(0),
    type: Optional[str] = Query(None),
    tags: Optional[str] = Query(None, description="カンマ区切りのタグ ID"),
    after: Optional[str] = Query(None, description="ISO8601 日時（この日時以降）"),
    before: Optional[str] = Query(None, description="ISO8601 日時（この日時以前）"),
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """メディア一覧をページングして返す。"""
    from bounded_contexts.photonest.infrastructure.photo_models import Media, Tag

    trace = uuid4().hex
    logger.info("media.list.begin trace=%s cursor=%s", trace, cursor)

    query = db.query(Media).options(
        joinedload(Media.account),
        joinedload(Media.tags),
    )

    if not include_deleted:
        from sqlalchemy import or_
        query = query.filter(
            or_(Media.is_deleted.is_(False), Media.is_deleted.is_(None))
        )

    media_type = (type or "").lower()
    if media_type == "photo":
        from sqlalchemy import or_
        query = query.filter(
            or_(Media.is_video.is_(False), Media.is_video.is_(None))
        )
    elif media_type == "video":
        query = query.filter(Media.is_video.is_(True))

    tag_ids: list[int] = []
    if tags:
        for part in tags.split(","):
            part = part.strip()
            if not part:
                continue
            try:
                tag_ids.append(int(part))
            except ValueError:
                continue

    if tag_ids:
        seen: set[int] = set()
        for tid in tag_ids:
            if tid not in seen:
                seen.add(tid)
                query = query.filter(Media.tags.any(Tag.id == tid))

    if after:
        try:
            after_dt = datetime.fromisoformat(after.replace("Z", "+00:00"))
            query = query.filter(Media.shot_at >= after_dt)
        except Exception:
            pass
    if before:
        try:
            before_dt = datetime.fromisoformat(before.replace("Z", "+00:00"))
            query = query.filter(Media.shot_at <= before_dt)
        except Exception:
            pass

    if order.lower() == "asc":
        query = query.order_by(Media.shot_at.asc().nullslast(), Media.id.asc())
    else:
        query = query.order_by(Media.shot_at.desc().nullslast(), Media.id.desc())

    items_raw = query.offset((page - 1) * pageSize).limit(pageSize).all()

    def _serialize(media) -> dict:
        source_type = media.source_type
        source_label = {
            "local": "Local Import",
            "google_photos": "Google Photos",
        }.get(source_type, source_type or "unknown")
        account_email = media.account.email if getattr(media, "account", None) else None
        media_tags = sorted(media.tags, key=lambda t: (t.name or "").lower())
        return {
            "id": media.id,
            "filename": media.filename,
            "shot_at": (
                media.shot_at.isoformat().replace("+00:00", "Z") if media.shot_at else None
            ),
            "mime_type": media.mime_type,
            "width": media.width,
            "height": media.height,
            "is_video": int(bool(media.is_video)),
            "has_playback": int(bool(media.has_playback)),
            "bytes": media.bytes,
            "source_type": source_type,
            "source_label": source_label,
            "account_id": media.account_id,
            "account_email": account_email,
            "camera_make": media.camera_make,
            "camera_model": media.camera_model,
            "tags": [_serialize_tag(t) for t in media_tags],
        }

    items = [_serialize(m) for m in items_raw]
    logger.info("media.list.success trace=%s count=%d", trace, len(items))
    return {
        "items": items,
        "page": page,
        "pageSize": pageSize,
        "server_time": utc_now_isoformat(),
    }


# ---------------------------------------------------------------------------
# 重複候補
# ---------------------------------------------------------------------------


@router.get("/media/duplicates")
async def api_media_duplicates(
    limit: int = Query(100, ge=1, le=500),
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """重複候補のメディアをグループ化して返す。"""
    from bounded_contexts.photonest.infrastructure.photo_models import Media
    from sqlalchemy import or_

    if not principal.can("media:view"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "forbidden", "message": "You do not have permission to view media."},
        )

    not_deleted = or_(Media.is_deleted.is_(False), Media.is_deleted.is_(None))

    exact_hashes = [
        row[0]
        for row in (
            db.query(Media.hash_sha256)
            .filter(not_deleted, Media.hash_sha256.isnot(None))
            .group_by(Media.hash_sha256)
            .having(func.count(Media.id) > 1)
            .order_by(func.count(Media.id).desc())
            .limit(limit)
            .all()
        )
    ]

    similar_filter = [not_deleted, Media.phash.isnot(None)]
    if exact_hashes:
        similar_filter.append(
            or_(Media.hash_sha256.is_(None), Media.hash_sha256.notin_(exact_hashes))
        )
    similar_hashes = [
        row[0]
        for row in (
            db.query(Media.phash)
            .filter(*similar_filter)
            .group_by(Media.phash)
            .having(func.count(Media.id) > 1)
            .order_by(func.count(Media.id).desc())
            .limit(limit)
            .all()
        )
    ]

    def _dup_member(m) -> dict:
        return {
            "id": m.id,
            "filename": m.filename,
            "thumbnail_url": f"/api/media/{m.id}/thumbnail?size=512",
            "width": m.width,
            "height": m.height,
            "bytes": m.bytes,
            "is_video": int(bool(m.is_video)),
            "source_type": m.source_type,
            "source_label": {"local": "Local Import", "google_photos": "Google Photos"}.get(
                m.source_type, m.source_type or "unknown"
            ),
            "shot_at": m.shot_at.isoformat().replace("+00:00", "Z") if m.shot_at else None,
            "imported_at": (
                m.imported_at.isoformat().replace("+00:00", "Z") if m.imported_at else None
            ),
        }

    groups: list[dict] = []

    for digest in exact_hashes:
        members = (
            db.query(Media)
            .filter(not_deleted, Media.hash_sha256 == digest)
            .order_by(Media.imported_at.asc(), Media.id.asc())
            .all()
        )
        if len(members) < 2:
            continue
        groups.append({
            "key": f"sha256:{digest}",
            "match_type": "exact",
            "count": len(members),
            "items": [_dup_member(m) for m in members],
        })

    for digest in similar_hashes:
        q2 = db.query(Media).filter(not_deleted, Media.phash == digest)
        if exact_hashes:
            from sqlalchemy import or_
            q2 = q2.filter(
                or_(Media.hash_sha256.is_(None), Media.hash_sha256.notin_(exact_hashes))
            )
        members = q2.order_by(Media.imported_at.asc(), Media.id.asc()).all()
        if len(members) < 2:
            continue
        groups.append({
            "key": f"phash:{digest}",
            "match_type": "similar",
            "count": len(members),
            "items": [_dup_member(m) for m in members],
        })

    return {"groups": groups, "group_count": len(groups)}


# ---------------------------------------------------------------------------
# メディア詳細・更新・削除
# ---------------------------------------------------------------------------


@router.get("/media/{media_id}")
async def api_media_detail(
    media_id: int,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """メディア詳細を返す。"""
    from bounded_contexts.photonest.infrastructure.photo_models import Media

    media = (
        db.query(Media)
        .options(joinedload(Media.tags), joinedload(Media.sidecars), joinedload(Media.playbacks))
        .filter(Media.id == media_id)
        .first()
    )
    if not media or media.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "not_found"},
        )

    data = _serialize_media_detail(media)
    data["server_time"] = utc_now_isoformat()
    return data


@router.patch("/media/{media_id}")
async def api_media_update_metadata(
    media_id: int,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """メディアのメタデータを更新する（media:metadata-manage 権限が必要）。"""
    from bounded_contexts.photonest.infrastructure.photo_models import Media

    if not principal.can("media:metadata-manage"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "forbidden", "message": "You do not have permission to update the shooting date."},
        )

    media = db.get(Media, media_id)
    if not media or media.is_deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "not_found"})

    payload = await request.json()
    if "shot_at" not in payload:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "shot_at_required"},
        )

    shot_at_value = payload.get("shot_at")
    if shot_at_value is None:
        normalized_shot_at: Optional[datetime] = None
    elif isinstance(shot_at_value, str):
        candidate = shot_at_value.strip()
        if not candidate:
            normalized_shot_at = None
        else:
            try:
                parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={"error": "invalid_shot_at"},
                )
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            normalized_shot_at = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_shot_at"},
        )

    media.shot_at = normalized_shot_at
    media.updated_at = datetime.now(timezone.utc)

    try:
        db.commit()
    except Exception as exc:
        logger.exception("Failed to update media metadata: media_id=%s", media_id)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "update_failed", "message": "Failed to update media metadata."},
        )

    db.refresh(media)
    return {"media": _serialize_media_detail(media)}


@router.delete("/media/{media_id}")
async def api_media_delete(
    media_id: int,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """メディアをソフト削除する（media:delete 権限が必要）。"""
    from bounded_contexts.photonest.infrastructure.photo_models import Media

    if not principal.can("media:delete"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "forbidden", "message": "You do not have permission to delete media."},
        )

    media = db.get(Media, media_id)
    if not media or media.is_deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "not_found"})

    now = datetime.now(timezone.utc)
    _soft_delete_media(media, db, now=now)
    db.commit()
    logger.info("media.delete: media_id=%s user_id=%s", media_id, principal.id)
    return {"result": "deleted"}


# ---------------------------------------------------------------------------
# バルクアクション
# ---------------------------------------------------------------------------


@router.post("/media/bulk-actions")
async def api_media_bulk_actions(
    request: Request,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """複数メディアへの一括操作（削除・タグ追加・タグ削除）。"""
    from bounded_contexts.photonest.infrastructure.photo_models import Media, Tag

    payload = await request.json()

    media_ids_raw = payload.get("media_ids")
    if not isinstance(media_ids_raw, list) or not media_ids_raw:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "media_ids_required", "message": "Bulk action requires at least one media id."},
        )

    normalized_media_ids: list[int] = []
    seen_media_ids: set[int] = set()
    for raw_id in media_ids_raw:
        try:
            mid = int(raw_id)
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "invalid_media_id", "message": "Media id must be an integer."},
            )
        if mid not in seen_media_ids:
            seen_media_ids.add(mid)
            normalized_media_ids.append(mid)

    action = payload.get("action")
    valid_actions = {"delete", "add_tags", "remove_tags"}
    if action not in valid_actions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_action", "message": "Unsupported bulk action."},
        )

    target_tags: list = []
    if action == "delete":
        if not principal.can("media:delete"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error": "forbidden", "message": "You do not have permission to delete media."},
            )
    else:
        if not principal.can("media:tag-manage"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error": "forbidden", "message": "You do not have permission to manage media tags."},
            )

        tag_ids_raw = payload.get("tag_ids")
        if not isinstance(tag_ids_raw, list) or not tag_ids_raw:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "tag_ids_required", "message": "Tag ids are required for this action."},
            )

        normalized_tag_ids: list[int] = []
        seen_tag_ids: set[int] = set()
        for raw_tid in tag_ids_raw:
            try:
                tid = int(raw_tid)
            except (TypeError, ValueError):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={"error": "invalid_tag_id", "message": "Tag id must be an integer."},
                )
            if tid not in seen_tag_ids:
                seen_tag_ids.add(tid)
                normalized_tag_ids.append(tid)

        target_tags = db.query(Tag).filter(Tag.id.in_(normalized_tag_ids)).all()
        found_tag_ids = {tag.id for tag in target_tags}
        missing_tag_ids = [tid for tid in normalized_tag_ids if tid not in found_tag_ids]
        if missing_tag_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "unknown_tag", "missing": missing_tag_ids, "message": "Some tags were not found."},
            )

    medias = (
        db.query(Media)
        .options(joinedload(Media.tags))
        .filter(Media.id.in_(normalized_media_ids))
        .all()
    )
    media_by_id = {m.id: m for m in medias if not m.is_deleted}
    ordered_medias: list = []
    for mid in normalized_media_ids:
        m = media_by_id.get(mid)
        if not m:
            missing_ids = [x for x in normalized_media_ids if x not in media_by_id]
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": "media_not_found",
                    "missing": missing_ids,
                    "message": "Some media items were not found or already deleted.",
                },
            )
        ordered_medias.append(m)

    now = datetime.now(timezone.utc)

    if action == "delete":
        for m in ordered_medias:
            _soft_delete_media(m, db, now=now)
        db.commit()
        logger.info("media.bulk.delete: ids=%s user_id=%s", normalized_media_ids, principal.id)
        return {"result": "deleted", "deleted_ids": normalized_media_ids}

    tag_map = {tag.id: tag for tag in target_tags}
    changed_medias: list = []

    if action == "add_tags":
        for m in ordered_medias:
            existing_ids = {t.id for t in m.tags}
            changed = False
            for tag in target_tags:
                if tag.id not in existing_ids:
                    m.tags.append(tag)
                    changed = True
            if changed:
                m.updated_at = now
                changed_medias.append(m)
        if changed_medias:
            db.flush()
        db.commit()
        return {
            "result": "updated",
            "media": [
                {
                    "id": m.id,
                    "tags": [_serialize_tag(t) for t in sorted(m.tags, key=lambda t: (t.name or "").lower())],
                }
                for m in changed_medias
            ],
        }

    # remove_tags
    target_tag_ids = set(tag_map.keys())
    removed_tag_ids: set[int] = set()
    for m in ordered_medias:
        changed = False
        for tag in list(m.tags):
            if tag.id in target_tag_ids:
                m.tags.remove(tag)
                removed_tag_ids.add(tag.id)
                changed = True
        if changed:
            m.updated_at = now
            changed_medias.append(m)

    if changed_medias:
        db.flush()
        if removed_tag_ids:
            _remove_unused_tags(db, removed_tag_ids)
    db.commit()

    return {
        "result": "updated",
        "media": [
            {
                "id": m.id,
                "tags": [_serialize_tag(t) for t in sorted(m.tags, key=lambda t: (t.name or "").lower())],
            }
            for m in changed_medias
        ],
    }


# ---------------------------------------------------------------------------
# サムネイル / 署名付き URL
# ---------------------------------------------------------------------------


@router.get("/media/{media_id}/thumbnail")
async def api_media_thumbnail(
    media_id: int,
    size: int = Query(256, description="サムネイルサイズ（256, 512, 1024, 2048）"),
    request: Request = None,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """サムネイル画像を返す。"""
    from bounded_contexts.photonest.infrastructure.photo_models import Media
    from bounded_contexts.storage import StorageDomain

    if size not in (256, 512, 1024, 2048):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_size"},
        )

    media = db.get(Media, media_id)
    if not media:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "not_found"})
    if media.is_deleted:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail={"error": "gone"})

    rel_candidates = _thumbnail_rel_path_candidates(media)
    if not rel_candidates:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "not_found"})

    resolved_rel: Optional[str] = None
    resolved_file = None

    for candidate in rel_candidates:
        cand_str = candidate.as_posix()
        current = _resolve_storage_file(StorageDomain.MEDIA_THUMBNAILS, str(size), cand_str)
        if current.exists and current.absolute_path:
            resolved_rel = cand_str
            resolved_file = current
            break

    if not resolved_file or not resolved_file.absolute_path or not resolved_rel:
        triggered, celery_task_id = _trigger_thumbnail_regeneration(
            media_id, reason="api_thumbnail_missing", principal_id=principal.id
        )
        payload: dict[str, Any] = {"error": "not_found", "thumbnailJobTriggered": triggered}
        if celery_task_id:
            payload["thumbnailJobId"] = celery_task_id
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=payload)

    abs_path = resolved_file.absolute_path
    ct = mimetypes.guess_type(abs_path)[0] or media.mime_type or "application/octet-stream"
    ttl = settings.media_thumbnail_url_ttl_seconds

    if settings.media_accel_redirect_enabled:
        rel_path_from_thumbs = os.path.relpath(abs_path, settings.media_thumbs_directory)
        accel_target = posixpath.join(
            settings.media_accel_thumbnails_location.rstrip("/"), rel_path_from_thumbs
        )
        return Response(
            content=b"",
            media_type=ct,
            headers={
                "X-Accel-Redirect": accel_target,
                "Cache-Control": f"private, max-age={ttl}",
            },
        )

    service = _storage_service()
    with service.open(abs_path, "rb") as f:
        data = f.read()
    return Response(
        content=data,
        media_type=ct,
        headers={
            "Content-Length": str(service.size(abs_path)),
            "Cache-Control": f"private, max-age={ttl}",
        },
    )


@router.post("/media/{media_id}/thumb-url")
async def api_media_thumb_url(
    media_id: int,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """署名付きサムネイル URL を返す。"""
    from bounded_contexts.photonest.infrastructure.photo_models import Media
    from bounded_contexts.storage import StorageDomain

    body = await request.json()
    size = body.get("size")
    if size not in (256, 512, 1024, 2048):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_size"},
        )

    media = db.get(Media, media_id)
    if not media:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "not_found"})
    if media.is_deleted:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail={"error": "gone"})

    rel_candidates = _thumbnail_rel_path_candidates(media)
    if not rel_candidates:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "not_found"})

    resolved_rel: Optional[str] = None
    resolved_file = None

    for candidate in rel_candidates:
        cand_str = candidate.as_posix()
        current = _resolve_storage_file(StorageDomain.MEDIA_THUMBNAILS, str(size), cand_str)
        if current.exists and current.absolute_path:
            resolved_rel = cand_str
            resolved_file = current
            break

    if not resolved_file or not resolved_file.absolute_path or not resolved_rel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "not_found"})

    token_path = f"thumbs/{size}/{resolved_rel}"
    ct = (
        mimetypes.guess_type(resolved_file.absolute_path)[0]
        or media.mime_type
        or "application/octet-stream"
    )
    ttl = settings.media_thumbnail_url_ttl_seconds
    exp, max_age = _cacheable_signed_exp(ttl)
    token_payload = {
        "v": 1,
        "typ": "thumb",
        "mid": media_id,
        "size": size,
        "path": token_path,
        "ct": ct,
        "exp": exp,
    }
    token = _sign_payload(token_payload)
    expires_at = (
        datetime.fromtimestamp(exp, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    )
    logger.info("url.thumb.issue: mid=%s size=%s ttl=%s", media_id, size, ttl)
    return {
        "url": f"/api/dl/{token}",
        "expiresAt": expires_at,
        "cacheControl": f"private, max-age={max_age}",
    }


@router.post("/media/{media_id}/recover")
async def api_media_recover(
    media_id: int,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """メディアのメタデータを再取得して復元する（media:recover 権限が必要）。"""
    from bounded_contexts.photonest.infrastructure.photo_models import Media
    from bounded_contexts.storage import StorageDomain
    from bounded_contexts.photonest.tasks.local_import import (
        SUPPORTED_EXTENSIONS,
        refresh_media_metadata_from_original,
    )

    if not principal.can("media:recover"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "forbidden"},
        )

    media = db.get(Media, media_id)
    if not media:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "not_found"})
    if media.is_deleted:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail={"error": "gone"})

    rel_path = _normalize_rel_path(media.local_rel_path)
    if not rel_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "source_missing"},
        )

    resolved = _resolve_storage_file(StorageDomain.MEDIA_ORIGINALS, rel_path.as_posix())
    if not resolved.exists or not resolved.absolute_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "source_missing"},
        )

    abs_path = resolved.absolute_path
    base_dir = resolved.base_path
    file_extension = Path(abs_path).suffix.lower()
    if file_extension not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "unsupported_extension"},
        )

    try:
        refreshed = refresh_media_metadata_from_original(
            media,
            originals_dir=base_dir or os.path.dirname(abs_path),
            fallback_path=abs_path,
            file_extension=file_extension,
            session_id="ui_recover",
            preserve_original_path=True,
        )
    except Exception as exc:
        logger.exception("Metadata refresh failed during recovery: media_id=%s", media_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "refresh_failed"},
        )

    if not refreshed:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "refresh_failed"},
        )

    db.refresh(media)

    changed = False
    if not media.thumbnail_rel_path and media.local_rel_path:
        media.thumbnail_rel_path = media.local_rel_path
        changed = True
    if changed:
        db.add(media)
        db.commit()
        db.refresh(media)

    triggered, celery_task_id = _trigger_thumbnail_regeneration(
        media.id, reason="ui_recover", principal_id=principal.id
    )

    response_body: dict[str, Any] = {
        "result": "ok",
        "media": _serialize_media_detail(media),
        "metadataRefreshed": True,
        "thumbnailJobTriggered": triggered,
    }
    if celery_task_id:
        response_body["thumbnailJobId"] = celery_task_id
    return response_body


@router.post("/media/{media_id}/original-url")
async def api_media_original_url(
    media_id: int,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """署名付きオリジナル URL を返す。"""
    from bounded_contexts.photonest.infrastructure.photo_models import Media
    from bounded_contexts.storage import StorageDomain

    media = db.get(Media, media_id)
    if not media:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "not_found"})
    if media.is_deleted:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail={"error": "gone"})

    rel_path = _normalize_rel_path(media.local_rel_path)
    if not rel_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "not_found"})

    rel_str = rel_path.as_posix()
    token_path = f"originals/{rel_str}"
    resolved = _resolve_storage_file(StorageDomain.MEDIA_ORIGINALS, rel_str)
    if not resolved.exists or not resolved.absolute_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "not_found"})

    ct = (
        mimetypes.guess_type(resolved.absolute_path)[0]
        or media.mime_type
        or "application/octet-stream"
    )
    ttl = settings.media_original_url_ttl_seconds
    exp, max_age = _cacheable_signed_exp(ttl)
    token_payload = {
        "v": 1,
        "typ": "original",
        "mid": media_id,
        "size": None,
        "path": token_path,
        "ct": ct,
        "exp": exp,
    }
    token = _sign_payload(token_payload)
    expires_at = (
        datetime.fromtimestamp(exp, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    )
    logger.info("url.original.issue: mid=%s ttl=%s", media_id, ttl)
    return {
        "url": f"/api/dl/{token}",
        "expiresAt": expires_at,
        "cacheControl": f"private, max-age={max_age}",
    }


@router.post("/media/{media_id}/playback-url")
async def api_media_playback_url(
    media_id: int,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """署名付き再生 URL を返す。"""
    from bounded_contexts.photonest.infrastructure.photo_models import Media, MediaPlayback
    from bounded_contexts.storage import StorageDomain

    media = db.get(Media, media_id)
    if not media or not media.is_video:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "not_found"})
    if media.is_deleted:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail={"error": "gone"})

    pb = (
        db.query(MediaPlayback)
        .filter_by(media_id=media_id, preset="std1080p")
        .first()
    )
    if not pb or pb.status == "error":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "not_found"})
    if pb.status in ("pending", "processing"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"error": "not_ready"})
    if pb.status != "done":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "not_found"})

    token_path = f"playback/{pb.rel_path}"
    resolved = _resolve_storage_file(StorageDomain.MEDIA_PLAYBACK, pb.rel_path)
    if not resolved.exists or not resolved.absolute_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "not_found"})

    ct = mimetypes.guess_type(resolved.absolute_path)[0] or "video/mp4"
    ttl = settings.media_playback_url_ttl_seconds
    exp, max_age = _cacheable_signed_exp(ttl)
    token_payload = {
        "v": 1,
        "typ": "playback",
        "mid": media_id,
        "size": None,
        "path": token_path,
        "ct": ct,
        "exp": exp,
    }
    token = _sign_payload(token_payload)
    expires_at = (
        datetime.fromtimestamp(exp, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    )
    logger.info("url.playback.issue: mid=%s ttl=%s", media_id, ttl)
    return {
        "url": f"/api/dl/{token}",
        "expiresAt": expires_at,
        "cacheControl": f"private, max-age={max_age}",
    }


# ---------------------------------------------------------------------------
# ダウンロード fallback エンドポイント（nginx X-Accel-Redirect 未設定時）
# ---------------------------------------------------------------------------


def _handle_accel_fallback(
    *,
    expected_type: str,
    storage_domain,
    prefix: str,
    rel: str,
    request: Request,
    token: Optional[str],
    db: Session,
) -> Response:
    rel_normalized = rel.strip("/")
    if not rel_normalized:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    segments = rel_normalized.split("/")
    if any(part in ("..", "") for part in segments):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    expected_path = f"{prefix}/{rel_normalized}" if prefix else rel_normalized

    if not token:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    payload, err = _verify_token(token)
    if err or payload.get("typ") != expected_type:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if payload.get("path") != expected_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    resolved = _resolve_storage_file(storage_domain, *segments)
    if not resolved.exists or not resolved.absolute_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    ct = (
        payload.get("ct") if payload else None
    ) or mimetypes.guess_type(resolved.absolute_path)[0] or "application/octet-stream"
    payload["ct"] = ct

    download_filename = _resolve_download_filename(
        payload or {}, rel_normalized, resolved.absolute_path, db
    )
    return _build_file_response(
        payload=payload or {},
        resolved=resolved,
        rel=rel_normalized,
        content_type=ct,
        download_filename=download_filename,
        accel_target=None,
        request=request,
        db=db,
    )


@router.api_route("/media/thumbs/{rel:path}", methods=["GET", "HEAD"])
async def api_download_thumb_fallback(
    rel: str,
    token: Optional[str] = Query(None),
    request: Request = None,
    db: Session = Depends(get_db),
):
    """サムネイル fallback ダウンロード。"""
    from bounded_contexts.storage import StorageDomain

    return _handle_accel_fallback(
        expected_type="thumb",
        storage_domain=StorageDomain.MEDIA_THUMBNAILS,
        prefix="thumbs",
        rel=rel,
        request=request,
        token=token,
        db=db,
    )


@router.api_route("/media/playback/{rel:path}", methods=["GET", "HEAD"])
async def api_download_playback_fallback(
    rel: str,
    token: Optional[str] = Query(None),
    request: Request = None,
    db: Session = Depends(get_db),
):
    """再生ファイル fallback ダウンロード。"""
    from bounded_contexts.storage import StorageDomain

    return _handle_accel_fallback(
        expected_type="playback",
        storage_domain=StorageDomain.MEDIA_PLAYBACK,
        prefix="playback",
        rel=rel,
        request=request,
        token=token,
        db=db,
    )


@router.api_route("/media/originals/{rel:path}", methods=["GET", "HEAD"])
async def api_download_original_fallback(
    rel: str,
    token: Optional[str] = Query(None),
    request: Request = None,
    db: Session = Depends(get_db),
):
    """オリジナルファイル fallback ダウンロード。"""
    from bounded_contexts.storage import StorageDomain

    return _handle_accel_fallback(
        expected_type="original",
        storage_domain=StorageDomain.MEDIA_ORIGINALS,
        prefix="originals",
        rel=rel,
        request=request,
        token=token,
        db=db,
    )


@router.api_route("/dl/{token:path}", methods=["GET", "HEAD"])
async def api_download(
    token: str,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """署名付きトークンで保護されたメディアファイルをダウンロードする。"""
    from bounded_contexts.storage import StorageDomain

    payload, err = _verify_token(token)
    if err:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": err},
        )

    path = payload.get("path", "")
    ct = payload.get("ct", "application/octet-stream")

    if ".." in path.split("/"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "forbidden"},
        )

    typ = payload.get("typ")
    if typ == "thumb":
        if not path.startswith("thumbs/"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"error": "forbidden"})
        rel = path[len("thumbs/"):]
        resolved = _resolve_storage_file(StorageDomain.MEDIA_THUMBNAILS, *rel.split("/"))
        accel_prefix = settings.media_accel_thumbnails_location
    elif typ == "playback":
        if not path.startswith("playback/"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"error": "forbidden"})
        rel = path[len("playback/"):]
        resolved = _resolve_storage_file(StorageDomain.MEDIA_PLAYBACK, *rel.split("/"))
        accel_prefix = settings.media_accel_playback_location
    elif typ == "original":
        if not path.startswith("originals/"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"error": "forbidden"})
        rel = path[len("originals/"):]
        resolved = _resolve_storage_file(StorageDomain.MEDIA_ORIGINALS, *rel.split("/"))
        accel_prefix = settings.media_accel_originals_location
    else:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"error": "forbidden"})

    if not resolved.exists or not resolved.absolute_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "not_found"})

    abs_path = resolved.absolute_path
    download_filename = _resolve_download_filename(payload, rel, abs_path, db)

    guessed = mimetypes.guess_type(abs_path)[0]
    if guessed != ct:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"error": "forbidden"})

    accel_target: Optional[str] = None
    if settings.media_accel_redirect_enabled:
        accel_target = _build_accel_target(accel_prefix, rel, token)

    return _build_file_response(
        payload=payload,
        resolved=resolved,
        rel=rel,
        content_type=ct,
        download_filename=download_filename,
        accel_target=accel_target,
        request=request,
        db=db,
    )


__all__ = ["router"]
