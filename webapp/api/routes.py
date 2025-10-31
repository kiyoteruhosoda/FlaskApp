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
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode, quote
from email.utils import formatdate
from uuid import uuid4
from typing import Any, Iterable, Iterator

from flask import (
    Response,
    abort,
    current_app,
    flash,
    g,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import login_required, logout_user, login_user
from flask_babel import gettext as _
from functools import wraps

from . import bp
from .health import skip_auth
from .openapi import json_request_body
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
from shared.application.auth_service import AuthService
from shared.application.authenticated_principal import AuthenticatedPrincipal
from shared.domain.user import UserRegistrationService
from shared.infrastructure.user_repository import SqlAlchemyUserRepository
from ..services.token_service import TokenService
from ..services.gui_access_cookie import (
    API_LOGIN_SCOPE_SESSION_KEY,
    GUI_ACCESS_COOKIE_NAME,
    apply_gui_access_cookie,
    clear_gui_access_cookie,
    normalize_scope_items,
    should_issue_gui_access_cookie,
)
from ..auth.totp import verify_totp
from ..auth.service_account_auth import (
    ServiceAccountJWTError,
    ServiceAccountTokenValidator,
)
from core.settings import settings
from webapp.utils import determine_external_scheme
import jwt
from sqlalchemy.orm import joinedload
from sqlalchemy import func, select, case
from werkzeug.utils import secure_filename
from core.tasks.local_import import (
    SUPPORTED_EXTENSIONS,
    refresh_media_metadata_from_original,
)
from core.tasks.media_post_processing import enqueue_thumbs_generate
from core.time import utc_now_isoformat
from core.storage_service import StorageArea, StorageSelector, StorageService
from domain.storage import StorageDomain, StorageIntent, StorageResolution

from .schemas.auth import (
    LoginRequestSchema,
    LoginResponseSchema,
    LogoutResponseSchema,
    RefreshRequestSchema,
    RefreshResponseSchema,
    ServiceAccountTokenRequestSchema,
    ServiceAccountTokenResponseSchema,
)


user_repo = SqlAlchemyUserRepository(db.session)
user_registration_service = UserRegistrationService(user_repo)
auth_service = AuthService(user_repo, user_registration_service)


VALID_TAG_ATTRS = {"person", "place", "thing"}

_STORAGE_DEFAULTS: dict[str, tuple[str, ...]] = {}


@dataclass(frozen=True)
class ResolvedStorageFile:
    selector: StorageSelector
    area: StorageArea
    resolution: StorageResolution

    @property
    def base_path(self) -> str | None:
        return self.resolution.base_path

    @property
    def absolute_path(self) -> str | None:
        return self.resolution.absolute_path

    @property
    def exists(self) -> bool:
        return self.resolution.exists

JWT_BEARER_GRANT_TYPE = "urn:ietf:params:oauth:grant-type:jwt-bearer"


def _service_account_assertion_error(
    exc: ServiceAccountJWTError,
) -> tuple[dict[str, str], int]:
    status_map = {
        "InvalidSignature": 401,
        "ExpiredToken": 401,
        "MissingJTI": 400,
        "InvalidJTI": 400,
        "ReplayDetected": 403,
        "InvalidAudience": 403,
        "UnknownAccount": 403,
        "DisabledAccount": 403,
        "InvalidScope": 403,
        "JTICheckFailed": 500,
    }
    status = status_map.get(exc.code, 403)
    if status >= 500:
        return {
            "error": "server_error",
            "error_description": exc.message,
        }, status
    return {
        "error": "invalid_grant",
        "error_description": exc.message,
    }, status


@bp.post("/token")
@bp.doc(security=[])
@bp.arguments(ServiceAccountTokenRequestSchema)
@bp.response(
    200,
    ServiceAccountTokenResponseSchema,
    description="Issue access tokens for service accounts using JWT bearer assertions.",
)
@skip_auth
def api_service_account_token_exchange(data: dict) -> dict:
    grant_type = data.get("grant_type")
    if grant_type != JWT_BEARER_GRANT_TYPE:
        return (
            jsonify(
                {
                    "error": "unsupported_grant_type",
                    "error_description": _("Only the JWT bearer grant type is supported."),
                }
            ),
            400,
        )

    assertion = data.get("assertion")
    if not assertion:
        return (
            jsonify(
                {
                    "error": "invalid_request",
                    "error_description": _("The \"assertion\" field is required."),
                }
            ),
            400,
        )

    audiences = settings.service_account_signing_audiences
    if not audiences:
        current_app.logger.error(
            "Service account signing audience is not configured.",
            extra={
                "event": "service_account.token.failed",
                "reason": "audience_not_configured",
            },
        )
        return (
            jsonify(
                {
                    "error": "server_error",
                    "error_description": _("Service account signing audience is not configured."),
                }
            ),
            500,
        )

    if len(audiences) == 1:
        audience_param: str | tuple[str, ...] = audiences[0]
    else:
        audience_param = audiences

    try:
        account, claims = ServiceAccountTokenValidator.verify(
            assertion,
            audience=audience_param,
            required_scopes=None,
        )
    except ServiceAccountJWTError as exc:
        current_app.logger.info(
            "Service account assertion validation failed.",
            extra={
                "event": "service_account.token.failed",
                "code": exc.code,
                "error_description": exc.message,
            },
        )
        response, status = _service_account_assertion_error(exc)
        return jsonify(response), status

    if claims.get("iss") != account.name or claims.get("sub") != account.name:
        current_app.logger.info(
            "Service account assertion issuer mismatch.",
            extra={
                "event": "service_account.token.failed",
                "code": "IssuerMismatch",
                "service_account": account.name,
                "issuer": claims.get("iss"),
                "subject": claims.get("sub"),
            },
        )
        return (
            jsonify(
                {
                    "error": "invalid_grant",
                    "error_description": _("The assertion issuer must match the service account name."),
                }
            ),
            403,
        )

    if "scope" not in claims:
        return (
            jsonify(
                {
                    "error": "invalid_grant",
                    "error_description": _("The assertion must include a \"scope\" claim."),
                }
            ),
            400,
        )

    scope_claim = claims.get("scope")
    if not isinstance(scope_claim, str):
        return (
            jsonify(
                {
                    "error": "invalid_grant",
                    "error_description": _("The assertion scope claim must be a string."),
                }
            ),
            400,
        )

    requested_scope = [item for item in scope_claim.split() if item]
    normalized_scope, scope_str = TokenService._normalize_scope(requested_scope)
    allowed_scopes = set(account.scopes)
    disallowed = [scope for scope in normalized_scope if scope not in allowed_scopes]
    if disallowed:
        current_app.logger.info(
            "Service account assertion requested disallowed scope.",
            extra={
                "event": "service_account.token.failed",
                "service_account": account.name,
                "requested_scopes": normalized_scope,
                "allowed_scopes": sorted(allowed_scopes),
            },
        )
        return (
            jsonify(
                {
                    "error": "invalid_grant",
                    "error_description": _("The requested scope is not allowed for this service account."),
                }
            ),
            403,
        )

    access_token = TokenService.generate_service_account_access_token(
        account,
        normalized_scope,
    )
    expires_in = TokenService.ACCESS_TOKEN_EXPIRE_SECONDS

    current_app.logger.info(
        "Service account access token issued.",
        extra={
            "event": "service_account.token.issued",
            "service_account": account.name,
            "scopes": normalized_scope,
            "assertion_jti": claims.get("jti"),
        },
    )

    response_payload = {
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": expires_in,
        "scope": scope_str,
    }
    return jsonify(response_payload)


def _storage_service() -> StorageService:
    return settings.storage.service()


def _storage_area(selector: StorageSelector) -> StorageArea:
    service = _storage_service()
    if isinstance(selector, StorageDomain):
        return service.for_domain(selector)
    return service.for_key(selector)


def _normalize_storage_defaults(selector: StorageSelector) -> None:
    service = _storage_service()
    if isinstance(selector, StorageDomain):
        area = service.for_domain(selector)
        config_key = area.config_key
    else:
        config_key = selector

    defaults_override = _STORAGE_DEFAULTS.get(config_key)
    if defaults_override is None:
        return

    if isinstance(defaults_override, (list, tuple)):
        normalized = tuple(defaults_override)
    else:
        normalized = (defaults_override,)

    if _STORAGE_DEFAULTS.get(config_key) != normalized:
        _STORAGE_DEFAULTS[config_key] = normalized

    if service.defaults(config_key) != normalized:
        service.set_defaults(config_key, normalized)


def _storage_path_candidates(selector: StorageSelector) -> list[str]:
    _normalize_storage_defaults(selector)
    area = _storage_area(selector)
    return area.candidates()


def _storage_path(selector: StorageSelector) -> str | None:
    _normalize_storage_defaults(selector)
    area = _storage_area(selector)
    return area.first_existing()


def _resolve_storage_file(
    selector: StorageSelector,
    *path_parts: str,
    intent: StorageIntent = StorageIntent.READ,
) -> ResolvedStorageFile:
    _normalize_storage_defaults(selector)
    area = _storage_area(selector)
    resolution = area.resolve(*path_parts, intent=intent)
    return ResolvedStorageFile(selector=selector, area=area, resolution=resolution)


def _trigger_thumbnail_regeneration(
    media_id: int,
    *,
    reason: str,
    force: bool = False,
) -> tuple[bool, str | None]:
    """Attempt to regenerate thumbnails asynchronously.

    Returns a tuple of ``(triggered, celery_task_id)``.  When Celery is not
    available the helper falls back to synchronous thumbnail generation and
    returns ``(result_ok, None)``.
    """

    user_snapshot = _serialize_user_for_log(get_current_user())
    celery_task_id: str | None = None

    try:
        from cli.src.celery.tasks import thumbs_generate_task
    except Exception:  # pragma: no cover - celery not installed in environment
        thumbs_task = None
    else:
        thumbs_task = thumbs_generate_task

    is_testing = settings.testing

    if thumbs_task is not None and not is_testing:
        try:
            async_result = thumbs_task.apply_async(
                kwargs={"media_id": media_id, "force": force}
            )
        except Exception as exc:  # pragma: no cover - broker failure path
            _emit_structured_api_log(
                "Failed to enqueue thumbnail regeneration task.",
                level="warning",
                event="media.thumbnail.enqueue_failed",
                media_id=media_id,
                reason=reason,
                error=str(exc),
                force=force,
                user=user_snapshot,
            )
        else:
            celery_task_id = getattr(async_result, "id", None)
            _emit_structured_api_log(
                "Thumbnail regeneration task enqueued.",
                level="info",
                event="media.thumbnail.enqueue",
                media_id=media_id,
                reason=reason,
                force=force,
                celery_task_id=celery_task_id,
                user=user_snapshot,
            )
            return True, celery_task_id

    if thumbs_task is not None and is_testing:
        _emit_structured_api_log(
            "Skipping Celery thumbnail enqueue during testing; using synchronous fallback.",
            level="info",
            event="media.thumbnail.enqueue_skipped",
            media_id=media_id,
            reason=reason,
            force=force,
            user=user_snapshot,
        )

    request_context = {"reason": reason}
    if user_snapshot:
        request_context["user"] = user_snapshot

    try:
        result = enqueue_thumbs_generate(
            media_id,
            request_context=request_context,
            force=force,
        )
    except Exception as exc:  # pragma: no cover - unexpected failure path
        _emit_structured_api_log(
            "Synchronous thumbnail regeneration failed.",
            level="warning",
            event="media.thumbnail.enqueue_fallback_error",
            media_id=media_id,
            reason=reason,
            error=str(exc),
            force=force,
            user=user_snapshot,
        )
        return False, celery_task_id

    ok = bool(result.get("ok"))
    log_level = "info" if ok else "warning"
    _emit_structured_api_log(
        "Thumbnail regeneration processed synchronously." if ok else "Thumbnail regeneration could not be completed.",
        level=log_level,
        event="media.thumbnail.enqueue_fallback",
        media_id=media_id,
        reason=reason,
        result_ok=ok,
        notes=result.get("notes"),
        generated=result.get("generated"),
        skipped=result.get("skipped"),
        force=force,
        user=user_snapshot,
    )
    return ok, celery_task_id


def _serialize_user_for_log(user):
    """ユーザー情報を匿名化した形でログ出力用に整形する。"""
    if user is None:
        return None

    if isinstance(user, AuthenticatedPrincipal):
        identifier_parts = [
            f"type:{user.subject_type}",
            f"id:{user.id}",
        ]
        if user.display_name:
            identifier_parts.append(f"display_name:{user.display_name}")
        raw_identifier = "|".join(identifier_parts)
        digest = hashlib.sha256(raw_identifier.encode('utf-8')).hexdigest()
        snapshot = {
            'id_hash': digest,
            'subject_type': user.subject_type,
        }
        if user.display_name:
            snapshot['display_name'] = user.display_name
        if user.roles:
            snapshot['roles'] = list(user.roles)
        if user.scope:
            snapshot['scope'] = sorted(user.scope)
        return snapshot

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

    logger = current_app.logger
    log_methods = {
        'debug': logger.debug,
        'info': logger.info,
        'warning': logger.warning,
        'error': logger.error,
        'critical': logger.critical,
    }
    log_method = log_methods.get(level.lower(), logger.info)
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


def _set_jwt_context(principal: AuthenticatedPrincipal, scope: set[str]) -> None:
    g.current_user = principal
    g.current_token_scope = scope if scope else None


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
        
        principal = TokenService.verify_access_token(token)
        if not principal:
            return jsonify({'error': 'invalid_token'}), 401

        # Flask-Loginのcurrent_userと同じように使えるよう設定
        _set_jwt_context(principal, set(principal.scope))

        return f(*args, **kwargs)
    return decorated_function


def _normalize_rel_path(value: str | None) -> Path | None:
    if not value:
        return None
    normalized = value.replace("\\", "/").lstrip("/")
    if not normalized:
        return None
    return Path(normalized)


def _thumbnail_rel_path_candidates(media: Media) -> list[Path]:
    """Return candidate relative paths for thumbnail files."""

    candidates: list[Path] = []

    def _append(path: Path | None) -> None:
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
        for suffix in (".jpg", ".png"):
            alt = _replace_suffix(local_rel, suffix)
            _append(alt)

    return candidates


def _remove_media_files(media: Media) -> None:
    rel_path = _normalize_rel_path(media.local_rel_path)

    service = _storage_service()

    def _remove(selector: StorageSelector, *parts: str) -> None:
        resolved = _resolve_storage_file(
            selector,
            *parts,
            intent=StorageIntent.DELETE,
        )
        abs_path = resolved.absolute_path
        if not abs_path:
            return
        try:
            service.remove(abs_path)
        except FileNotFoundError:
            return
        except OSError as exc:
            current_app.logger.warning(
                json.dumps(
                    {
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "media_id": media.id,
                        "path": abs_path,
                        "error": str(exc),
                    }
                ),
                extra={"event": "media.delete.cleanup_failed"},
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


def _resolve_session_scope(user: User | None) -> list[str]:
    stored_scope = session.get(API_LOGIN_SCOPE_SESSION_KEY)
    candidates: list[str] = []
    has_stored_scope = stored_scope is not None

    if isinstance(stored_scope, str):
        candidates.extend(part for part in stored_scope.split() if part)
    elif isinstance(stored_scope, (list, tuple, set, frozenset)):
        for part in stored_scope:
            if isinstance(part, str) and part.strip():
                candidates.append(part)

    token_scope = getattr(g, "current_token_scope", None)
    if token_scope:
        candidates.extend(str(item) for item in token_scope if str(item).strip())

    if not candidates and not has_stored_scope and user is not None:
        permissions = getattr(user, "all_permissions", None)
        if isinstance(permissions, (set, frozenset, list, tuple)):
            candidates.extend(str(item) for item in permissions if str(item).strip())

    normalized = normalize_scope_items(candidates)
    session[API_LOGIN_SCOPE_SESSION_KEY] = normalized
    return normalized


def _refresh_gui_access_cookie(
    response, user: User, scope_items: Iterable[str] | None = None
) -> None:
    if scope_items is None:
        normalized_scope = _resolve_session_scope(user)
    else:
        normalized_scope = normalize_scope_items(scope_items)

    if not should_issue_gui_access_cookie(normalized_scope):
        clear_gui_access_cookie(response)
        return

    try:
        access_token = TokenService.generate_access_token(user, normalized_scope)
    except Exception:  # pragma: no cover - defensive logging
        current_app.logger.exception(
            "Failed to regenerate session access token",
            extra={
                "user_id": getattr(user, "id", None),
            "scope": normalized_scope,
        },
    )
        clear_gui_access_cookie(response)
        return

    apply_gui_access_cookie(response, access_token, normalized_scope)


def login_or_jwt_required(f):
    """Flask-LoginまたはJWT認証の両方に対応するデコレータ"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        _auth_log(
            'Authentication check started',
            stage='start',
        )

        auth_header = request.headers.get('Authorization')
        token = None
        token_source = None

        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]
            token_source = 'authorization_header'
        elif request.cookies.get('access_token'):
            token = request.cookies.get('access_token')
            token_source = 'cookie'

        if settings.login_disabled and not token and not current_user.is_authenticated:
            _auth_log(
                'Authentication bypassed because LOGIN_DISABLED is active',
                stage='bypass',
            )
            return f(*args, **kwargs)

        if token:
            _auth_log(
                'Evaluating JWT credentials',
                stage='jwt_check',
                token_source=token_source or 'unknown',
                has_authorization_header=bool(auth_header),
                authenticated_via_flask_login=current_user.is_authenticated,
            )

            principal = TokenService.verify_access_token(token)
            if not principal:
                _auth_log(
                    'JWT token verification failed',
                    level='warning',
                    stage='failure',
                    reason='invalid_token',
                    token_source=token_source or 'unknown',
                )
                if (
                    token_source == 'cookie'
                    and current_user.is_authenticated
                    and isinstance(current_user, User)
                ):
                    _auth_log(
                        'Regenerating access token from session after JWT failure',
                        level='info',
                        stage='fallback',
                        reason='invalid_token',
                        token_source=token_source or 'unknown',
                        authenticated_user=_serialize_user_for_log(current_user),
                    )
                    user_obj = getattr(
                        current_user, "_get_current_object", lambda: current_user
                    )()
                    session_scope_items = _resolve_session_scope(user_obj)
                    session_scope = set(session_scope_items)
                    g.current_token_scope = session_scope if session_scope else None
                    g.current_user = user_obj
                    response = make_response(f(*args, **kwargs))
                    _refresh_gui_access_cookie(
                        response,
                        user_obj,
                        scope_items=session_scope_items,
                    )
                    return response
                return jsonify({'error': 'invalid_token'}), 401

            else:
                _set_jwt_context(principal, set(principal.scope))
                _auth_log(
                    'Authentication successful via JWT',
                    stage='success',
                    auth_method='jwt',
                    token_source=token_source or 'unknown',
                    authenticated_user=_serialize_user_for_log(principal),
                )
                return f(*args, **kwargs)

        if current_user.is_authenticated:
            _auth_log(
                'Authentication successful via Flask-Login',
                stage='success',
                auth_method='flask_login',
                authenticated_user=_serialize_user_for_log(current_user),
            )
            return f(*args, **kwargs)

        _auth_log(
            'Flask-Login authentication unavailable; evaluating JWT credentials',
            stage='jwt_check',
            token_source='none',
            has_authorization_header=bool(auth_header),
        )
        _auth_log(
            'JWT token missing',
            level='warning',
            stage='failure',
            reason='token_missing',
            token_source='none',
        )
        return jsonify({'error': 'authentication_required'}), 401
    decorated_function._auth_enforced = True
    return decorated_function


def get_current_user():
    """現在のユーザーを取得（Flask-LoginまたはJWT認証から）"""
    from flask import g

    def _resolve_user(principal: AuthenticatedPrincipal):
        if not isinstance(principal, AuthenticatedPrincipal):
            return None
        if not principal.is_individual:
            return None

        cached = getattr(g, "current_user_model", None)
        if getattr(cached, "id", None) == principal.id:
            return cached

        user = User.query.get(principal.id)
        if user and user.is_active:
            g.current_user_model = user
            g.current_user = user
            return user
        return None

    if current_user.is_authenticated:
        if isinstance(current_user, AuthenticatedPrincipal):
            resolved = _resolve_user(current_user)
            if resolved:
                return resolved
        return current_user

    cached_user = getattr(g, "current_user_model", None)
    if cached_user is not None:
        return cached_user

    principal = getattr(g, 'current_principal', None)
    resolved = _resolve_user(principal)
    if resolved:
        return resolved
    if principal is not None:
        return principal

    fallback = getattr(g, 'current_user', None)
    resolved = _resolve_user(fallback)
    if resolved:
        return resolved
    return fallback


@bp.get("/auth/check")
@login_or_jwt_required
def api_auth_check():
    """APIクライアントがJWT認証できているか確認するためのシンプルなエンドポイント"""
    user = get_current_user()
    if not user:
        return jsonify({"error": "authentication_required"}), 401

    return jsonify({
        "id": user.id,
        "email": user.email,
        "active": bool(user.is_active),
    })


def require_api_perms(*perm_codes):
    """APIエンドポイント向けの権限チェックデコレータ"""

    def decorator(func):
        @wraps(func)
        @login_or_jwt_required
        def wrapper(*args, **kwargs):
            if settings.login_disabled:
                return func(*args, **kwargs)

            user = get_current_user()
            if not user or not user.can(*perm_codes):
                return jsonify({'error': 'forbidden'}), 403

            return func(*args, **kwargs)

        wrapper._auth_enforced = True
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

    rel_candidates = _thumbnail_rel_path_candidates(media)
    if not rel_candidates:
        return None

    for size in (2048, 1024, 512):
        for rel_path in rel_candidates:
            resolved = _resolve_storage_file(
                StorageDomain.MEDIA_THUMBNAILS,
                str(size),
                rel_path.as_posix(),
            )
            if resolved.exists:
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
@bp.doc(
    methods=["POST"],
    requestBody=json_request_body(
        "Create a new album and optionally attach media items.",
        schema={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Album title shown to end users.",
                },
                "description": {
                    "type": "string",
                    "description": "Optional rich description of the album.",
                },
                "visibility": {
                    "type": "string",
                    "enum": sorted(ALBUM_VISIBILITY_VALUES),
                    "description": "Visibility of the album (public/private/unlisted).",
                },
                "mediaIds": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Media identifiers to include in the album in order.",
                },
                "coverMediaId": {
                    "type": "integer",
                    "description": "Optional media id that should be used as the cover image.",
                },
            },
            "required": ["name"],
            "additionalProperties": False,
        },
        example={
            "name": "Trip to Kyoto",
            "description": "Photos from spring break.",
            "visibility": "private",
            "mediaIds": [101, 102, 103],
            "coverMediaId": 101,
        },
    ),
)
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
@bp.doc(
    methods=["PUT"],
    requestBody=json_request_body(
        "Update mutable properties of an album.",
        required=False,
        schema={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "New album title.",
                },
                "description": {
                    "type": "string",
                    "description": "Updated description text.",
                },
                "visibility": {
                    "type": "string",
                    "enum": sorted(ALBUM_VISIBILITY_VALUES),
                    "description": "Album visibility mode.",
                },
                "mediaIds": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Reordered list of media identifiers belonging to the album.",
                },
                "coverMediaId": {
                    "type": "integer",
                    "description": "Media id that should become the album cover.",
                },
            },
            "additionalProperties": False,
        },
        example={
            "name": "Family gathering 2023",
            "visibility": "unlisted",
            "mediaIds": [201, 202, 203],
            "coverMediaId": 203,
        },
    ),
)
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
@bp.doc(
    methods=["PUT"],
    requestBody=json_request_body(
        "Reorder the media items contained in the album.",
        schema={
            "type": "object",
            "properties": {
                "mediaIds": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Media identifiers in the desired order.",
                }
            },
            "required": ["mediaIds"],
            "additionalProperties": False,
        },
        example={"mediaIds": [501, 502, 503]},
    ),
)
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
@bp.doc(
    methods=["PUT"],
    requestBody=json_request_body(
        "Reorder albums in the sidebar.",
        schema={
            "type": "object",
            "properties": {
                "albumIds": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Album identifiers sorted in the desired order.",
                }
            },
            "required": ["albumIds"],
            "additionalProperties": False,
        },
        example={"albumIds": [10, 5, 2, 7]},
    ),
)
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
@bp.doc(security=[])
@bp.arguments(LoginRequestSchema)
@bp.response(200, LoginResponseSchema, description="ユーザー認証してJWTを発行")
@skip_auth
def api_login(data):
    """ユーザー認証してJWTを発行"""
    email = data.get("email")
    password = data.get("password")
    token = data.get("token")
    requested_scope_items = data.get("scope", [])
    requested_scope = {item for item in requested_scope_items if isinstance(item, str)}

    user_model = auth_service.authenticate(email, password)
    if not user_model:
        return jsonify({"error": "invalid_credentials"}), 401

    if user_model.totp_secret:
        if not token:
            return jsonify({"error": "totp_required"}), 401
        if not verify_totp(user_model.totp_secret, token):
            return jsonify({"error": "invalid_totp"}), 401

    login_user(user_model)

    session.pop("active_role_id", None)
    roles = list(getattr(user_model, "roles", []) or [])

    requested_role_id = data.get("active_role_id")
    if requested_role_id is not None:
        for role in roles:
            if role.id == requested_role_id:
                session["active_role_id"] = role.id
                break

    user_permissions = set(user_model.all_permissions)
    available_scope_set = set(user_permissions)
    if "gui:view" in requested_scope or "gui:view" in user_permissions:
        available_scope_set.add("gui:view")

    if "gui:view" in requested_scope:
        granted_scope = sorted(available_scope_set)
    else:
        granted_scope = sorted(requested_scope & available_scope_set)
    scope_str = " ".join(granted_scope)
    session[API_LOGIN_SCOPE_SESSION_KEY] = granted_scope

    # TokenServiceを使用してトークンペアを生成
    access_token, refresh_token = TokenService.generate_token_pair(user_model, granted_scope)

    raw_next = data.get("next_url") or request.args.get("next")
    if isinstance(raw_next, str) and raw_next.startswith("/") and not raw_next.startswith("//"):
        redirect_target = raw_next
    else:
        redirect_target = url_for("dashboard.dashboard")

    if len(roles) > 1:
        session["role_selection_next"] = redirect_target
        response_payload = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "Bearer",
            "requires_role_selection": True,
            "redirect_url": url_for("auth.select_role", next=redirect_target),
            "scope": scope_str,
            "available_scopes": sorted(available_scope_set),
        }
    else:
        _sync_active_role(user_model)
        response_payload = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "Bearer",
            "requires_role_selection": False,
            "redirect_url": redirect_target,
            "scope": scope_str,
            "available_scopes": sorted(available_scope_set),
        }

    response = jsonify(response_payload)
    apply_gui_access_cookie(response, access_token, granted_scope)
    return response


@bp.post("/logout")
@login_or_jwt_required
@bp.response(200, LogoutResponseSchema)
def api_logout():
    """JWT Cookieを削除し、リフレッシュトークンを無効化"""
    user = get_current_user()
    if user:
        TokenService.revoke_refresh_token(user)

    if current_user.is_authenticated:
        logout_user()

    session.pop("picker_session_id", None)
    session.pop(API_LOGIN_SCOPE_SESSION_KEY, None)

    resp = jsonify({"result": "ok"})
    clear_gui_access_cookie(resp)
    return resp


@bp.post("/refresh")
@bp.doc(security=[])
@bp.arguments(RefreshRequestSchema)
@bp.response(200, RefreshResponseSchema)
@skip_auth
def api_refresh(data):
    """リフレッシュトークンから新しいアクセス・リフレッシュトークンを発行"""
    refresh_token = data.get("refresh_token")

    # TokenServiceを使用してトークンをリフレッシュ
    token_bundle = TokenService.refresh_tokens(refresh_token)
    if not token_bundle:
        return jsonify({"error": "invalid_token"}), 401

    access_token, new_refresh_token, scope_str = token_bundle
    scope_items = normalize_scope_items(scope_str.split())
    session[API_LOGIN_SCOPE_SESSION_KEY] = scope_items

    resp = jsonify({
        "access_token": access_token,
        "refresh_token": new_refresh_token,
        "token_type": "Bearer",
        "scope": scope_str,
    })
    apply_gui_access_cookie(resp, access_token, scope_items)
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
@bp.doc(
    methods=["POST"],
    requestBody=json_request_body(
        "Request an OAuth authorization URL for Google APIs.",
        required=False,
        schema={
            "type": "object",
            "properties": {
                "scopes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Additional OAuth scopes to request.",
                },
                "scope_profile": {
                    "type": "string",
                    "description": "Named scope profile such as 'photo_picker'.",
                },
                "redirect": {
                    "type": "string",
                    "format": "uri",
                    "description": "Optional redirect URL to continue after authorization.",
                },
            },
            "additionalProperties": False,
        },
        example={
            "scopes": ["https://www.googleapis.com/auth/photoslibrary.readonly"],
            "scope_profile": "photo_picker",
            "redirect": "https://example.com/oauth/callback",
        },
    ),
)
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
    current_app.logger.info(
        f"OAuth start - PREFERRED_URL_SCHEME: {settings.preferred_url_scheme}"
    )
    
    callback_scheme = determine_external_scheme()
    callback_url = url_for(
        "auth.google_oauth_callback",
        _external=True,
        _scheme=callback_scheme,
    )
    current_app.logger.info(f"OAuth start - Generated callback URL: {callback_url}")
    
    params = {
        "client_id": settings.google_client_id,
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
@login_or_jwt_required
def debug_request_info():
    """デバッグ用: リクエスト情報と生成されるURLを確認"""
    info = {
        "headers": dict(request.headers),
        "environ": {k: v for k, v in request.environ.items() if isinstance(v, str)},
        "url_root": request.url_root,
        "host": request.host,
        "scheme": request.scheme,
        "config": {
            "PREFERRED_URL_SCHEME": settings.preferred_url_scheme,
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
@bp.doc(
    methods=["PATCH"],
    requestBody=json_request_body(
        "Update the status of a linked Google account.",
        schema={
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["active", "disabled"],
                    "description": "New status flag for the account.",
                }
            },
            "required": ["status"],
            "additionalProperties": False,
        },
        example={"status": "disabled"},
    ),
)
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
                "server_time": result.get("server_time"),
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


def _path_to_posix(rel_path: str | None) -> str | None:
    """Convert a stored relative path into POSIX-style notation."""

    if not rel_path:
        return None

    normalized = _normalize_rel_path(rel_path)
    if not normalized:
        return None
    return normalized.as_posix()


def _isoformat_utc(value: datetime | None) -> str | None:
    """Return an ISO8601 string in UTC for *value* if present."""

    if not value:
        return None

    if value.tzinfo is None:
        normalized = value.replace(tzinfo=timezone.utc)
    else:
        normalized = value.astimezone(timezone.utc)
    return normalized.isoformat().replace("+00:00", "Z")


_PLAYBACK_STATUS_PRIORITY = {
    "done": 3,
    "processing": 2,
    "pending": 1,
    "error": 0,
}


def _select_preferred_playback(playbacks: list[MediaPlayback]) -> MediaPlayback | None:
    """Return the most relevant playback entry from *playbacks*."""

    if not playbacks:
        return None

    base_timestamp = datetime.min.replace(tzinfo=timezone.utc)

    def _priority(pb: MediaPlayback) -> tuple[int, int, datetime, int]:
        status = (pb.status or "").lower()
        status_rank = _PLAYBACK_STATUS_PRIORITY.get(status, -1)
        preset_rank = 1 if (pb.preset or "").lower() == "std1080p" else 0
        timestamp = pb.updated_at or pb.created_at or base_timestamp
        identifier = pb.id or 0
        return (status_rank, preset_rank, timestamp, identifier)

    return max(playbacks, key=_priority)


def build_playback_dict(playback: MediaPlayback | None) -> dict:
    """Return playback information dictionary."""

    rel_path = _path_to_posix(playback.rel_path) if playback else None
    poster_rel_path = _path_to_posix(playback.poster_rel_path) if playback else None

    return {
        "available": bool(playback and playback.status == "done"),
        "preset": playback.preset if playback else None,
        "rel_path": rel_path,
        "poster_rel_path": poster_rel_path,
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
    playback_record = _select_preferred_playback(list(media.playbacks))
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

    server_time = utc_now_isoformat()
    media_data["server_time"] = server_time
    current_app.logger.info(
        json.dumps(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "media_id": media_id,
                "trace": trace,
                "server_time": server_time,
            }
        ),
        extra={"event": "media.detail.success"},
    )
    return jsonify(media_data)


@bp.patch("/media/<int:media_id>")
@login_or_jwt_required
@bp.doc(
    methods=["PATCH"],
    requestBody=json_request_body(
        "Update metadata for a media item.",
        schema={
            "type": "object",
            "properties": {
                "shot_at": {
                    "oneOf": [
                        {"type": "string", "format": "date-time"},
                        {"type": "null"},
                    ],
                    "description": "Timestamp that represents when the media was shot.",
                }
            },
            "required": ["shot_at"],
            "additionalProperties": False,
        },
        example={"shot_at": "2024-05-01T12:00:00Z"},
    ),
)
def api_media_update_metadata(media_id: int):
    """Update mutable metadata attributes for a media item."""

    user = get_current_user()
    if not user or not user.can("media:metadata-manage"):
        return (
            jsonify(
                {
                    "error": "forbidden",
                    "message": _("You do not have permission to update the shooting date."),
                }
            ),
            403,
        )

    media = Media.query.get(media_id)
    if not media or media.is_deleted:
        return jsonify({"error": "not_found"}), 404

    payload = request.get_json(silent=True) or {}
    if "shot_at" not in payload:
        return jsonify({"error": "shot_at_required"}), 400

    shot_at_value = payload.get("shot_at")
    if shot_at_value is None:
        normalized_shot_at: datetime | None = None
    elif isinstance(shot_at_value, str):
        candidate = shot_at_value.strip()
        if not candidate:
            normalized_shot_at = None
        else:
            try:
                parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
            except ValueError:
                return jsonify({"error": "invalid_shot_at"}), 400
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            normalized_shot_at = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    else:
        return jsonify({"error": "invalid_shot_at"}), 400

    media.shot_at = normalized_shot_at
    media.updated_at = datetime.now(timezone.utc)

    try:
        db.session.commit()
    except Exception:
        current_app.logger.exception(
            "Failed to update media metadata", extra={"media_id": media_id}
        )
        db.session.rollback()
        return (
            jsonify({"error": "update_failed", "message": _("Failed to update media metadata.")}),
            500,
        )

    db.session.refresh(media)

    current_app.logger.info(
        json.dumps(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "media_id": media_id,
                "shot_at": _isoformat_utc(media.shot_at),
                "event": "media.metadata.updated",
            }
        ),
        extra={"event": "media.metadata.updated"},
    )

    return jsonify({"media": serialize_media_detail(media)})


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
@bp.doc(
    methods=["POST"],
    requestBody=json_request_body(
        "Create a new media tag.",
        schema={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Display name of the tag.",
                },
                "attr": {
                    "type": "string",
                    "enum": sorted(VALID_TAG_ATTRS),
                    "description": "Tag attribute used for grouping (person/place/thing).",
                },
            },
            "required": ["name", "attr"],
            "additionalProperties": False,
        },
        example={"name": "Family", "attr": "person"},
    ),
)
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
@bp.doc(
    methods=["PUT"],
    requestBody=json_request_body(
        "Update name or attribute of an existing tag.",
        required=False,
        schema={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "New display name for the tag.",
                },
                "attr": {
                    "type": "string",
                    "enum": sorted(VALID_TAG_ATTRS),
                    "description": "Updated tag attribute value.",
                },
            },
            "additionalProperties": False,
        },
        example={"name": "Vacation", "attr": "place"},
    ),
)
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
@bp.doc(
    methods=["PUT"],
    requestBody=json_request_body(
        "Replace tags assigned to the media item.",
        schema={
            "type": "object",
            "properties": {
                "tag_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Set of tag identifiers that should remain attached.",
                }
            },
            "required": ["tag_ids"],
            "additionalProperties": False,
        },
        example={"tag_ids": [1, 5, 8]},
    ),
)
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


def _build_accel_target(prefix: str | None, rel: str, token: str) -> str | None:
    if not prefix:
        return None

    normalized_rel = rel.replace(os.sep, "/").lstrip("/")
    if not normalized_rel:
        return None

    base = posixpath.join(prefix.rstrip("/"), normalized_rel)
    if token:
        return f"{base}?token={quote(token, safe='')}"
    return base


def _build_download_response(
    *,
    payload: dict,
    resolved: "ResolvedStorageFile",
    rel: str,
    content_type: str,
    download_filename: str | None,
    accel_target: str | None,
    log_event: str,
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
            resp = current_app.response_class(
                data, 206, mimetype=content_type, direct_passthrough=True
            )
            resp.headers["Content-Range"] = f"bytes {start}-{end}/{size}"
            resp.headers["Accept-Ranges"] = "bytes"
            resp.headers["Content-Length"] = str(length)
            resp.headers["Cache-Control"] = cache_control
            if download_filename:
                resp.headers["Content-Disposition"] = _build_content_disposition(
                    download_filename
                )
            if accel_target:
                resp.headers["X-Accel-Redirect"] = accel_target
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
            current_app.logger.info(
                json.dumps(
                    {
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "mid": payload.get("mid"),
                        "nonce": payload.get("nonce"),
                    }
                ),
                extra={"event": log_event},
            )
            return resp

    if request.method == "HEAD":
        resp = current_app.response_class(b"", mimetype=content_type)
        resp.headers["Content-Length"] = str(size)
    else:
        with service.open(abs_path, "rb") as f:
            data = f.read()
        resp = current_app.response_class(
            data, mimetype=content_type, direct_passthrough=True
        )
        resp.headers["Content-Length"] = str(size)

    resp.headers["Accept-Ranges"] = "bytes"
    resp.headers["Cache-Control"] = cache_control
    if download_filename:
        resp.headers["Content-Disposition"] = _build_content_disposition(
            download_filename
        )
    if accel_target:
        resp.headers["X-Accel-Redirect"] = accel_target
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
    current_app.logger.info(
        json.dumps(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "mid": payload.get("mid"),
                "nonce": payload.get("nonce"),
            }
        ),
        extra={"event": log_event},
    )
    return resp
def _infer_media_id(expected_type: str, rel_path: str) -> int | None:
    if expected_type == "original":
        media = Media.query.filter_by(local_rel_path=rel_path).first()
        return media.id if media else None
    if expected_type == "thumb":
        media = Media.query.filter_by(thumbnail_rel_path=rel_path).first()
        if media:
            return media.id
        media = Media.query.filter_by(local_rel_path=rel_path).first()
        return media.id if media else None
    if expected_type == "playback":
        playback = MediaPlayback.query.filter_by(rel_path=rel_path).first()
        return playback.media_id if playback else None
    return None


def _handle_accel_fallback(
    *,
    expected_type: str,
    storage_domain: StorageDomain,
    prefix: str,
    rel: str,
) -> Response:
    token = request.args.get("token", "")

    rel_normalized = rel.strip("/")
    if not rel_normalized:
        abort(404)

    segments = rel_normalized.split("/")
    if any(part in ("..", "") for part in segments):
        abort(404)

    expected_path = f"{prefix}/{rel_normalized}" if prefix else rel_normalized

    payload: dict[str, Any] | None = None

    if not token:
        abort(404)

    payload, err = _verify_token(token)
    if err or payload.get("typ") != expected_type:
        abort(404)
    if payload.get("path") != expected_path:
        abort(404)

    resolved = _resolve_storage_file(storage_domain, *segments)
    if not resolved.exists or not resolved.absolute_path:
        abort(404)

    ct = (
        payload.get("ct") if payload else None
    ) or mimetypes.guess_type(resolved.absolute_path)[0] or "application/octet-stream"

    if payload is not None:
        payload["ct"] = ct

    download_filename = _resolve_download_filename(
        payload or {}, rel_normalized, resolved.absolute_path
    )
    return _build_download_response(
        payload=payload or {},
        resolved=resolved,
        rel=rel_normalized,
        content_type=ct,
        download_filename=download_filename,
        accel_target=None,
        log_event="dl.fallback",
    )


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

    rel_candidates = _thumbnail_rel_path_candidates(media)
    if not rel_candidates:
        return jsonify({"error": "not_found"}), 404
    resolved_rel: str | None = None
    resolved_file: ResolvedStorageFile | None = None
    thumbs_base: str | None = None

    for candidate in rel_candidates:
        candidate_str = candidate.as_posix()
        current = _resolve_storage_file(
            StorageDomain.MEDIA_THUMBNAILS,
            str(size),
            candidate_str,
        )
        if thumbs_base is None:
            thumbs_base = current.base_path
        if current.exists and current.absolute_path:
            resolved_rel = candidate_str
            resolved_file = current
            break

    if not resolved_file or not resolved_file.absolute_path or not resolved_rel:
        _emit_structured_api_log(
            "thumbnail file missing",
            level="warning",
            event="media.thumbnail",
            media_id=media_id,
            size=size,
            base_dir=thumbs_base,
            rel_path=rel_candidates[0].as_posix(),
            abs_path=resolved_file.absolute_path if resolved_file else None,
            candidates=_storage_path_candidates(StorageDomain.MEDIA_THUMBNAILS),
        )
        triggered, celery_task_id = _trigger_thumbnail_regeneration(
            media_id,
            reason="api_thumbnail_missing",
        )
        payload = {"error": "not_found", "thumbnailJobTriggered": triggered}
        if celery_task_id:
            payload["thumbnailJobId"] = celery_task_id
        return jsonify(payload), 404

    abs_path = resolved_file.absolute_path
    ct = (
        mimetypes.guess_type(abs_path)[0]
        or media.mime_type
        or "application/octet-stream"
    )
    ttl = settings.media_thumbnail_url_ttl_seconds

    # nginx X-Accel-Redirect 方式
    if settings.media_accel_redirect_enabled:
        # /mnt/data/media/thumbs/... → /media/thumbs/... に変換
        rel_path = os.path.relpath(abs_path, settings.media_thumbs_directory)
        accel_target = posixpath.join(settings.media_accel_thumbnails_location.rstrip("/"), rel_path)
        resp = current_app.response_class(b"", mimetype=ct)
        resp.headers["X-Accel-Redirect"] = accel_target
        resp.headers["Cache-Control"] = f"private, max-age={ttl}"
        return resp

    # fallback: Flask側で直接送る
    service = _storage_service()
    with service.open(abs_path, "rb") as f:
        data = f.read()
    resp = current_app.response_class(data, mimetype=ct, direct_passthrough=True)
    resp.headers["Content-Length"] = str(service.size(abs_path))
    resp.headers["Cache-Control"] = f"private, max-age={ttl}"
    return resp


@bp.post("/media/<int:media_id>/thumb-url")
@login_or_jwt_required
@bp.doc(
    methods=["POST"],
    requestBody=json_request_body(
        "Request a temporary signed thumbnail URL for the media item.",
        schema={
            "type": "object",
            "properties": {
                "size": {
                    "type": "integer",
                    "enum": [256, 512, 1024, 2048],
                    "description": "Pixel width of the thumbnail to generate.",
                }
            },
            "required": ["size"],
            "additionalProperties": False,
        },
        example={"size": 512},
    ),
)
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

    rel_candidates = _thumbnail_rel_path_candidates(media)
    if not rel_candidates:
        return jsonify({"error": "not_found"}), 404
    resolved_rel: str | None = None
    resolved_file: ResolvedStorageFile | None = None

    for candidate in rel_candidates:
        candidate_str = candidate.as_posix()
        current = _resolve_storage_file(
            StorageDomain.MEDIA_THUMBNAILS,
            str(size),
            candidate_str,
        )
        if current.exists and current.absolute_path:
            resolved_rel = candidate_str
            resolved_file = current
            break

    if not resolved_file or not resolved_file.absolute_path or not resolved_rel:
        return jsonify({"error": "not_found"}), 404

    token_path = f"thumbs/{size}/{resolved_rel}"

    ct = (
        mimetypes.guess_type(resolved_file.absolute_path)[0]
        or media.mime_type
        or "application/octet-stream"
    )
    ttl = settings.media_thumbnail_url_ttl_seconds
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


@bp.post("/media/<int:media_id>/recover")
@login_or_jwt_required
def api_media_recover(media_id: int):
    user = get_current_user()
    if not user or not user.can("media:recover"):
        return jsonify({"error": "forbidden"}), 403

    media = Media.query.get(media_id)
    if not media:
        return jsonify({"error": "not_found"}), 404
    if media.is_deleted:
        return jsonify({"error": "gone"}), 410

    rel_path = _normalize_rel_path(media.local_rel_path)
    if not rel_path:
        _emit_structured_api_log(
            "Original path is missing; cannot recover metadata.",
            level="warning",
            event="media.recover",
            media_id=media_id,
            user=_serialize_user_for_log(get_current_user()),
        )
        return jsonify({"error": "source_missing"}), 400

    resolved = _resolve_storage_file(
        StorageDomain.MEDIA_ORIGINALS,
        rel_path.as_posix(),
    )
    if not resolved.exists or not resolved.absolute_path:
        _emit_structured_api_log(
            "Original file for recovery was not found.",
            level="warning",
            event="media.recover",
            media_id=media_id,
            user=_serialize_user_for_log(get_current_user()),
            rel_path=rel_path.as_posix(),
            base_dir=resolved.base_path,
        )
        return jsonify({"error": "source_missing"}), 404

    abs_path = resolved.absolute_path
    base_dir = resolved.base_path
    file_extension = Path(abs_path).suffix.lower()
    if file_extension not in SUPPORTED_EXTENSIONS:
        return jsonify({"error": "unsupported_extension"}), 400

    try:
        refreshed = refresh_media_metadata_from_original(
            media,
            originals_dir=base_dir or os.path.dirname(abs_path),
            fallback_path=abs_path,
            file_extension=file_extension,
            session_id="ui_recover",
            preserve_original_path=True,
        )
    except Exception as exc:  # pragma: no cover - unexpected failure path
        _emit_structured_api_log(
            "Metadata refresh failed with an exception during recovery.",
            level="error",
            event="media.recover",
            media_id=media_id,
            user=_serialize_user_for_log(get_current_user()),
            error=str(exc),
        )
        return jsonify({"error": "refresh_failed"}), 500

    if not refreshed:
        _emit_structured_api_log(
            "Metadata refresh did not report success during recovery.",
            level="warning",
            event="media.recover",
            media_id=media_id,
            user=_serialize_user_for_log(get_current_user()),
            rel_path=rel_path.as_posix(),
        )
        return jsonify({"error": "refresh_failed"}), 500

    db.session.refresh(media)

    changed = False
    if not media.thumbnail_rel_path and media.local_rel_path:
        media.thumbnail_rel_path = media.local_rel_path
        changed = True

    if changed:
        db.session.add(media)
        db.session.commit()
        db.session.refresh(media)

    triggered, celery_task_id = _trigger_thumbnail_regeneration(
        media.id,
        reason="ui_recover",
    )

    response = {
        "result": "ok",
        "media": serialize_media_detail(media),
        "metadataRefreshed": True,
        "thumbnailJobTriggered": triggered,
    }
    if celery_task_id:
        response["thumbnailJobId"] = celery_task_id

    _emit_structured_api_log(
        "Media recovery completed successfully.",
        level="info",
        event="media.recover",
        media_id=media.id,
        user=_serialize_user_for_log(get_current_user()),
        rel_path=rel_path.as_posix(),
        source_path=abs_path,
        triggered=triggered,
        thumbnail_job_id=celery_task_id,
    )

    return jsonify(response)


@bp.post("/media/<int:media_id>/original-url")
@login_or_jwt_required
def api_media_original_url(media_id):
    media = Media.query.get(media_id)
    if not media:
        return jsonify({"error": "not_found"}), 404
    if media.is_deleted:
        return jsonify({"error": "gone"}), 410

    rel_path = _normalize_rel_path(media.local_rel_path)
    if not rel_path:
        return jsonify({"error": "not_found"}), 404

    rel_str = rel_path.as_posix()
    token_path = f"originals/{rel_str}"
    resolved = _resolve_storage_file(StorageDomain.MEDIA_ORIGINALS, rel_str)
    if not resolved.exists or not resolved.absolute_path:
        return jsonify({"error": "not_found"}), 404

    ct = (
        mimetypes.guess_type(resolved.absolute_path)[0]
        or media.mime_type
        or "application/octet-stream"
    )
    ttl = settings.media_original_url_ttl_seconds
    exp = int(time.time()) + ttl
    payload = {
        "v": 1,
        "typ": "original",
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
        extra={"event": "url.original.issue"},
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
    resolved = _resolve_storage_file(
        StorageDomain.MEDIA_PLAYBACK,
        pb.rel_path,
    )
    if not resolved.exists or not resolved.absolute_path:
        return jsonify({"error": "not_found"}), 404
    ct = mimetypes.guess_type(resolved.absolute_path)[0] or "video/mp4"
    ttl = settings.media_playback_url_ttl_seconds
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


@bp.route("/media/thumbs/<path:rel>", methods=["GET", "HEAD"])
@skip_auth
def api_download_thumb_fallback(rel: str):
    return _handle_accel_fallback(
        expected_type="thumb",
        storage_domain=StorageDomain.MEDIA_THUMBNAILS,
        prefix="thumbs",
        rel=rel,
    )


@bp.route("/media/playback/<path:rel>", methods=["GET", "HEAD"])
@skip_auth
def api_download_playback_fallback(rel: str):
    return _handle_accel_fallback(
        expected_type="playback",
        storage_domain=StorageDomain.MEDIA_PLAYBACK,
        prefix="playback",
        rel=rel,
    )


@bp.route("/media/originals/<path:rel>", methods=["GET", "HEAD"])
@skip_auth
def api_download_original_fallback(rel: str):
    return _handle_accel_fallback(
        expected_type="original",
        storage_domain=StorageDomain.MEDIA_ORIGINALS,
        prefix="originals",
        rel=rel,
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

    typ = payload.get("typ")
    if typ == "thumb":
        if not path.startswith("thumbs/"):
            return jsonify({"error": "forbidden"}), 403
        rel = path[len("thumbs/") :]
        resolved = _resolve_storage_file(
            StorageDomain.MEDIA_THUMBNAILS,
            *rel.split("/"),
        )
        accel_prefix = settings.media_accel_thumbnails_location
    elif typ == "playback":
        if not path.startswith("playback/"):
            return jsonify({"error": "forbidden"}), 403
        rel = path[len("playback/") :]
        resolved = _resolve_storage_file(
            StorageDomain.MEDIA_PLAYBACK,
            *rel.split("/"),
        )
        accel_prefix = settings.media_accel_playback_location
    elif typ == "original":
        if not path.startswith("originals/"):
            return jsonify({"error": "forbidden"}), 403
        rel = path[len("originals/") :]
        resolved = _resolve_storage_file(
            StorageDomain.MEDIA_ORIGINALS,
            *rel.split("/"),
        )
        accel_prefix = settings.media_accel_originals_location
    else:
        return jsonify({"error": "forbidden"}), 403
    if not resolved.exists or not resolved.absolute_path:
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

    abs_path = resolved.absolute_path
    download_filename = _resolve_download_filename(payload, rel, abs_path)

    guessed = mimetypes.guess_type(abs_path)[0]
    if guessed != ct:
        return jsonify({"error": "forbidden"}), 403

    accel_target = None
    if settings.media_accel_redirect_enabled:
        accel_target = _build_accel_target(accel_prefix, rel, token)

    return _build_download_response(
        payload=payload,
        resolved=resolved,
        rel=rel,
        content_type=ct,
        download_filename=download_filename,
        accel_target=accel_target,
        log_event="dl.success",
    )


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
