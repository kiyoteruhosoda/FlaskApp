from datetime import datetime, timezone, timedelta
import base64
import hashlib
import hmac
import json
import mimetypes
import os
import posixpath
import re
import secrets
import time
from pathlib import Path
from urllib.parse import urlencode, quote
from email.utils import formatdate
from uuid import uuid4

from flask import (
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
    flash,
    g,
)
from flask_login import login_required, logout_user
from flask_babel import gettext as _
from functools import wraps

from . import bp
from ..extensions import db
from core.models.google_account import GoogleAccount
from core.models.picker_session import PickerSession
from core.models.photo_models import (
    Media,
    Album,
    Exif,
    MediaSidecar,
    MediaPlayback,
    Tag,
    PickerSelection,
    album_item,
    media_tag,
)
from core.models.user import User, Role
from core.crypto import decrypt
from ..auth.utils import refresh_google_token, RefreshTokenError, log_requests_and_send
from ..auth.routes import _sync_active_role
from .pagination import PaginationParams, paginate_and_respond
from flask_login import current_user
from application.auth_service import AuthService
from infrastructure.user_repository import SqlAlchemyUserRepository
from ..services.token_service import TokenService
from ..auth.totp import verify_totp
import jwt
from sqlalchemy.orm import joinedload
from sqlalchemy import func, select, case
from werkzeug.utils import secure_filename
from core.storage_paths import (
    first_existing_storage_path,
    resolve_storage_file,
    storage_path_candidates,
)


user_repo = SqlAlchemyUserRepository(db.session)
auth_service = AuthService(user_repo)


VALID_TAG_ATTRS = {"person", "place", "thing"}


def _storage_path_candidates(config_key: str) -> list[str]:
    return storage_path_candidates(config_key)


def _storage_path(config_key: str) -> str | None:
    return first_existing_storage_path(config_key)


def _resolve_storage_file(config_key: str, *path_parts: str) -> tuple[str | None, str | None, bool]:
    return resolve_storage_file(config_key, *path_parts)


def _serialize_user_for_log(user):
    """ユーザー情報を匿名化した形でログ出力用に整形する。"""
    if user is None:
        return None

    identifier_parts = []
    if getattr(user, 'id', None) is not None:
        identifier_parts.append(f"id:{user.id}")
    if getattr(user, 'email', None):
        identifier_parts.append(f"email:{user.email}")
    if getattr(user, 'name', None):
        identifier_parts.append(f"name:{user.name}")

    if not identifier_parts:
        return None

    raw_identifier = "|".join(str(part) for part in identifier_parts)
    digest = hashlib.sha256(raw_identifier.encode('utf-8')).hexdigest()

    snapshot = {'id_hash': digest}

    roles = getattr(user, 'roles', None)
    if roles:
        role_names = [getattr(role, 'name', None) for role in roles if getattr(role, 'name', None)]
        if role_names:
            snapshot['roles'] = role_names

    return snapshot


def _resolve_remote_addr():
    """リクエスト送信元IPアドレスを取得する。"""
    forwarded_for = request.headers.get('X-Forwarded-For')
    if forwarded_for:
        return forwarded_for.split(',')[0].strip()
    return request.remote_addr


def _build_auth_log_context(**extra):
    """認証系ログの共通情報を構築する。"""

    request_id = extra.pop('request_id', None) or request.headers.get('X-Request-ID') or str(uuid4())
    remote_addr = _resolve_remote_addr()

    request_info = {
        'id': request_id,
        'ip': remote_addr,
        'userAgent': request.user_agent.string,
        'path': request.path,
        'method': request.method,
    }

    context = {
        'endpoint': request.endpoint,
        'method': request.method,
        'path': request.path,
        'blueprint': request.blueprint,
        'session_id': session.get('session_id'),
        'request': request_info,
        'remote_addr': remote_addr,
        'user_agent': request.user_agent.string,
    }

    # current_user もしくは g.current_user からユーザー情報を取得
    active_user = current_user if current_user.is_authenticated else getattr(g, 'current_user', None)

    user_snapshot = _serialize_user_for_log(active_user)
    if user_snapshot:
        context['user'] = user_snapshot

    if extra:
        context['extra'] = {k: v for k, v in extra.items() if v is not None}

    return context


def _emit_structured_api_log(message: str, *, level: str, event: str, **extra_context):
    """共通の構造化APIログ出力処理。"""

    context = _build_auth_log_context(**extra_context)
    request_id = None
    if isinstance(context.get('request'), dict):
        request_id = context['request'].get('id')

    payload = {
        'ts': datetime.now(timezone.utc).isoformat(),
        'event': event,
        'level': level.upper(),
        'message': message,
        'requestId': request_id,
        'context': context,
    }

    log_method = getattr(current_app.logger, level, current_app.logger.info)
    log_method(
        json.dumps(payload, ensure_ascii=False, default=str),
        extra={'event': event, 'request_id': request_id},
    )


def _auth_log(message: str, *, level: str = 'info', event: str = 'auth', **extra_context):
    """認証周りのログを構造化して出力する。"""
    _emit_structured_api_log(message, level=level, event=event, **extra_context)


def _local_import_log(message: str, *, level: str = 'info', event: str = 'local_import.api', **extra_context):
    """ローカルインポート関連のAPIログを出力する。"""
    _emit_structured_api_log(message, level=level, event=event, **extra_context)


def jwt_required(f):
    """JWT認証が必要なエンドポイント用のデコレータ"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Authorizationヘッダーからトークンを取得
        auth_header = request.headers.get('Authorization')
        token = None
        
        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]
        elif request.cookies.get('access_token'):
            # Cookieからもトークンを取得（既存の実装との互換性）
            token = request.cookies.get('access_token')
        
        if not token:
            return jsonify({'error': 'token_missing'}), 401
        
        user = TokenService.verify_access_token(token)
        if not user:
            return jsonify({'error': 'invalid_token'}), 401
        
        # Flask-Loginのcurrent_userと同じように使えるよう設定
        from flask import g
        g.current_user = user
        
        return f(*args, **kwargs)
    return decorated_function


def _normalize_rel_path(value: str | None) -> Path | None:
    if not value:
        return None
    normalized = value.lstrip("/\\")
    if not normalized:
        return None
    return Path(normalized)


def _remove_media_files(media: Media) -> None:
    rel_path = _normalize_rel_path(media.local_rel_path)
    if rel_path is None:
        return

    def _unlink(target: Path) -> None:
        try:
            target.unlink()
        except FileNotFoundError:
            return
        except OSError as exc:
            current_app.logger.warning(
                json.dumps(
                    {
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "media_id": media.id,
                        "path": str(target),
                        "error": str(exc),
                    }
                ),
                extra={"event": "media.delete.cleanup_failed"},
            )

    orig_base = _storage_path("FPV_NAS_ORIGINALS_DIR")
    if orig_base:
        _unlink(Path(orig_base) / rel_path)

    thumbs_base = _storage_path("FPV_NAS_THUMBS_DIR")
    if thumbs_base:
        for size in (256, 1024, 2048):
            _unlink(Path(thumbs_base) / str(size) / rel_path)

    play_base = _storage_path("FPV_NAS_PLAY_DIR")
    if play_base:
        for playback in media.playbacks:
            rel = _normalize_rel_path(playback.rel_path)
            if rel:
                _unlink(Path(play_base) / rel)
            poster_rel = _normalize_rel_path(playback.poster_rel_path)
            if poster_rel:
                _unlink(Path(play_base) / poster_rel)


def login_or_jwt_required(f):
    """Flask-LoginまたはJWT認証の両方に対応するデコレータ"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        _auth_log(
            'Authentication check started',
            stage='start',
        )

        if current_app.config.get('LOGIN_DISABLED'):
            _auth_log(
                'Authentication bypassed because LOGIN_DISABLED is active',
                stage='bypass',
            )
            return f(*args, **kwargs)

        # まずFlask-Loginでの認証をチェック
        if current_user.is_authenticated:
            _auth_log(
                'Authentication successful via Flask-Login',
                stage='success',
                auth_method='flask_login',
                authenticated_user=_serialize_user_for_log(current_user),
            )
            return f(*args, **kwargs)

        # Flask-Loginで認証されていない場合、JWTをチェック
        auth_header = request.headers.get('Authorization')
        token_source = None
        token = None

        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]
            token_source = 'authorization_header'
        elif request.cookies.get('access_token'):
            token = request.cookies.get('access_token')
            token_source = 'cookie'

        _auth_log(
            'Flask-Login authentication unavailable; evaluating JWT credentials',
            stage='jwt_check',
            token_source=token_source or 'none',
            has_authorization_header=bool(auth_header),
        )

        if not token:
            _auth_log(
                'JWT token missing',
                level='warning',
                stage='failure',
                reason='token_missing',
                token_source=token_source or 'none',
            )
            return jsonify({'error': 'authentication_required'}), 401

        user = TokenService.verify_access_token(token)
        if not user:
            _auth_log(
                'JWT token verification failed',
                level='warning',
                stage='failure',
                reason='invalid_token',
                token_source=token_source or 'unknown',
            )
            return jsonify({'error': 'invalid_token'}), 401

        # Flask-Loginのcurrent_userと同じように使えるよう設定
        g.current_user = user
        _auth_log(
            'Authentication successful via JWT',
            stage='success',
            auth_method='jwt',
            token_source=token_source or 'unknown',
            authenticated_user=_serialize_user_for_log(user),
        )

        return f(*args, **kwargs)
    return decorated_function


def get_current_user():
    """現在のユーザーを取得（Flask-LoginまたはJWT認証から）"""
    if current_user.is_authenticated:
        return current_user

    from flask import g
    return getattr(g, 'current_user', None)


def require_api_perms(*perm_codes):
    """APIエンドポイント向けの権限チェックデコレータ"""

    def decorator(func):
        @wraps(func)
        @login_or_jwt_required
        def wrapper(*args, **kwargs):
            if current_app.config.get('LOGIN_DISABLED'):
                return func(*args, **kwargs)

            user = get_current_user()
            if not user or not user.can(*perm_codes):
                return jsonify({'error': 'forbidden'}), 403

            return func(*args, **kwargs)

        return wrapper

    return decorator


def _parse_media_ids(raw_value):
    """リクエストペイロードからメディアIDの配列を整形する。"""

    if raw_value is None:
        return []

    if not isinstance(raw_value, (list, tuple)):
        raise ValueError('mediaIds must be a list')

    ordered: list[int] = []
    seen: set[int] = set()
    for item in raw_value:
        if item in (None, ''):
            continue
        try:
            media_id = int(item)
        except (TypeError, ValueError) as exc:
            raise ValueError('mediaIds must contain integers') from exc

        if media_id not in seen:
            seen.add(media_id)
            ordered.append(media_id)

    return ordered


def _load_ordered_media(media_ids: list[int]):
    """指定されたID順にMediaレコードを取得する。"""

    if not media_ids:
        return [], []

    medias = Media.query.filter(Media.id.in_(media_ids)).all()
    media_map = {media.id: media for media in medias}

    ordered: list[Media] = []
    missing: list[int] = []
    for media_id in media_ids:
        media = media_map.get(media_id)
        if media is None:
            missing.append(media_id)
        else:
            ordered.append(media)

    return ordered, missing


def _update_album_sort_indexes(album_id: int, media_ids: list[int]) -> None:
    """アルバム内のメディア順序をsort_indexに保存する。"""

    if not media_ids:
        return

    for position, media_id in enumerate(media_ids):
        db.session.execute(
            album_item.update()
            .where(
                album_item.c.album_id == album_id,
                album_item.c.media_id == media_id,
            )
            .values(sort_index=position)
        )


def _get_album_media_rows(album_id: int):
    """アルバムに紐づくメディア情報を取得する。"""

    return (
        db.session.query(Media, album_item.c.sort_index)
        .join(album_item, album_item.c.media_id == Media.id)
        .filter(album_item.c.album_id == album_id)
        .options(joinedload(Media.tags))
        .order_by(album_item.c.sort_index.asc(), Media.id.asc())
        .all()
    )


def serialize_album_summary(
    album: Album,
    *,
    media_count: int | None = None,
    fallback_cover_id: int | None = None,
    available_media_ids: list[int] | None = None,
) -> dict:
    """アルバム情報をリスト表示向けにシリアライズする。"""

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
        album.created_at.isoformat().replace('+00:00', 'Z')
        if album.created_at
        else None
    )
    updated_at = (
        album.updated_at.isoformat().replace('+00:00', 'Z')
        if album.updated_at
        else None
    )

    return {
        'id': album.id,
        'title': album.name,
        'description': album.description,
        'visibility': album.visibility,
        'coverImageId': cover_id,
        'coverMediaId': cover_id,
        'mediaCount': int(computed_count or 0),
        'createdAt': created_at,
        'lastModified': updated_at,
        'displayOrder': album.display_order,
    }


def _resolve_best_thumbnail_url(media: Media) -> str | None:
    """Return the largest available thumbnail URL for a media item."""

    rel_path = _normalize_rel_path(media.local_rel_path)
    if rel_path is None:
        return None

    thumbs_base = _storage_path("FPV_NAS_THUMBS_DIR")
    if not thumbs_base:
        return None

    for size in (2048, 1024, 512):
        candidate = Path(thumbs_base) / str(size) / rel_path
        if candidate.exists():
            return f"/api/media/{media.id}/thumbnail?size={size}"

    return None


def serialize_album_detail(album: Album, media_rows) -> dict:
    """アルバム詳細情報を構築する。"""

    media_items: list[dict] = []
    fallback_cover_id: int | None = None
    media_ids: list[int] = []

    for media, sort_index in media_rows:
        if fallback_cover_id is None:
            fallback_cover_id = media.id

        media_ids.append(media.id)
        tags = sorted(media.tags, key=lambda t: (t.name or '').lower())
        thumbnail_url = f"/api/media/{media.id}/thumbnail?size=512"
        full_url = _resolve_best_thumbnail_url(media) or thumbnail_url

        media_items.append(
            {
                'id': media.id,
                'filename': media.filename,
                'shotAt': (
                    media.shot_at.isoformat().replace('+00:00', 'Z')
                    if media.shot_at
                    else None
                ),
                'thumbnailUrl': thumbnail_url,
                'fullUrl': full_url,
                'sortIndex': sort_index,
                'tags': [serialize_tag(tag) for tag in tags],
            }
        )

    summary = serialize_album_summary(
        album,
        media_count=len(media_items),
        fallback_cover_id=fallback_cover_id,
        available_media_ids=media_ids,
    )
    summary['coverMediaId'] = summary.get('coverMediaId')
    summary['media'] = media_items
    summary['mediaIds'] = [item['id'] for item in media_items]

    return summary


ALBUM_VISIBILITY_VALUES = {"public", "private", "unlisted"}


@bp.get("/albums")
@require_api_perms("media:view", "album:view")
def api_albums_list():
    """アルバムの一覧をページングして返す。"""

    params = PaginationParams.from_request(default_page_size=24)
    order_value = (params.order or "desc").lower()
    custom_order_requested = order_value == "custom"

    if custom_order_requested:
        params.use_cursor = False

    stats_subquery = (
        db.session.query(
            album_item.c.album_id.label("album_id"),
            func.count(album_item.c.media_id).label("media_count"),
            func.min(album_item.c.media_id).label("first_media_id"),
        )
        .group_by(album_item.c.album_id)
        .subquery()
    )

    query = (
        Album.query
        .outerjoin(stats_subquery, Album.id == stats_subquery.c.album_id)
        .add_columns(
            stats_subquery.c.media_count,
            stats_subquery.c.first_media_id,
        )
    )

    search_text = (request.args.get("q") or "").strip()
    if search_text:
        like_expr = f"%{search_text}%"
        query = query.filter(Album.name.ilike(like_expr))

    if custom_order_requested:
        order_columns = [
            case((Album.display_order.is_(None), 1), else_=0).asc(),
            Album.display_order.asc(),
            Album.created_at.desc(),
            Album.id.desc(),
        ]
        query = query.order_by(*order_columns)
        result = paginate_and_respond(
            query=query,
            params=params,
            serializer_func=lambda row: serialize_album_summary(
                row[0],
                media_count=row[1] or 0,
                fallback_cover_id=row[2],
            ),
            id_column=None,
            created_at_column=None,
            count_total=False,
            default_page_size=24,
        )
    else:
        result = paginate_and_respond(
            query=query,
            params=params,
            serializer_func=lambda row: serialize_album_summary(
                row[0],
                media_count=row[1] or 0,
                fallback_cover_id=row[2],
            ),
            id_column=Album.id,
            created_at_column=Album.created_at,
            count_total=False,
            default_page_size=24,
        )

    return jsonify(result)


@bp.get("/albums/<int:album_id>")
@require_api_perms("media:view", "album:view")
def api_album_detail(album_id: int):
    """アルバム詳細情報を取得する。"""

    requester = get_current_user()
    requester_info = None
    if requester:
        requester_info = {
            "id": getattr(requester, "id", None),
            "email": getattr(requester, "email", None),
        }

    log_context = {
        "event": "album.detail.fetch",
        "album_id": album_id,
        "requested_by": requester_info,
    }

    current_app.logger.info(
        json.dumps({**log_context, "stage": "start"}),
        extra={"event": "album.detail.fetch"},
    )

    try:
        album = Album.query.get(album_id)
    except Exception as exc:  # pragma: no cover - unexpected database failure
        current_app.logger.exception(
            json.dumps({**log_context, "stage": "query_failed", "error": str(exc)}),
            extra={"event": "album.detail.fetch"},
        )
        raise

    if not album:
        current_app.logger.warning(
            json.dumps({**log_context, "stage": "not_found"}),
            extra={"event": "album.detail.fetch"},
        )
        return (
            jsonify({"error": "not_found", "message": _("Album not found.")}),
            404,
        )

    try:
        media_rows = _get_album_media_rows(album_id)
        detail = serialize_album_detail(album, media_rows)
    except Exception as exc:  # pragma: no cover - unexpected serialization failure
        current_app.logger.exception(
            json.dumps({**log_context, "stage": "serialization_failed", "error": str(exc)}),
            extra={"event": "album.detail.fetch"},
        )
        raise

    current_app.logger.info(
        json.dumps(
            {
                **log_context,
                "stage": "success",
                "media_count": len(media_rows),
                "visibility": album.visibility,
                "cover_media_id": detail.get("coverMediaId"),
            }
        ),
        extra={"event": "album.detail.fetch"},
    )

    return jsonify({"album": detail})


@bp.post("/albums")
@require_api_perms("album:create")
def api_album_create():
    """アルバムを新規作成する。"""

    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    description = (payload.get("description") or "").strip()
    visibility = (payload.get("visibility") or "private").strip().lower()

    if not name:
        return (
            jsonify({"error": "name_required", "message": _("Album name is required.")}),
            400,
        )

    if visibility not in ALBUM_VISIBILITY_VALUES:
        return (
            jsonify({"error": "invalid_visibility", "message": _("Invalid album visibility value.")}),
            400,
        )

    try:
        media_ids = _parse_media_ids(payload.get("mediaIds"))
    except ValueError:
        return (
            jsonify(
                {
                    "error": "invalid_media_ids",
                    "message": _("Invalid media selection payload."),
                }
            ),
            400,
        )

    cover_media_raw = payload.get("coverMediaId")
    if cover_media_raw in (None, ""):
        cover_media_id = None
    else:
        try:
            cover_media_id = int(cover_media_raw)
        except (TypeError, ValueError):
            return (
                jsonify({"error": "invalid_cover", "message": _("Cover media id must be an integer.")}),
                400,
            )

    ordered_medias, missing_ids = _load_ordered_media(media_ids)
    if missing_ids:
        return (
            jsonify(
                {
                    "error": "invalid_media",
                    "message": _("Some selected media could not be found."),
                    "missingMediaIds": missing_ids,
                }
            ),
            400,
        )

    if cover_media_id and cover_media_id not in media_ids:
        return (
            jsonify(
                {
                    "error": "invalid_cover",
                    "message": _("Cover image must be one of the selected media items."),
                }
            ),
            400,
        )

    now = datetime.now(timezone.utc)
    album = Album(
        name=name,
        description=description or None,
        visibility=visibility,
        cover_media_id=cover_media_id,
        created_at=now,
        updated_at=now,
    )
    db.session.add(album)
    db.session.flush()

    album.media = ordered_medias
    db.session.flush()
    _update_album_sort_indexes(album.id, media_ids)

    if not album.cover_media_id and media_ids:
        album.cover_media_id = media_ids[0]

    album.updated_at = now
    db.session.commit()

    detail = serialize_album_detail(album, _get_album_media_rows(album.id))
    return jsonify({"album": detail, "created": True}), 201


@bp.put("/albums/<int:album_id>")
@require_api_perms("album:edit")
def api_album_update(album_id: int):
    """アルバム情報を更新する。"""

    album = Album.query.get(album_id)
    if not album:
        return (
            jsonify({"error": "not_found", "message": _("Album not found.")}),
            404,
        )

    payload = request.get_json(silent=True) or {}

    name = payload.get("name")
    description = payload.get("description")
    visibility = payload.get("visibility")
    media_ids_raw = payload.get("mediaIds")
    cover_media_raw = payload.get("coverMediaId") if "coverMediaId" in payload else None

    has_changes = False

    if isinstance(name, str):
        stripped = name.strip()
        if not stripped:
            return (
                jsonify({"error": "name_required", "message": _("Album name is required.")}),
                400,
            )
        if stripped != album.name:
            album.name = stripped
            has_changes = True

    if isinstance(description, str):
        normalized_desc = description.strip() or None
        if normalized_desc != album.description:
            album.description = normalized_desc
            has_changes = True

    if isinstance(visibility, str):
        vis_value = visibility.strip().lower()
        if vis_value not in ALBUM_VISIBILITY_VALUES:
            return (
                jsonify({"error": "invalid_visibility", "message": _("Invalid album visibility value.")}),
                400,
            )
        if vis_value != album.visibility:
            album.visibility = vis_value
            has_changes = True

    if media_ids_raw is not None:
        try:
            media_ids = _parse_media_ids(media_ids_raw)
        except ValueError:
            return (
                jsonify(
                    {
                        "error": "invalid_media_ids",
                        "message": _("Invalid media selection payload."),
                    }
                ),
                400,
            )

        ordered_medias, missing_ids = _load_ordered_media(media_ids)
        if missing_ids:
            return (
                jsonify(
                    {
                        "error": "invalid_media",
                        "message": _("Some selected media could not be found."),
                        "missingMediaIds": missing_ids,
                    }
                ),
                400,
            )

        album.media = ordered_medias
        db.session.flush()
        _update_album_sort_indexes(album.id, media_ids)
        has_changes = True
        current_media_ids = media_ids
    else:
        current_media_ids = [media.id for media in album.media]

    if album.cover_media_id and album.cover_media_id not in current_media_ids:
        album.cover_media_id = current_media_ids[0] if current_media_ids else None
        has_changes = True

    if "coverMediaId" in payload:
        if cover_media_raw in (None, ""):
            cover_media_id = None
        else:
            try:
                cover_media_id = int(cover_media_raw)
            except (TypeError, ValueError):
                return (
                    jsonify({"error": "invalid_cover", "message": _("Cover media id must be an integer.")}),
                    400,
                )

        if cover_media_id and cover_media_id not in current_media_ids:
            return (
                jsonify(
                    {
                        "error": "invalid_cover",
                        "message": _("Cover image must be one of the selected media items."),
                    }
                ),
                400,
            )

        if cover_media_id != album.cover_media_id:
            album.cover_media_id = cover_media_id
            has_changes = True

    if not album.cover_media_id and current_media_ids:
        album.cover_media_id = current_media_ids[0]

    now = datetime.now(timezone.utc)
    if has_changes:
        album.updated_at = now

    db.session.commit()

    detail = serialize_album_detail(album, _get_album_media_rows(album.id))
    return jsonify({"album": detail, "updated": has_changes})


@bp.put("/albums/<int:album_id>/media/order")
@require_api_perms("album:edit")
def api_album_media_reorder(album_id: int):
    """アルバム内のメディア表示順を更新する。"""

    album = Album.query.get(album_id)
    if not album:
        return (
            jsonify({"error": "not_found", "message": _("Album not found.")}),
            404,
        )

    payload = request.get_json(silent=True) or {}
    media_ids_raw = payload.get("mediaIds")

    if not isinstance(media_ids_raw, list):
        return (
            jsonify(
                {
                    "error": "invalid_media_order",
                    "message": _("Media order payload must be a list of media ids."),
                }
            ),
            400,
        )

    normalized_ids: list[int] = []
    seen: set[int] = set()

    try:
        for value in media_ids_raw:
            media_id = int(value)
            if media_id in seen:
                raise ValueError("duplicate media id")
            seen.add(media_id)
            normalized_ids.append(media_id)
    except (TypeError, ValueError):
        return (
            jsonify(
                {
                    "error": "invalid_media_order",
                    "message": _("Media order payload must include each album media id exactly once."),
                }
            ),
            400,
        )

    media_rows = _get_album_media_rows(album_id)
    current_media_ids = [media.id for media, _ in media_rows]

    if not normalized_ids:
        if current_media_ids:
            return (
                jsonify(
                    {
                        "error": "invalid_media_order",
                        "message": _("Media order payload must include every media id currently in the album."),
                    }
                ),
                400,
            )

        detail = serialize_album_detail(album, media_rows)
        return jsonify({"updated": False, "album": detail})

    if len(normalized_ids) != len(current_media_ids) or set(normalized_ids) != set(current_media_ids):
        return (
            jsonify(
                {
                    "error": "invalid_media_order",
                    "message": _("Media order payload must include every media id currently in the album."),
                }
            ),
            400,
        )

    if normalized_ids == current_media_ids:
        detail = serialize_album_detail(album, media_rows)
        return jsonify({"updated": False, "album": detail})

    _update_album_sort_indexes(album.id, normalized_ids)
    album.updated_at = datetime.now(timezone.utc)
    db.session.commit()

    detail = serialize_album_detail(album, _get_album_media_rows(album.id))
    return jsonify({"updated": True, "album": detail})


@bp.put("/albums/order")
@require_api_perms("album:edit")
def api_albums_reorder():
    """アルバムの表示順序を更新する。"""

    payload = request.get_json(silent=True) or {}
    album_ids_raw = payload.get("albumIds")

    if not isinstance(album_ids_raw, list) or not album_ids_raw:
        return (
            jsonify(
                {
                    "error": "invalid_payload",
                    "message": _("Album order payload must include at least one album id."),
                }
            ),
            400,
        )

    normalized_ids = []
    seen = set()

    try:
        for value in album_ids_raw:
            album_id = int(value)
            if album_id in seen:
                continue
            normalized_ids.append(album_id)
            seen.add(album_id)
    except (TypeError, ValueError):
        return (
            jsonify(
                {
                    "error": "invalid_payload",
                    "message": _("Album order payload must include integer ids."),
                }
            ),
            400,
        )

    if not normalized_ids:
        return (
            jsonify(
                {
                    "error": "invalid_payload",
                    "message": _("Album order payload must include at least one album id."),
                }
            ),
            400,
        )

    albums = Album.query.filter(Album.id.in_(normalized_ids)).all()
    album_by_id = {album.id: album for album in albums}
    missing_ids = [album_id for album_id in normalized_ids if album_id not in album_by_id]

    if missing_ids:
        return (
            jsonify(
                {
                    "error": "invalid_album",
                    "message": _("Some specified albums could not be found."),
                    "missingAlbumIds": missing_ids,
                }
            ),
            400,
        )

    now = datetime.now(timezone.utc)
    updated_count = 0

    for index, album_id in enumerate(normalized_ids):
        album = album_by_id[album_id]
        if album.display_order != index:
            album.display_order = index
            album.updated_at = now
            updated_count += 1

    if updated_count:
        db.session.commit()
    else:
        db.session.rollback()

    return jsonify({"updated": bool(updated_count), "albumIds": normalized_ids})


@bp.delete("/albums/<int:album_id>")
@require_api_perms("album:edit")
def api_album_delete(album_id: int):
    """アルバムを削除する。"""

    album = Album.query.get(album_id)
    if not album:
        return (
            jsonify({"error": "not_found", "message": _("Album not found.")}),
            404,
        )

    db.session.delete(album)
    db.session.commit()

    return jsonify({"result": "deleted"})


@bp.post("/login")
def api_login():
    """ユーザー認証してJWTを発行"""
    data = request.get_json(silent=True) or {}
    email = data.get("email")
    password = data.get("password")
    token = data.get("token")
    user_model = auth_service.authenticate(email, password)
    if not user_model:
        return jsonify({"error": "invalid_credentials"}), 401

    if user_model.totp_secret:
        if not token:
            return jsonify({"error": "totp_required"}), 401
        if not verify_totp(user_model.totp_secret, token):
            return jsonify({"error": "invalid_totp"}), 401

    # TokenServiceを使用してトークンペアを生成
    access_token, refresh_token = TokenService.generate_token_pair(user_model)

    session.pop("active_role_id", None)
    roles = list(getattr(user_model, "roles", []) or [])

    raw_next = data.get("next") or request.args.get("next")
    if isinstance(raw_next, str) and raw_next.startswith("/") and not raw_next.startswith("//"):
        redirect_target = raw_next
    else:
        redirect_target = url_for("feature_x.dashboard")

    if len(roles) > 1:
        session["role_selection_next"] = redirect_target
        response_payload = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "requires_role_selection": True,
            "redirect_url": url_for("auth.select_role"),
        }
    else:
        _sync_active_role(user_model)
        response_payload = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "requires_role_selection": False,
            "redirect_url": redirect_target,
        }

    resp = jsonify(response_payload)
    resp.set_cookie(
        "access_token",
        access_token,
        httponly=True,
        secure=current_app.config.get("SESSION_COOKIE_SECURE", False),
        samesite="Lax",
    )
    return resp


@bp.post("/logout")
@login_or_jwt_required
def api_logout():
    """JWT Cookieを削除し、リフレッシュトークンを無効化"""
    user = get_current_user()
    if user:
        TokenService.revoke_refresh_token(user)

    if current_user.is_authenticated:
        logout_user()

    session.pop("picker_session_id", None)

    resp = jsonify({"result": "ok"})
    resp.delete_cookie("access_token")
    return resp


@bp.post("/refresh")
def api_refresh():
    """リフレッシュトークンから新しいアクセス・リフレッシュトークンを発行"""
    data = request.get_json(silent=True) or {}
    refresh_token = data.get("refresh_token")
    
    if not refresh_token:
        return jsonify({"error": "missing_refresh_token"}), 400
    
    # TokenServiceを使用してトークンをリフレッシュ
    token_pair = TokenService.refresh_tokens(refresh_token)
    if not token_pair:
        return jsonify({"error": "invalid_token"}), 401
    
    access_token, new_refresh_token = token_pair
    
    resp = jsonify({"access_token": access_token, "refresh_token": new_refresh_token})
    resp.set_cookie(
        "access_token",
        access_token,
        httponly=True,
        secure=current_app.config.get("SESSION_COOKIE_SECURE", False),
        samesite="Lax",
    )
    return resp


REQUIRED_GOOGLE_OAUTH_SCOPES = {
    "https://www.googleapis.com/auth/userinfo.email",
}

GOOGLE_OAUTH_SCOPE_SETS = {
    "photo_picker": {
        "https://www.googleapis.com/auth/photospicker.mediaitems.readonly",
        "https://www.googleapis.com/auth/photoslibrary.readonly.appcreateddata",
        "https://www.googleapis.com/auth/photoslibrary.appendonly",
    },
}


@bp.post("/google/oauth/start")
@login_or_jwt_required
def google_oauth_start():
    """Start Google OAuth flow by returning an authorization URL."""
    data = request.get_json(silent=True) or {}
    scopes = set(data.get("scopes") or [])
    scope_profile = data.get("scope_profile")

    if scope_profile:
        profile_scopes = GOOGLE_OAUTH_SCOPE_SETS.get(scope_profile)
        if profile_scopes is None:
            return (
                jsonify({"error": "invalid_scope_profile", "scope_profile": scope_profile}),
                400,
            )
        scopes.update(profile_scopes)

    scopes.update(REQUIRED_GOOGLE_OAUTH_SCOPES)
    sorted_scopes = sorted(scopes)
    redirect_target = data.get("redirect")
    state = secrets.token_urlsafe(16)
    session["google_oauth_state"] = {
        "state": state,
        "scopes": sorted_scopes,
        "redirect": redirect_target,
    }
    
    # デバッグ情報を追加
    current_app.logger.info(f"OAuth start - Headers: {dict(request.headers)}")
    current_app.logger.info(f"OAuth start - PREFERRED_URL_SCHEME: {current_app.config.get('PREFERRED_URL_SCHEME')}")
    
    callback_url = url_for("auth.google_oauth_callback", _external=True)
    current_app.logger.info(f"OAuth start - Generated callback URL: {callback_url}")
    
    params = {
        "client_id": current_app.config.get("GOOGLE_CLIENT_ID"),
        "redirect_uri": callback_url,
        "response_type": "code",
        "scope": " ".join(sorted_scopes),
        "access_type": "offline",
        "include_granted_scopes": "true",
        "prompt": "consent",
        "state": state,
    }
    auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
    return jsonify(
        {"auth_url": auth_url, "server_time": datetime.now(timezone.utc).isoformat()}
    )


@bp.get("/debug/request-info")
def debug_request_info():
    """デバッグ用: リクエスト情報と生成されるURLを確認"""
    info = {
        "headers": dict(request.headers),
        "environ": {k: v for k, v in request.environ.items() if isinstance(v, str)},
        "url_root": request.url_root,
        "host": request.host,
        "scheme": request.scheme,
        "config": {
            "PREFERRED_URL_SCHEME": current_app.config.get("PREFERRED_URL_SCHEME"),
        }
    }
    
    # テスト用のURL生成
    try:
        callback_url = url_for("auth.google_oauth_callback", _external=True)
        info["generated_callback_url"] = callback_url
    except Exception as e:
        info["callback_url_error"] = str(e)
    
    return jsonify(info)


@bp.get("/google/accounts")
@login_or_jwt_required
def api_google_accounts():
    """Return paginated list of linked Google accounts."""
    
    # ページングパラメータの取得
    params = PaginationParams.from_request(default_page_size=200)
    
    # ベースクエリ
    query = GoogleAccount.query
    
    # Googleアカウントのシリアライザ関数
    def serialize_google_account(account):
        return {
            "id": account.id,
            "email": account.email,
            "status": account.status,
            "scopes": account.scopes_list(),
            "last_synced_at": (
                account.last_synced_at.isoformat() if account.last_synced_at else None
            ),
            "has_token": bool(account.oauth_token_json),
        }
    
    # ページング処理
    result = paginate_and_respond(
        query=query,
        params=params,
        serializer_func=serialize_google_account,
        id_column=GoogleAccount.id,
        count_total=not params.use_cursor,
        default_page_size=200
    )
    
    return jsonify(result)


@bp.patch("/google/accounts/<int:account_id>")
@login_or_jwt_required
def api_google_account_update(account_id):
    """Update status of a Google account."""
    account = GoogleAccount.query.get_or_404(account_id)
    data = request.get_json(silent=True) or {}
    status = data.get("status")
    if status not in ("active", "disabled"):
        return jsonify({"error": "invalid_status"}), 400
    account.status = status
    db.session.commit()
    return jsonify({"result": "ok", "status": account.status})


@bp.delete("/google/accounts/<int:account_id>")
@login_or_jwt_required
def api_google_account_delete(account_id):
    """Delete a linked Google account and revoke token."""
    account = GoogleAccount.query.get_or_404(account_id)
    token_json = json.loads(decrypt(account.oauth_token_json) or "{}")
    refresh_token = token_json.get("refresh_token")
    if refresh_token:
        try:
            log_requests_and_send(
                "POST",
                "https://oauth2.googleapis.com/revoke",
                data={"token": refresh_token},
                timeout=10,
            )
        except Exception:
            pass
    db.session.delete(account)
    db.session.commit()
    return jsonify({"result": "deleted"})


@bp.post("/google/accounts/<int:account_id>/test")
@login_or_jwt_required
def api_google_account_test(account_id):
    """Test refresh token by attempting to obtain a new access token."""
    account = GoogleAccount.query.get_or_404(account_id)
    try:
        refresh_google_token(account)
    except RefreshTokenError as e:
        return jsonify({"error": str(e)}), e.status_code
    return jsonify({"result": "ok"})


@bp.get("/media")
@login_or_jwt_required
def api_media_list():
    """Return paginated list of media items."""
    trace = uuid4().hex
    current_app.logger.info(
        json.dumps(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "trace": trace,
                "cursor": request.args.get("cursor"),
                "limit": request.args.get("limit"),
            }
        ),
        extra={"event": "media.list.begin"},
    )
    
    # ページングパラメータの取得
    params = PaginationParams.from_request(default_page_size=200)
    
    # フィルタパラメータ
    include_deleted = request.args.get("include_deleted", type=int, default=0)
    media_type = (request.args.get("type") or "").lower()
    raw_tag_ids = request.args.get("tags") or ""
    after_param = request.args.get("after")
    before_param = request.args.get("before")

    tag_ids: list[int] = []
    if raw_tag_ids:
        for part in raw_tag_ids.split(","):
            part = part.strip()
            if not part:
                continue
            try:
                tag_ids.append(int(part))
            except ValueError:
                continue

    # ベースクエリの構築
    query = Media.query.options(
        joinedload(Media.account),
        joinedload(Media.tags),
    )
    if not include_deleted:
        # is_deletedがNullまたはFalseの場合を含める
        query = query.filter(
            db.or_(Media.is_deleted.is_(False), Media.is_deleted.is_(None))
        )

    if media_type == "photo":
        query = query.filter(
            db.or_(Media.is_video.is_(False), Media.is_video.is_(None))
        )
    elif media_type == "video":
        query = query.filter(Media.is_video.is_(True))

    # タグフィルタ：すべての指定タグを含むメディアのみ
    if tag_ids:
        seen: set[int] = set()
        unique_tag_ids: list[int] = []
        for tid in tag_ids:
            if tid not in seen:
                seen.add(tid)
                unique_tag_ids.append(tid)
        for tid in unique_tag_ids:
            query = query.filter(Media.tags.any(Tag.id == tid))
        
    # 日付範囲フィルタ
    if after_param:
        try:
            after_dt = datetime.fromisoformat(after_param.replace("Z", "+00:00"))
            query = query.filter(Media.shot_at >= after_dt)
        except Exception:
            pass
    if before_param:
        try:
            before_dt = datetime.fromisoformat(before_param.replace("Z", "+00:00"))
            query = query.filter(Media.shot_at <= before_dt)
        except Exception:
            pass
    
    # メディアアイテムのシリアライザ関数
    def serialize_media_item(media):
        source_type = media.source_type
        source_label = {
            "local": "Local Import",
            "google_photos": "Google Photos",
        }.get(source_type, source_type or "unknown")
        account_email = media.account.email if getattr(media, "account", None) else None
        tags = sorted(media.tags, key=lambda t: (t.name or "").lower())

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
            "tags": [serialize_tag(tag) for tag in tags],
        }
    
    # ページング処理
    result = paginate_and_respond(
        query=query,
        params=params,
        serializer_func=serialize_media_item,
        id_column=Media.id,
        shot_at_column=Media.shot_at,
        count_total=False,  # 高速化のため総件数はカウントしない
        default_page_size=200
    )
    
    # ログ出力
    current_app.logger.info(
        json.dumps(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "trace": trace,
                "count": len(result["items"]),
                "cursor": params.cursor,
                "nextCursor": result.get("nextCursor"),
                "serverTime": result.get("serverTime"),
            }
        ),
        extra={"event": "media.list.success"},
    )
    
    return jsonify(result)


def serialize_tag(tag: Tag) -> dict:
    return {
        "id": tag.id,
        "name": tag.name,
        "attr": tag.attr,
    }


def build_playback_dict(playback: MediaPlayback | None) -> dict:
    """Return playback information dictionary."""
    return {
        "available": bool(playback and playback.status == "done"),
        "preset": playback.preset if playback else None,
        "rel_path": playback.rel_path if playback else None,
        "status": playback.status if playback else None,
    }


def build_exif_dict(exif: Exif | None) -> dict:
    """Return EXIF information dictionary."""
    return {
        "camera_make": exif.camera_make if exif else None,
        "camera_model": exif.camera_model if exif else None,
        "lens": exif.lens if exif else None,
        "iso": exif.iso if exif else None,
        "shutter": exif.shutter if exif else None,
        "f_number": (
            float(exif.f_number) if exif and exif.f_number is not None else None
        ),
        "focal_len": (
            float(exif.focal_len) if exif and exif.focal_len is not None else None
        ),
        "gps_lat": float(exif.gps_lat) if exif and exif.gps_lat is not None else None,
        "gps_lng": float(exif.gps_lng) if exif and exif.gps_lng is not None else None,
    }


def serialize_media_detail(media: Media) -> dict:
    """Serialize detailed information for a media item."""
    sidecars = [
        {"type": s.type, "rel_path": s.rel_path, "bytes": s.bytes}
        for s in media.sidecars
    ]
    playback_record = media.playbacks[0] if media.playbacks else None
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
        "shot_at": (
            media.shot_at.isoformat().replace("+00:00", "Z") if media.shot_at else None
        ),
        "imported_at": (
            media.imported_at.isoformat().replace("+00:00", "Z")
            if media.imported_at
            else None
        ),
        "is_video": int(bool(media.is_video)),
        "is_deleted": int(bool(media.is_deleted)),
        "has_playback": int(bool(media.has_playback)),
        "exif": build_exif_dict(media.exif),
        "sidecars": sidecars,
        "playback": build_playback_dict(playback_record),
        "tags": [
            serialize_tag(tag)
            for tag in sorted(media.tags, key=lambda t: (t.name or "").lower())
        ],
    }


@bp.get("/media/<int:media_id>")
@login_or_jwt_required
def api_media_detail(media_id):
    """Return detailed info for a single media item."""
    trace = uuid4().hex
    current_app.logger.info(
        json.dumps(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "media_id": media_id,
                "trace": trace,
            }
        ),
        extra={"event": "media.detail.begin"},
    )
    media = (
        Media.query.options(
            joinedload(Media.tags),
            joinedload(Media.sidecars),
            joinedload(Media.playbacks),
        )
        .get(media_id)
    )
    if not media or media.is_deleted:
        current_app.logger.info(
            json.dumps(
                {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "media_id": media_id,
                    "trace": trace,
                }
            ),
            extra={"event": "media.detail.not_found"},
        )
        return jsonify({"error": "not_found"}), 404

    media_data = serialize_media_detail(media)

    server_time = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    media_data["serverTime"] = server_time
    current_app.logger.info(
        json.dumps(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "media_id": media_id,
                "trace": trace,
                "serverTime": server_time,
            }
        ),
        extra={"event": "media.detail.success"},
    )
    return jsonify(media_data)


@bp.delete("/media/<int:media_id>")
@login_or_jwt_required
def api_media_delete(media_id: int):
    """Soft delete a media item when the user has permission."""
    user = get_current_user()
    if not user or not user.can("media:delete"):
        return (
            jsonify(
                {
                    "error": "forbidden",
                    "message": _("You do not have permission to delete media."),
                }
            ),
            403,
        )

    media = Media.query.get(media_id)
    if not media or media.is_deleted:
        return jsonify({"error": "not_found"}), 404

    associated_albums = (
        Album.query.join(album_item, Album.id == album_item.c.album_id)
        .filter(album_item.c.media_id == media_id)
        .all()
    )

    if associated_albums:
        db.session.execute(
            album_item.delete().where(album_item.c.media_id == media_id)
        )
        now = datetime.now(timezone.utc)
        for album in associated_albums:
            if album.cover_media_id == media_id:
                new_cover_id = db.session.execute(
                    select(album_item.c.media_id)
                    .where(album_item.c.album_id == album.id)
                    .order_by(
                        album_item.c.sort_index.asc(),
                        album_item.c.media_id.asc(),
                    )
                    .limit(1)
                ).scalar()
                album.cover_media_id = new_cover_id
            else:
                if album.cover_media_id is not None:
                    existing_cover = db.session.execute(
                        select(album_item.c.media_id)
                        .where(
                            album_item.c.album_id == album.id,
                            album_item.c.media_id == album.cover_media_id,
                        )
                        .limit(1)
                    ).scalar()
                    if existing_cover is None:
                        new_cover_id = db.session.execute(
                            select(album_item.c.media_id)
                            .where(album_item.c.album_id == album.id)
                            .order_by(
                                album_item.c.sort_index.asc(),
                                album_item.c.media_id.asc(),
                            )
                            .limit(1)
                        ).scalar()
                        album.cover_media_id = new_cover_id

            album.updated_at = now

    _remove_media_files(media)
    media.is_deleted = True
    db.session.commit()

    current_app.logger.info(
        json.dumps(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "media_id": media_id,
                "user_id": getattr(user, "id", None),
            }
        ),
        extra={"event": "media.delete"},
    )

    return jsonify({"result": "deleted"})


@bp.get("/tags")
@login_or_jwt_required
def api_tags_list():
    """Return list of tags for incremental search."""
    query_text = (request.args.get("q") or "").strip()
    limit = request.args.get("limit", type=int)
    if limit is None or limit <= 0:
        limit = 20
    limit = min(limit, 100)

    query = Tag.query
    if query_text:
        like_expr = f"%{query_text}%"
        query = query.filter(Tag.name.ilike(like_expr))

    tags = query.order_by(Tag.name.asc()).limit(limit).all()
    return jsonify({"items": [serialize_tag(tag) for tag in tags]})


@bp.post("/tags")
@login_or_jwt_required
def api_tags_create():
    """Create a new tag (requires tag management permission)."""
    if not current_user.can("media:tag-manage"):
        return jsonify({"error": "forbidden"}), 403

    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    attr = (payload.get("attr") or "").strip()

    if not name:
        return jsonify({"error": "name_required"}), 400
    if attr not in VALID_TAG_ATTRS:
        return jsonify({"error": "invalid_attr"}), 400

    existing = Tag.query.filter(db.func.lower(Tag.name) == name.lower()).first()
    if existing:
        return jsonify({"tag": serialize_tag(existing), "created": False}), 200

    tag = Tag(name=name, attr=attr, created_by=getattr(current_user, "id", None))
    db.session.add(tag)
    db.session.commit()

    return jsonify({"tag": serialize_tag(tag), "created": True}), 201


@bp.put("/tags/<int:tag_id>")
@login_or_jwt_required
def api_tags_update(tag_id: int):
    """Update an existing tag."""
    if not current_user.can("media:tag-manage"):
        return jsonify({"error": "forbidden"}), 403

    tag = Tag.query.get(tag_id)
    if not tag:
        return jsonify({"error": "not_found"}), 404

    payload = request.get_json(silent=True) or {}
    name = payload.get("name")
    attr = payload.get("attr")

    has_changes = False

    if isinstance(name, str):
        stripped = name.strip()
        if not stripped:
            return jsonify({"error": "name_required"}), 400
        if stripped.lower() != tag.name.lower():
            duplicate = Tag.query.filter(
                db.func.lower(Tag.name) == stripped.lower(),
                Tag.id != tag.id,
            ).first()
            if duplicate:
                return jsonify({"error": "duplicate_name"}), 409
            tag.name = stripped
            has_changes = True

    if isinstance(attr, str):
        if attr not in VALID_TAG_ATTRS:
            return jsonify({"error": "invalid_attr"}), 400
        if attr != tag.attr:
            tag.attr = attr
            has_changes = True

    if has_changes:
        tag.updated_at = datetime.now(timezone.utc)
        db.session.commit()

    return jsonify({"tag": serialize_tag(tag), "updated": has_changes})


@bp.put("/media/<int:media_id>/tags")
@login_or_jwt_required
def api_media_update_tags(media_id: int):
    """Replace tag assignments for a media item."""
    if not current_user.can("media:tag-manage"):
        return jsonify({"error": "forbidden"}), 403

    media = (
        Media.query.options(joinedload(Media.tags))
        .filter(Media.id == media_id)
        .first()
    )
    if not media or media.is_deleted:
        return jsonify({"error": "not_found"}), 404

    payload = request.get_json(silent=True) or {}
    tag_ids = payload.get("tag_ids")
    if tag_ids is None:
        return jsonify({"error": "tag_ids_required"}), 400
    if not isinstance(tag_ids, list):
        return jsonify({"error": "invalid_tag_ids"}), 400

    normalized_ids: list[int] = []
    seen: set[int] = set()
    for raw_id in tag_ids:
        try:
            value = int(raw_id)
        except (TypeError, ValueError):
            return jsonify({"error": "invalid_tag_id"}), 400
        if value not in seen:
            seen.add(value)
            normalized_ids.append(value)

    if normalized_ids:
        tags = Tag.query.filter(Tag.id.in_(normalized_ids)).all()
        found_ids = {tag.id for tag in tags}
        missing = [tid for tid in normalized_ids if tid not in found_ids]
        if missing:
            return jsonify({"error": "unknown_tag", "missing": missing}), 400
    else:
        tags = []

    previous_tag_ids = {tag.id for tag in media.tags}
    new_tag_ids = {tag.id for tag in tags}

    media.tags = tags
    media.updated_at = datetime.now(timezone.utc)
    db.session.flush()

    removed_tag_ids = previous_tag_ids - new_tag_ids
    if removed_tag_ids:
        unused_tags = (
            Tag.query.filter(Tag.id.in_(removed_tag_ids))
            .outerjoin(media_tag, Tag.id == media_tag.c.tag_id)
            .group_by(Tag.id)
            .having(db.func.count(media_tag.c.media_id) == 0)
            .all()
        )
        for unused_tag in unused_tags:
            db.session.delete(unused_tag)

    db.session.commit()

    return jsonify({
        "tags": [
            serialize_tag(tag)
            for tag in sorted(media.tags, key=lambda t: (t.name or "").lower())
        ]
    })


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _sign_payload(payload: dict) -> str:
    canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    key_b64 = current_app.config.get("FPV_DL_SIGN_KEY")
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

    key_b64 = current_app.config.get("FPV_DL_SIGN_KEY")
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


def _resolve_download_filename(payload: dict, rel: str, abs_path: str) -> str | None:
    """Return preferred download file name for a signed URL."""
    filename: str | None = None
    media_id = payload.get("mid")
    if media_id is not None:
        media = Media.query.get(media_id)
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


def _build_content_disposition(filename: str) -> str:
    """Build Content-Disposition header value keeping UTF-8 names intact."""
    sanitized = (filename or "").replace("\r", " ").replace("\n", " ").strip()
    fallback = secure_filename(sanitized) or "download"
    if sanitized and sanitized != fallback:
        return f'attachment; filename="{fallback}"; filename*=UTF-8\'\'{quote(sanitized, safe="")}'
    return f'attachment; filename="{fallback}"'
@bp.get("/media/<int:media_id>/thumbnail")
@login_or_jwt_required
def api_media_thumbnail(media_id):
    """Return thumbnail image for a media item."""
    size = request.args.get("size", type=int, default=256)
    if size not in (256, 512, 1024, 2048):
        return jsonify({"error": "invalid_size"}), 400

    media = Media.query.get(media_id)
    if not media:
        return jsonify({"error": "not_found"}), 404
    if media.is_deleted:
        return jsonify({"error": "gone"}), 410

    rel_path = media.local_rel_path
    thumbs_base, abs_path, found = _resolve_storage_file(
        "FPV_NAS_THUMBS_DIR", str(size), rel_path
    )

    if not found or not abs_path:
        _emit_structured_api_log(
            "thumbnail file missing",
            level="warning",
            event="media.thumbnail",
            media_id=media_id,
            size=size,
            base_dir=thumbs_base,
            rel_path=rel_path,
            abs_path=abs_path,
            candidates=_storage_path_candidates("FPV_NAS_THUMBS_DIR"),
        )
        return jsonify({"error": "not_found"}), 404

    ct = (
        mimetypes.guess_type(abs_path)[0]
        or media.mime_type
        or "application/octet-stream"
    )
    ttl = current_app.config.get("FPV_URL_TTL_THUMB", 600)
    with open(abs_path, "rb") as f:
        data = f.read()
    resp = current_app.response_class(data, mimetype=ct, direct_passthrough=True)
    resp.headers["Content-Length"] = str(os.path.getsize(abs_path))
    resp.headers["Cache-Control"] = f"private, max-age={ttl}"
    return resp



@bp.post("/media/<int:media_id>/thumb-url")
@login_or_jwt_required
def api_media_thumb_url(media_id):
    data = request.get_json(silent=True) or {}
    size = data.get("size")
    if size not in (256, 512, 1024, 2048):
        return jsonify({"error": "invalid_size"}), 400

    media = Media.query.get(media_id)
    if not media:
        return jsonify({"error": "not_found"}), 404
    if media.is_deleted:
        return jsonify({"error": "gone"}), 410

    rel_path = media.local_rel_path
    token_path = f"thumbs/{size}/{rel_path}"
    thumbs_base, abs_path, found = _resolve_storage_file(
        "FPV_NAS_THUMBS_DIR", str(size), rel_path
    )
    if not found or not abs_path:
        return jsonify({"error": "not_found"}), 404

    ct = (
        mimetypes.guess_type(abs_path)[0]
        or media.mime_type
        or "application/octet-stream"
    )
    ttl = current_app.config.get("FPV_URL_TTL_THUMB", 600)
    exp = int(time.time()) + ttl
    payload = {
        "v": 1,
        "typ": "thumb",
        "mid": media_id,
        "size": size,
        "path": token_path,
        "ct": ct,
        "exp": exp,
        "nonce": uuid4().hex,
    }
    token = _sign_payload(payload)
    expires_at = (
        datetime.fromtimestamp(exp, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    )
    current_app.logger.info(
        json.dumps(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "mid": media_id,
                "size": size,
                "ttl": ttl,
                "nonce": payload["nonce"],
            }
        ),
        extra={"event": "url.thumb.issue"},
    )
    return (
        jsonify(
            {
                "url": f"/api/dl/{token}",
                "expiresAt": expires_at,
                "cacheControl": f"private, max-age={ttl}",
            }
        ),
        200,
    )


@bp.post("/media/<int:media_id>/playback-url")
@login_or_jwt_required
def api_media_playback_url(media_id):
    media = Media.query.get(media_id)
    if not media or not media.is_video:
        return jsonify({"error": "not_found"}), 404
    if media.is_deleted:
        return jsonify({"error": "gone"}), 410

    pb = MediaPlayback.query.filter_by(media_id=media_id, preset="std1080p").first()
    if not pb or pb.status == "error":
        return jsonify({"error": "not_found"}), 404
    if pb.status in ("pending", "processing"):
        return jsonify({"error": "not_ready"}), 409
    if pb.status != "done":
        return jsonify({"error": "not_found"}), 404

    token_path = f"playback/{pb.rel_path}"
    play_base, abs_path, found = _resolve_storage_file(
        "FPV_NAS_PLAY_DIR", pb.rel_path
    )
    if not found or not abs_path:
        return jsonify({"error": "not_found"}), 404
    ct = mimetypes.guess_type(abs_path)[0] or "video/mp4"
    ttl = current_app.config.get("FPV_URL_TTL_PLAYBACK", 600)
    exp = int(time.time()) + ttl
    payload = {
        "v": 1,
        "typ": "playback",
        "mid": media_id,
        "size": None,
        "path": token_path,
        "ct": ct,
        "exp": exp,
        "nonce": uuid4().hex,
    }
    token = _sign_payload(payload)
    expires_at = (
        datetime.fromtimestamp(exp, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    )
    current_app.logger.info(
        json.dumps(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "mid": media_id,
                "ttl": ttl,
                "nonce": payload["nonce"],
            }
        ),
        extra={"event": "url.playback.issue"},
    )
    return (
        jsonify(
            {
                "url": f"/api/dl/{token}",
                "expiresAt": expires_at,
                "cacheControl": f"private, max-age={ttl}",
            }
        ),
        200,
    )


@bp.route("/dl/<path:token>", methods=["GET", "HEAD"])
@login_or_jwt_required
def api_download(token):
    payload, err = _verify_token(token)
    if err:
        return jsonify({"error": err}), 403

    path = payload.get("path", "")
    ct = payload.get("ct", "application/octet-stream")
    if ".." in path.split("/"):
        current_app.logger.info(
            json.dumps(
                {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "mid": payload.get("mid"),
                    "nonce": payload.get("nonce"),
                }
            ),
            extra={"event": "dl.forbidden"},
        )
        return jsonify({"error": "forbidden"}), 403

    if payload.get("typ") == "thumb":
        if not path.startswith("thumbs/"):
            return jsonify({"error": "forbidden"}), 403
        rel = path[len("thumbs/") :]
        base, abs_path, found = _resolve_storage_file(
            "FPV_NAS_THUMBS_DIR", *rel.split("/")
        )
        accel_prefix = current_app.config.get("FPV_ACCEL_THUMBS_LOCATION", "")
        ttl = current_app.config.get("FPV_URL_TTL_THUMB", 600)
    else:
        if not path.startswith("playback/"):
            return jsonify({"error": "forbidden"}), 403
        rel = path[len("playback/") :]
        base, abs_path, found = _resolve_storage_file(
            "FPV_NAS_PLAY_DIR", *rel.split("/")
        )
        accel_prefix = current_app.config.get("FPV_ACCEL_PLAYBACK_LOCATION", "")
        ttl = current_app.config.get("FPV_URL_TTL_PLAYBACK", 600)
    if not found or not abs_path:
        current_app.logger.info(
            json.dumps(
                {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "mid": payload.get("mid"),
                    "nonce": payload.get("nonce"),
                }
            ),
            extra={"event": "dl.notfound"},
        )
        return jsonify({"error": "not_found"}), 404

    download_filename = _resolve_download_filename(payload, rel, abs_path)

    guessed = mimetypes.guess_type(abs_path)[0]
    if guessed != ct:
        return jsonify({"error": "forbidden"}), 403

    size = os.path.getsize(abs_path)
    cache_control = f"private, max-age={ttl}"
    range_header = request.headers.get("Range")

    accel_enabled = current_app.config.get("FPV_ACCEL_REDIRECT_ENABLED", True)
    accel_prefix = (accel_prefix or "").strip() if accel_enabled else ""
    accel_target = None
    if accel_prefix:
        rel_posix = rel.replace(os.sep, "/").lstrip("/")
        accel_target = posixpath.join(accel_prefix.rstrip("/"), rel_posix)

    if accel_target:
        resp = current_app.response_class(b"", mimetype=ct)
        resp.headers["Cache-Control"] = cache_control
        resp.headers["Accept-Ranges"] = "bytes"
        resp.headers["X-Accel-Redirect"] = accel_target
        resp.headers["Content-Length"] = str(size)
        if download_filename:
            resp.headers["Content-Disposition"] = _build_content_disposition(
                download_filename
            )
        current_app.logger.info(
            json.dumps(
                {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "mid": payload.get("mid"),
                    "nonce": payload.get("nonce"),
                }
            ),
            extra={"event": "dl.accel"},
        )
        return resp

    if range_header:
        m = re.match(r"bytes=(\d+)-(\d*)", range_header)
        if m:
            start = int(m.group(1))
            end = int(m.group(2) or size - 1)
            end = min(end, size - 1)
            length = end - start + 1
            with open(abs_path, "rb") as f:
                f.seek(start)
                data = f.read(length)
            resp = current_app.response_class(
                data, 206, mimetype=ct, direct_passthrough=True
            )
            resp.headers["Content-Range"] = f"bytes {start}-{end}/{size}"
            resp.headers["Accept-Ranges"] = "bytes"
            resp.headers["Content-Length"] = str(length)
            resp.headers["Cache-Control"] = cache_control
            if download_filename:
                resp.headers["Content-Disposition"] = _build_content_disposition(
                    download_filename
                )
            current_app.logger.info(
                json.dumps(
                    {
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "mid": payload.get("mid"),
                        "nonce": payload.get("nonce"),
                        "start": start,
                        "end": end,
                    }
                ),
                extra={"event": "dl.range"},
            )
            return resp

    if request.method == "HEAD":
        resp = current_app.response_class(b"", mimetype=ct)
        resp.headers["Content-Length"] = str(size)
        resp.headers["Accept-Ranges"] = "bytes"
        resp.headers["Cache-Control"] = cache_control
        if download_filename:
            resp.headers["Content-Disposition"] = _build_content_disposition(
                download_filename
            )
        return resp

    with open(abs_path, "rb") as f:
        data = f.read()
    resp = current_app.response_class(data, mimetype=ct, direct_passthrough=True)
    resp.headers["Content-Length"] = str(size)
    resp.headers["Accept-Ranges"] = "bytes"
    resp.headers["Cache-Control"] = cache_control
    if download_filename:
        resp.headers["Content-Disposition"] = _build_content_disposition(
            download_filename
        )
    current_app.logger.info(
        json.dumps(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "mid": payload.get("mid"),
                "nonce": payload.get("nonce"),
            }
        ),
        extra={"event": "dl.success"},
    )
    return resp


@bp.post("/sync/local-import")
@login_or_jwt_required
def trigger_local_import():
    """ローカルファイル取り込みを手動実行"""
    user = get_current_user()
    if not user or not getattr(user, "has_role", None) or not user.has_role("admin"):
        _local_import_log(
            "Local import trigger rejected: insufficient permissions",
            level="warning",
            event="local_import.api.trigger",
            stage="denied",
        )
        return (
            jsonify({"error": _("You do not have permission to start a local import.")}),
            403,
        )

    from cli.src.celery.tasks import local_import_task_celery
    from core.models.picker_session import PickerSession
    from core.db import db
    import uuid
    import random
    import string

    _local_import_log(
        "Local import trigger requested",
        event="local_import.api.trigger",
        stage="start",
    )

    try:
        # PickerSessionを先に作成
        now = datetime.now(timezone.utc)
        random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
        session_id = f"local_import_{now.strftime('%Y%m%d_%H%M%S')}_{now.microsecond}_{random_suffix}"
        
        session = PickerSession(
            account_id=None,  # ローカルインポートの場合はNone
            session_id=session_id,
            status="processing",
            selected_count=0,
            created_at=now,
            updated_at=now,
            last_progress_at=now
        )
        db.session.add(session)
        db.session.commit()

        # Celeryタスクにセッション情報を渡して非同期実行
        task = local_import_task_celery.delay(session_id)

        _local_import_log(
            "Local import task dispatched",
            event="local_import.api.trigger",
            stage="dispatched",
            session_id=session_id,
            celery_task_id=task.id,
            picker_session_db_id=session.id,
        )

        return jsonify({
            "success": True,
            "task_id": task.id,
            "session_id": session_id,
            "message": "ローカルインポートタスクを開始しました",
            "server_time": now.isoformat()
        })

    except Exception as e:
        _local_import_log(
            "Failed to start local import task",
            level="error",
            event="local_import.api.trigger",
            stage="error",
            error=str(e),
        )
        return jsonify({
            "success": False,
            "error": str(e),
            "server_time": datetime.now(timezone.utc).isoformat()
        }), 500


@bp.post("/sync/local-import/<path:session_id>/stop")
@login_or_jwt_required
def stop_local_import(session_id):
    """キャンセル要求を受けてローカルインポートを停止（管理者専用）。"""

    user = get_current_user()
    if not user or not getattr(user, "has_role", None) or not user.has_role("admin"):
        _local_import_log(
            "Local import stop rejected: insufficient permissions",
            level="warning",
            event="local_import.api.stop",
            stage="denied",
            session_id=session_id,
        )
        return (
            jsonify({"error": _("You do not have permission to stop a local import.")}),
            403,
        )

    _local_import_log(
        "Local import stop requested",
        event="local_import.api.stop",
        stage="start",
        session_id=session_id,
    )

    picker_session = (
        PickerSession.query.filter_by(session_id=session_id, account_id=None).first()
    )
    if not picker_session:
        _local_import_log(
            "Local import stop failed: session not found",
            level="warning",
            event="local_import.api.stop",
            stage="not_found",
            session_id=session_id,
        )
        return jsonify({"error": _("Local import session not found.")}), 404

    cancelable_statuses = {"expanding", "processing", "importing", "enqueued"}
    if picker_session.status == "canceled":
        _local_import_log(
            "Local import stop noop: already canceled",
            event="local_import.api.stop",
            stage="already_canceled",
            session_id=session_id,
        )
        return jsonify({"success": True, "message": _("Local import session is already canceled."), "session_id": session_id})

    if picker_session.status not in cancelable_statuses:
        _local_import_log(
            "Local import stop rejected: invalid status",
            level="warning",
            event="local_import.api.stop",
            stage="invalid_status",
            session_id=session_id,
            status=picker_session.status,
        )
        return (
            jsonify({"error": _("Local import session is not currently running.")}),
            409,
        )

    now = datetime.now(timezone.utc)

    stats = picker_session.stats() if hasattr(picker_session, "stats") else {}
    if not isinstance(stats, dict):
        stats = {}

    celery_task_id = stats.get("celery_task_id")

    pending_statuses = ("pending", "enqueued")
    skipped_items = (
        db.session.query(PickerSelection)
        .filter(
            PickerSelection.session_id == picker_session.id,
            PickerSelection.status.in_(pending_statuses),
        )
        .all()
    )

    skipped_count = 0
    for selection in skipped_items:
        selection.status = "skipped"
        selection.finished_at = now
        skipped_count += 1

    picker_session.status = "canceled"
    picker_session.updated_at = now
    picker_session.last_progress_at = now

    db.session.flush()

    counts_query = (
        db.session.query(
            PickerSelection.status,
            db.func.count(PickerSelection.id)
        )
        .filter(PickerSelection.session_id == picker_session.id)
        .group_by(PickerSelection.status)
        .all()
    )
    counts_map = {row[0]: row[1] for row in counts_query}

    pending_remaining = sum(
        counts_map.get(status, 0) for status in ("pending", "enqueued", "running")
    )
    imported_count = counts_map.get("imported", 0)
    dup_count = counts_map.get("dup", 0)
    skipped_total = counts_map.get("skipped", 0) + dup_count
    failed_count = counts_map.get("failed", 0)

    picker_session.selected_count = imported_count

    stats.update(
        {
            "stage": "canceling",
            "cancel_requested": True,
            "canceled_at": now.isoformat().replace("+00:00", "Z"),
            "total": imported_count + skipped_total + failed_count,
            "success": imported_count,
            "skipped": skipped_total,
            "failed": failed_count,
            "pending": pending_remaining,
        }
    )
    picker_session.set_stats(stats)

    db.session.commit()

    _local_import_log(
        "Local import stop marked",
        event="local_import.api.stop",
        stage="marked",
        session_id=session_id,
        celery_task_id=celery_task_id,
        skipped=skipped_count,
    )

    revoke_error = None
    if celery_task_id:
        try:
            from cli.src.celery.celery_app import celery

            celery.control.revoke(celery_task_id, terminate=False)
            _local_import_log(
                "Local import stop revoke dispatched",
                event="local_import.api.stop",
                stage="revoked",
                session_id=session_id,
                celery_task_id=celery_task_id,
            )
        except Exception as exc:
            revoke_error = str(exc)
            _local_import_log(
                "Local import stop revoke failed",
                level="error",
                event="local_import.api.stop",
                stage="revoke_failed",
                session_id=session_id,
                celery_task_id=celery_task_id,
                error=revoke_error,
            )

    payload = {
        "success": True,
        "session_id": session_id,
        "celery_task_id": celery_task_id,
        "skipped": skipped_count,
        "counts": {
            "imported": imported_count,
            "skipped": skipped_total,
            "failed": failed_count,
            "pending": pending_remaining,
        },
        "message": _("Local import session was canceled."),
    }

    if revoke_error:
        payload["revoke_error"] = revoke_error

    return jsonify(payload)


def _prepare_local_import_path(path_value):
    if not path_value:
        return {
            "raw": None,
            "absolute": None,
            "realpath": None,
            "exists": False,
        }

    absolute = os.path.abspath(path_value)
    realpath = os.path.realpath(absolute)
    exists = os.path.isdir(realpath)
    return {
        "raw": path_value,
        "absolute": absolute,
        "realpath": realpath,
        "exists": exists,
    }


def _resolve_local_import_config():
    from webapp.config import Config

    import_dir_raw = current_app.config.get("LOCAL_IMPORT_DIR") or Config.LOCAL_IMPORT_DIR
    originals_dir_raw = current_app.config.get("FPV_NAS_ORIGINALS_DIR") or Config.FPV_NAS_ORIGINALS_DIR

    import_dir_info = _prepare_local_import_path(import_dir_raw)
    originals_dir_info = _prepare_local_import_path(originals_dir_raw)

    return {
        "import_dir": import_dir_raw,
        "originals_dir": originals_dir_raw,
        "import_dir_info": import_dir_info,
        "originals_dir_info": originals_dir_info,
    }


@bp.get("/sync/local-import/status")
@login_or_jwt_required
def local_import_status():
    """ローカルインポートの設定と状態を取得"""
    config_info = _resolve_local_import_config()

    import_dir_info = config_info["import_dir_info"]
    originals_dir_info = config_info["originals_dir_info"]

    # 取り込み対象ファイル数の計算
    file_count = 0
    if import_dir_info["exists"]:
        try:
            from core.tasks.local_import import scan_import_directory
            files = scan_import_directory(import_dir_info["realpath"])
            file_count = len(files)
        except Exception as e:
            _local_import_log(
                "Failed to scan local import directory",
                level="warning",
                event="local_import.api.status",
                stage="scan_failed",
                error=str(e),
                import_dir=import_dir_info["realpath"],
            )

    _local_import_log(
        "Local import status requested",
        event="local_import.api.status",
        stage="status",
        import_dir=config_info["import_dir"],
        import_dir_exists=import_dir_info["exists"],
        originals_dir=config_info["originals_dir"],
        originals_dir_exists=originals_dir_info["exists"],
        pending_files=file_count,
    )

    return jsonify({
        "config": {
            "import_dir": config_info["import_dir"],
            "originals_dir": config_info["originals_dir"],
            "import_dir_absolute": import_dir_info["absolute"],
            "import_dir_realpath": import_dir_info["realpath"],
            "import_dir_exists": import_dir_info["exists"],
            "originals_dir_absolute": originals_dir_info["absolute"],
            "originals_dir_realpath": originals_dir_info["realpath"],
            "originals_dir_exists": originals_dir_info["exists"],
        },
        "status": {
            "pending_files": file_count,
            "ready": import_dir_info["exists"] and originals_dir_info["exists"],
        },
        "server_time": datetime.now(timezone.utc).isoformat(),
    })


@bp.post("/sync/local-import/directories")
@login_or_jwt_required
def ensure_local_import_directories():
    """Ensure that local import directories exist (admin only)."""

    user = get_current_user()
    if not user or not getattr(user, "has_role", None) or not user.has_role("admin"):
        _local_import_log(
            "Local import directory ensure rejected: insufficient permissions",
            level="warning",
            event="local_import.api.directories",
            stage="denied",
        )
        return (
            jsonify({"error": _("You do not have permission to manage local import directories.")}),
            403,
        )

    _local_import_log(
        "Local import directory ensure requested",
        event="local_import.api.directories",
        stage="start",
    )

    initial_config = _resolve_local_import_config()

    created = []
    errors = {}

    for key in ("import_dir", "originals_dir"):
        raw_path = initial_config.get(key)
        path_info = initial_config.get(f"{key}_info") or {}
        if not raw_path:
            continue

        if path_info.get("exists"):
            continue

        target_path = path_info.get("realpath") or os.path.abspath(raw_path)
        try:
            os.makedirs(target_path, exist_ok=True)
            created.append(key)
        except Exception as exc:  # pragma: no cover - defensive logging
            _local_import_log(
                "Failed to create local import directory",
                level="error",
                event="local_import.api.directories",
                stage="create_failed",
                target_path=target_path,
                error=str(exc),
            )
            errors[key] = str(exc)

    updated_config = _resolve_local_import_config()

    payload = {
        "success": len(errors) == 0,
        "created": created,
        "errors": errors,
        "config": {
            "import_dir": updated_config["import_dir"],
            "originals_dir": updated_config["originals_dir"],
            "import_dir_absolute": updated_config["import_dir_info"]["absolute"],
            "import_dir_realpath": updated_config["import_dir_info"]["realpath"],
            "import_dir_exists": updated_config["import_dir_info"]["exists"],
            "originals_dir_absolute": updated_config["originals_dir_info"]["absolute"],
            "originals_dir_realpath": updated_config["originals_dir_info"]["realpath"],
            "originals_dir_exists": updated_config["originals_dir_info"]["exists"],
        },
        "message": _("Directories created successfully.") if created else _("Directories already exist."),
        "server_time": datetime.now(timezone.utc).isoformat(),
    }

    status_code = 200 if not errors else 500
    if errors and not created:
        payload["message"] = _("Failed to create one or more directories.")

    _local_import_log(
        "Local import directory ensure completed",
        event="local_import.api.directories",
        stage="completed",
        created=created,
        errors=errors,
        status_code=status_code,
    )

    return jsonify(payload), status_code


@bp.get("/sync/local-import/task/<task_id>")
@login_or_jwt_required
def get_local_import_task_result(task_id):
    """ローカルインポートタスクの結果を取得"""

    user = get_current_user()
    if not user or not getattr(user, "has_role", None) or not user.has_role("admin"):
        _local_import_log(
            "Local import task result rejected: insufficient permissions",
            level="warning",
            event="local_import.api.task_status",
            stage="denied",
            task_id=task_id,
        )
        return (
            jsonify({"error": _("You do not have permission to view local import progress.")}),
            403,
        )

    from cli.src.celery.celery_app import celery

    _local_import_log(
        "Local import task result requested",
        event="local_import.api.task_status",
        stage="start",
        task_id=task_id,
    )

    try:
        # タスクの結果を取得
        result = celery.AsyncResult(task_id)

        if result.state == 'PENDING':
            response = {
                "state": result.state,
                "status": "タスクが実行待ちです",
                "progress": 0
            }
        elif result.state == 'PROGRESS':
            response = {
                "state": result.state,
                "status": result.info.get('status', ''),
                "progress": result.info.get('progress', 0),
                "current": result.info.get('current', 0),
                "total": result.info.get('total', 0),
                "message": result.info.get('message', '')
            }
        elif result.state == 'SUCCESS':
            response = {
                "state": result.state,
                "status": "完了",
                "progress": 100,
                "result": result.result
            }
        else:  # FAILURE
            response = {
                "state": result.state,
                "status": "エラー",
                "progress": 0,
                "error": str(result.info)
            }

        response["server_time"] = datetime.now(timezone.utc).isoformat()

        _local_import_log(
            "Local import task result returned",
            event="local_import.api.task_status",
            stage="completed",
            task_id=task_id,
            state=response.get("state"),
            progress=response.get("progress"),
            status=response.get("status"),
            has_error=response.get("error") is not None,
        )
        return jsonify(response)

    except Exception as e:
        _local_import_log(
            "Failed to get local import task result",
            level="error",
            event="local_import.api.task_status",
            stage="error",
            task_id=task_id,
            error=str(e),
        )
        return jsonify({
            "state": "ERROR",
            "status": "タスク結果の取得に失敗しました",
            "error": str(e),
            "server_time": datetime.now(timezone.utc).isoformat()
        }), 500


@bp.get("/admin/user")
@login_or_jwt_required
def api_admin_user():
    """ユーザー一覧API（ページング対応）"""
    # 管理者権限チェック
    user = get_current_user()
    if not user or not user.can('user:manage'):
        return jsonify({"error": _("You do not have permission to access this page.")}), 403
    
    # ページング用パラメータ
    params = PaginationParams.from_request(default_page_size=50)
    
    # 検索パラメータ
    search = request.args.get('search', '').strip()
    
    # ベースクエリ
    query = User.query
    
    # 検索フィルタ
    if search:
        query = query.filter(User.email.contains(search))
    
    # ソート（IDで降順）
    query = query.order_by(User.id.desc())
    
    # ページング実行
    return paginate_and_respond(
        query=query,
        params=params,
        serializer_func=lambda user: {
            "id": user.id,
            "email": user.email,
            "is_active": user.is_active,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "roles": [{"id": role.id, "name": role.name} for role in user.roles] if user.roles else [],
            "totp_enabled": bool(user.totp_secret)
        },
        id_column=User.id
    )


@bp.post("/admin/user/<int:user_id>/toggle-active")
@login_or_jwt_required
def api_admin_user_toggle_active(user_id):
    """ユーザーのアクティブ状態を切り替えるAPI"""
    # 管理者権限チェック
    current_admin = get_current_user()
    if not current_admin or not current_admin.can('user:manage'):
        return jsonify({"error": _("You do not have permission to access this page.")}), 403
    
    user = User.query.get_or_404(user_id)
    
    # 自分自身を無効化することを防ぐ
    if user.id == current_admin.id:
        return jsonify({"error": _("You cannot deactivate yourself.")}), 400
    
    # アクティブ状態を切り替え
    user.is_active = not user.is_active
    db.session.commit()
    
    return jsonify({
        "success": True,
        "is_active": user.is_active,
        "message": _("User status updated successfully.")
    })
