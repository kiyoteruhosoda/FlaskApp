# webapp/__init__.py
import hashlib
import logging
import importlib
import json
import os
import time
from collections.abc import Mapping, MutableMapping, Sequence
from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4

from babel.messages.pofile import read_po
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

import jwt

from contextlib import contextmanager

from flask import (
    Flask,
    app,
    flash,
    g,
    current_app,
    has_request_context,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user, logout_user

from flask_babel import get_locale
from flask_babel import gettext as _
from sqlalchemy.engine import make_url
from typing import Any, Dict, Iterable, List, Optional, Tuple

from core.settings import settings

from werkzeug.datastructures import FileStorage

from .extensions import db, migrate, login_manager, babel, api as smorest_api
from .error_handlers import register_error_handlers
from webapp.auth import SERVICE_LOGIN_SESSION_KEY, SERVICE_LOGIN_TOKEN_SESSION_KEY
from webapp.auth.api_key_auth import API_KEY_SECURITY_SCHEME_NAME
from .timezone import resolve_timezone, convert_to_timezone
from core.db_log_handler import DBLogHandler
from core.logging_config import ensure_appdb_file_logging
from core.settings import settings
from core.time import utc_now_isoformat
from core.system_settings_defaults import (
    DEFAULT_APPLICATION_SETTINGS,
    DEFAULT_CORS_SETTINGS,
)
from webapp.services.system_setting_service import SystemSettingService
from webapp.services.token_service import TokenService


_SENSITIVE_KEYWORDS = {
    "password",
    "passwd",
    "secret",
    "token",
    "access_token",
    "refresh_token",
    "api_key",
}


_MAX_LOG_PAYLOAD_BYTES = 60_000


_MAX_POST_PARAM_STRING_LENGTH = 120


_DEFAULT_CORS_ALLOW_HEADERS = "Authorization,Content-Type"
_DEFAULT_CORS_ALLOW_METHODS = "GET,POST,PUT,PATCH,DELETE,OPTIONS"
_DEFAULT_CORS_MAX_AGE = "86400"


def _is_sensitive_key(key):
    if not isinstance(key, str):
        return False
    key_lower = key.lower()
    return any(keyword in key_lower for keyword in _SENSITIVE_KEYWORDS)


def _mask_sensitive_data(data):
    """再帰的に辞書やリスト内の機密情報をマスクする。"""

    if isinstance(data, Mapping):
        masked = {}
        for key, value in data.items():
            if _is_sensitive_key(key):
                masked[key] = "***"
            else:
                masked[key] = _mask_sensitive_data(value)
        return masked
    if isinstance(data, Sequence) and not isinstance(data, (str, bytes, bytearray)):
        return [_mask_sensitive_data(item) for item in data]
    return data


def _summarize_for_logging(
    data,
    *,
    _depth=0,
    _max_depth=2,
    _max_string_length=120,
    _max_list_items=1,
    _max_dict_items=10,
):
    """ログ用にJSONレスポンスを必要最小限の情報へ要約する。"""

    if data is None or isinstance(data, (bool, int, float)):
        return data

    if isinstance(data, str):
        if len(data) <= _max_string_length:
            return data
        return f"{data[:_max_string_length]}… ({len(data)} chars)"

    if isinstance(data, (bytes, bytearray)):
        return f"<binary {len(data)} bytes>"

    if _depth >= _max_depth:
        if isinstance(data, Mapping):
            keys = list(data.keys())
            summary = {
                "type": "dict",
                "keys": keys[:_max_dict_items],
                "length": len(keys),
            }
            if len(keys) > _max_dict_items:
                summary["..."] = f"{len(keys) - _max_dict_items} more keys"
            return summary
        if isinstance(data, Sequence) and not isinstance(data, (str, bytes, bytearray)):
            return {
                "type": "list",
                "length": len(data),
            }
        return str(data)

    if isinstance(data, Mapping):
        summary = {}
        for index, (key, value) in enumerate(data.items()):
            if index >= _max_dict_items:
                summary["..."] = f"{len(data) - _max_dict_items} more keys"
                break
            summary[key] = _summarize_for_logging(
                value,
                _depth=_depth + 1,
                _max_depth=_max_depth,
                _max_string_length=_max_string_length,
                _max_list_items=_max_list_items,
                _max_dict_items=_max_dict_items,
            )
        return summary

    if isinstance(data, Sequence) and not isinstance(data, (str, bytes, bytearray)):
        length = len(data)
        summary = {"length": length}
        if length:
            sample_count = min(length, _max_list_items)
            summary["sample"] = [
                _summarize_for_logging(
                    data[i],
                    _depth=_depth + 1,
                    _max_depth=_max_depth,
                    _max_string_length=_max_string_length,
                    _max_list_items=_max_list_items,
                    _max_dict_items=_max_dict_items,
                )
                for i in range(sample_count)
            ]
            if length > sample_count:
                summary["..."] = f"{length - sample_count} more items"
        return summary

    return str(data)


def _serialize_for_logging(payload: Any) -> Tuple[str, int]:
    text = json.dumps(payload, ensure_ascii=False, default=str)
    return text, len(text.encode("utf-8"))


def _prepare_log_payload(
    payload: Dict[str, Any],
    *,
    keys_to_summarize: Sequence[str],
    max_bytes: int = _MAX_LOG_PAYLOAD_BYTES,
) -> Tuple[Dict[str, Any], str]:
    working = dict(payload)
    text, size = _serialize_for_logging(working)
    if size <= max_bytes:
        return working, text

    truncation: Dict[str, Dict[str, Any]] = {}
    existing_truncation = working.get("_truncation")
    if isinstance(existing_truncation, dict):
        truncation.update(existing_truncation)

    for key in keys_to_summarize:
        if key not in working:
            continue
        value = working[key]
        if value is None:
            continue
        summary = _summarize_for_logging(value)
        if summary is value:
            continue

        _, value_size = _serialize_for_logging(value)
        truncation[key] = {
            "summary": True,
            "originalBytes": value_size,
        }
        working[key] = summary
        working["_truncation"] = {"limitBytes": max_bytes, **truncation}

        text, size = _serialize_for_logging(working)
        if size <= max_bytes:
            return working, text

    minimal: Dict[str, Any] = {
        "status": working.get("status"),
        "message": "payload omitted due to size limit",
        "_truncation": {"limitBytes": max_bytes, **truncation, "omitted": True},
    }

    text, size = _serialize_for_logging(minimal)
    if size <= max_bytes:
        return minimal, text

    fallback = {
        "message": "payload omitted",
        "_truncation": {"limitBytes": max_bytes, "omitted": True},
    }
    fallback_text, _ = _serialize_for_logging(fallback)
    return fallback, fallback_text


def _truncate_long_parameter_values(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {k: _truncate_long_parameter_values(v) for k, v in value.items()}

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_truncate_long_parameter_values(item) for item in value]

    if isinstance(value, str):
        if len(value) <= _MAX_POST_PARAM_STRING_LENGTH:
            return value
        return f"{value[:_MAX_POST_PARAM_STRING_LENGTH]}… ({len(value)} chars)"

    if isinstance(value, (bytes, bytearray)):
        return f"<binary {len(value)} bytes>"

    return value


def _format_form_parameters_for_logging(form) -> Dict[str, Any]:
    if not form:
        return {}

    result: Dict[str, Any] = {}
    for key in form.keys():
        values = form.getlist(key)
        summarized_values = [_truncate_long_parameter_values(value) for value in values]
        if len(summarized_values) == 1:
            result[key] = summarized_values[0]
        else:
            result[key] = summarized_values
    return result


def _summarize_file_storage(storage: FileStorage) -> Dict[str, Any]:
    summary: Dict[str, Any] = {"omitted": True}
    filename = getattr(storage, "filename", None)
    if filename:
        summary["filename"] = filename
    content_type = getattr(storage, "content_type", None)
    if content_type:
        summary["contentType"] = content_type
    content_length = getattr(storage, "content_length", None)
    if isinstance(content_length, int):
        summary["contentLength"] = content_length
    return summary


def _format_file_parameters_for_logging(files) -> Dict[str, Any]:
    if not files:
        return {}

    result: Dict[str, Any] = {}
    for key in files.keys():
        storages: List[FileStorage] = files.getlist(key)
        summarized = [_summarize_file_storage(storage) for storage in storages]
        if len(summarized) == 1:
            result[key] = summarized[0]
        else:
            result[key] = summarized
    return result


def _extract_request_jwt_details() -> Optional[Dict[str, Any]]:
    token: Optional[str] = None
    source: Optional[str] = None

    authorization = request.headers.get("Authorization")
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        source = "authorization_header"

    if not token:
        cookie_token = request.cookies.get("access_token")
        if cookie_token:
            token = cookie_token
            source = "access_token_cookie"

    if not token:
        return None

    details: Dict[str, Any] = {"source": source or "unknown", "token": token}

    try:
        header = jwt.get_unverified_header(token)
    except jwt.InvalidTokenError as exc:
        details["header_error"] = str(exc)
        header = None
    else:
        details["header"] = header

    algorithms: Optional[list[str]] = None
    if isinstance(header, dict):
        algorithm = header.get("alg")
        if isinstance(algorithm, str) and algorithm:
            algorithms = [algorithm]

    decode_options = {
        "verify_signature": False,
        "verify_aud": False,
        "verify_exp": False,
        "verify_iss": False,
    }

    try:
        payload = jwt.decode(
            token,
            options=decode_options,
            algorithms=algorithms
            or [
                "HS256",
                "HS384",
                "HS512",
                "RS256",
                "RS384",
                "RS512",
                "ES256",
                "ES384",
                "ES512",
                "PS256",
                "PS384",
                "PS512",
            ],
        )
    except Exception as exc:  # pragma: no cover - defensive logging aid
        details["payload_error"] = str(exc)
    else:
        details["payload"] = payload

    return details


def _build_error_log_extra(event_name: str, jwt_details: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    extra = {
        "event": event_name,
        "request_id": getattr(g, "request_id", None),
        "path": request.path,
    }
    if jwt_details:
        extra["_trace_payload"] = {"jwt": jwt_details}
    return extra


def _resolve_translation_directories() -> list[str]:
    directories_config = settings.babel_translation_directories
    candidates = [directory for directory in directories_config if directory]
    return [str(Path(candidate)) for candidate in candidates if candidate]


@lru_cache(maxsize=32)
def _load_po_catalog(locale: str, directories: tuple[str, ...]) -> Dict[str, str]:
    catalog: Dict[str, str] = {}
    for directory in directories:
        po_path = Path(directory) / locale / "LC_MESSAGES" / "messages.po"
        if not po_path.exists():
            continue
        try:
            with po_path.open("rb") as buffer:
                parsed_catalog = read_po(buffer)
        except (OSError, ValueError):  # pragma: no cover - corrupted file handling
            continue
        for message in parsed_catalog:
            message_id = getattr(message, "id", None)
            message_str = getattr(message, "string", None)
            if message_id and message_str:
                catalog.setdefault(message_id, message_str)
    return catalog


def _translate_message(message: str) -> str:
    translated = _(message)
    if translated != message:
        return translated

    locale_obj = get_locale()
    locale_candidates: list[str] = []
    if locale_obj is not None:
        locale_str = str(locale_obj)
        if locale_str:
            locale_candidates.append(locale_str)
            if "_" in locale_str:
                base = locale_str.split("_", 1)[0]
                if base and base not in locale_candidates:
                    locale_candidates.append(base)

    default_locale = settings.babel_default_locale
    if isinstance(default_locale, str) and default_locale:
        if default_locale not in locale_candidates:
            locale_candidates.append(default_locale)

    directories = tuple(_resolve_translation_directories())
    if not directories:
        return message

    for candidate in locale_candidates:
        candidate = candidate.strip()
        if not candidate:
            continue
        catalog = _load_po_catalog(candidate, directories)
        if message in catalog:
            return catalog[message]

    return message


def _normalize_openapi_prefix(prefix: Optional[str]) -> str:
    if not prefix:
        return ""
    normalized = prefix.strip()
    if not normalized:
        return ""
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"
    # The OpenAPI server URL should not end with a trailing slash unless the prefix is root
    return normalized.rstrip("/")


def _strip_openapi_path_prefix(spec, prefix: Optional[str]) -> None:
    normalized_prefix = _normalize_openapi_prefix(prefix)
    if not normalized_prefix:
        return
    paths = getattr(spec, "_paths", None)
    if not isinstance(paths, MutableMapping):
        return
    items = list(paths.items())
    if not items:
        return
    if not any(path.startswith(normalized_prefix) for path, _ in items):
        return
    new_paths = type(paths)()
    for path, operations in items:
        if path.startswith(normalized_prefix):
            trimmed = path[len(normalized_prefix) :]
            if not trimmed:
                trimmed = "/"
            elif not trimmed.startswith("/"):
                trimmed = f"/{trimmed}"
            new_paths[trimmed] = operations
        else:
            new_paths[path] = operations
    spec._paths = new_paths


def _ensure_openapi_success_responses(spec) -> None:
    if spec is None:
        return
    paths = getattr(spec, "_paths", None)
    if not isinstance(paths, MutableMapping):
        return
    default_response = {
        "description": "Successful response",
        "content": {
            "application/json": {
                "schema": {
                    "type": "object",
                    "required": ["result"],
                    "properties": {
                        "result": {
                            "type": "string",
                            "description": "Generic success indicator.",
                            "example": "OK",
                        }
                    },
                    "additionalProperties": False,
                }
            }
        },
    }
    for operations in paths.values():
        if not isinstance(operations, MutableMapping):
            continue
        for operation in operations.values():
            if not isinstance(operation, MutableMapping):
                continue
            responses = operation.setdefault("responses", {})
            if not isinstance(responses, MutableMapping):
                continue
            has_success = False
            for status_code in responses.keys():
                try:
                    code_int = int(status_code)
                except (TypeError, ValueError):
                    continue
                if 200 <= code_int < 300:
                    has_success = True
                    break
            if has_success:
                continue
            responses["200"] = deepcopy(default_response)


def _configure_cors(app: Flask) -> None:
    """Configure Cross-Origin Resource Sharing based on application settings."""

    def _current_allowed_origins() -> tuple[str, ...]:
        config_value = settings.cors_allowed_origins
        origins = tuple(value for value in config_value if value)
        app.config["CORS_ALLOWED_ORIGINS"] = origins
        return origins

    def _is_origin_allowed(origin: Optional[str]) -> bool:
        if not origin:
            return False
        allowed_origins = _current_allowed_origins()
        if not allowed_origins:
            return False
        if "*" in allowed_origins:
            return True
        return origin in allowed_origins

    def _apply_base_headers(response, origin: str) -> None:
        allowed_origins = _current_allowed_origins()
        if "*" in allowed_origins:
            response.headers["Access-Control-Allow-Origin"] = "*"
        else:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers.add("Vary", "Origin")
            response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers.setdefault("Access-Control-Max-Age", _DEFAULT_CORS_MAX_AGE)

    @app.before_request
    def _handle_cors_preflight():
        if request.method != "OPTIONS":
            return None
        origin = request.headers.get("Origin")
        if not _is_origin_allowed(origin):
            return None

        response = make_response("", 204)
        _apply_base_headers(response, origin or "")

        requested_method = request.headers.get("Access-Control-Request-Method")
        response.headers["Access-Control-Allow-Methods"] = (
            requested_method or _DEFAULT_CORS_ALLOW_METHODS
        )

        requested_headers = request.headers.get("Access-Control-Request-Headers")
        if requested_headers:
            response.headers["Access-Control-Allow-Headers"] = requested_headers
        else:
            response.headers["Access-Control-Allow-Headers"] = _DEFAULT_CORS_ALLOW_HEADERS

        return response

    @app.after_request
    def _apply_cors_headers(response):
        origin = request.headers.get("Origin")
        if not _is_origin_allowed(origin):
            return response

        _apply_base_headers(response, origin or "")

        if "Access-Control-Allow-Methods" not in response.headers:
            response.headers["Access-Control-Allow-Methods"] = _DEFAULT_CORS_ALLOW_METHODS

        request_headers = request.headers.get("Access-Control-Request-Headers")
        if request_headers:
            response.headers["Access-Control-Allow-Headers"] = request_headers
        elif "Access-Control-Allow-Headers" not in response.headers:
            response.headers["Access-Control-Allow-Headers"] = _DEFAULT_CORS_ALLOW_HEADERS

        return response

def _normalize_script_root(script_root: Optional[str]) -> str:
    if not script_root:
        return ""
    normalized = script_root.strip()
    if not normalized:
        return ""
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"
    return normalized.rstrip("/")


def _build_base_url(scheme: str, host: str, script_root: str) -> str:
    base = f"{scheme}://{host.strip()}"
    if script_root and script_root != "/":
        base = f"{base}{script_root}"
    return base


def _combine_base_and_prefix(base: str, api_prefix: str) -> str:
    normalized_base = base.rstrip("/") or ("/" if base.startswith("/") else base or "/")
    if not api_prefix:
        return normalized_base
    if normalized_base == "/":
        return api_prefix or "/"
    if normalized_base.endswith(api_prefix):
        return normalized_base
    return f"{normalized_base}{api_prefix}"


def _calculate_openapi_server_urls(prefix: str) -> List[str]:
    script_root = _normalize_script_root(request.script_root)

    host = (request.host or "").strip()
    if not host:
        host_url = request.host_url or ""
        if host_url:
            host = urlsplit(host_url).netloc
    if not host:
        url_root = request.url_root or ""
        if url_root:
            host = urlsplit(url_root).netloc
    host = host.strip()

    def add_url(urls: List[str], seen: set[str], base: str) -> None:
        if not base:
            return
        combined = _combine_base_and_prefix(base, prefix)
        if combined in seen:
            return
        seen.add(combined)
        urls.append(combined)

    urls: List[str] = []
    seen: set[str] = set()

    def add_scheme(scheme: Optional[str]) -> None:
        if not scheme:
            return
        normalized = scheme.strip().lower()
        if normalized and normalized not in schemes:
            schemes.append(normalized)

    schemes: List[str] = []

    add_scheme(settings.preferred_url_scheme)

    forwarded_header = request.headers.get("Forwarded", "")
    if forwarded_header:
        for part in forwarded_header.split(","):
            for attribute in part.split(";"):
                attribute = attribute.strip()
                if attribute.lower().startswith("proto="):
                    value = attribute.split("=", 1)[1].strip().strip('"')
                    add_scheme(value)

    x_forwarded_proto = request.headers.get("X-Forwarded-Proto", "")
    if x_forwarded_proto:
        for proto in x_forwarded_proto.split(","):
            add_scheme(proto)

    add_scheme(request.scheme or request.environ.get("wsgi.url_scheme"))

    if not schemes:
        schemes = ["http"]

    if host:
        for scheme in schemes:
            base = _build_base_url(scheme, host, script_root)
            add_url(urls, seen, base)

    if not urls:
        fallback = "/" if not prefix else prefix
        return [fallback]

    return urls


def _apply_persisted_settings(app: Flask) -> None:
    """Load persisted configuration values into ``app.config``."""

    try:
        stored_payload = SystemSettingService.load_application_config_payload()
    except Exception as exc:  # pragma: no cover - defensive fallback
        app.logger.warning("Failed to load application settings from DB: %s", exc)
        stored_payload = {}

    config_payload = dict(DEFAULT_APPLICATION_SETTINGS)
    config_payload.update(stored_payload)

    if stored_payload:
        for canonical_key, legacy_keys in settings._LEGACY_KEYS.items():
            if canonical_key in stored_payload:
                continue
            for legacy_key in legacy_keys:
                if legacy_key in stored_payload:
                    config_payload[canonical_key] = stored_payload[legacy_key]
                    break
    for key, value in config_payload.items():
        if key == "DATABASE_URI":
            continue
        if isinstance(value, dict):
            app.config[key] = dict(value)
        elif isinstance(value, list):
            app.config[key] = list(value)
        else:
            app.config[key] = value

    if "REMEMBER_COOKIE_SECURE" not in config_payload:
        app.config["REMEMBER_COOKIE_SECURE"] = bool(
            app.config.get("SESSION_COOKIE_SECURE", False)
        )

    try:
        cors_payload = SystemSettingService.load_cors_config()
    except Exception as exc:  # pragma: no cover - defensive fallback
        app.logger.warning("Failed to load CORS settings from DB: %s", exc)
        cors_payload = dict(DEFAULT_CORS_SETTINGS)
    allowed = cors_payload.get("allowedOrigins", [])
    if isinstance(allowed, str):
        allowed_origins = [segment.strip() for segment in allowed.split(",") if segment.strip()]
    elif isinstance(allowed, (list, tuple, set)):
        allowed_origins = [str(origin).strip() for origin in allowed if str(origin).strip()]
    else:
        allowed_origins = []
    app.config["CORS_ALLOWED_ORIGINS"] = tuple(allowed_origins)
    
    # メール設定を再適用
    from .extensions import mail

    mail_enabled = bool(config_payload.get("MAIL_ENABLED", False))

    if mail_enabled:
        app.config["MAIL_SERVER"] = config_payload.get("MAIL_SERVER", "")
        app.config["MAIL_PORT"] = config_payload.get("MAIL_PORT", 587)
        app.config["MAIL_USE_TLS"] = config_payload.get("MAIL_USE_TLS", True)
        app.config["MAIL_USE_SSL"] = config_payload.get("MAIL_USE_SSL", False)
        app.config["MAIL_USERNAME"] = config_payload.get("MAIL_USERNAME", "")
        app.config["MAIL_PASSWORD"] = config_payload.get("MAIL_PASSWORD", "")
        app.config["MAIL_DEFAULT_SENDER"] = config_payload.get("MAIL_DEFAULT_SENDER") or config_payload.get("MAIL_USERNAME", "")

        mail_state = mail.init_app(app)
        mail.state = mail_state
        mail.app = app
    else:
        extensions = getattr(app, "extensions", None)
        if isinstance(extensions, MutableMapping):
            extensions.pop("mailman", None)
        mail.state = None
        mail.app = None


def create_app():
    """アプリケーションファクトリ"""
    from dotenv import load_dotenv
    from .config import BaseApplicationSettings
    from werkzeug.middleware.proxy_fix import ProxyFix

    # .env を読み込む（環境変数が未設定の場合のみ）
    load_dotenv()

    from flask.testing import FlaskClient

    class _HostPreservingClient(FlaskClient):
        def __init__(self, *args, **kwargs):  # type: ignore[override]
            super().__init__(*args, **kwargs)
            self.environ_base.setdefault("SERVER_NAME", "localhost")
            self.environ_base.setdefault("HTTP_HOST", "localhost")

        def open(self, *args, **kwargs):  # type: ignore[override]
            if not kwargs.get("base_url"):
                kwargs["base_url"] = "http://localhost"
            return super().open(*args, **kwargs)

        @contextmanager
        def session_transaction(self, *args, **kwargs):  # type: ignore[override]
            kwargs.setdefault("base_url", "http://localhost")
            with super().session_transaction(*args, **kwargs) as sess:
                yield sess

    app = Flask(__name__)
    app.test_client_class = _HostPreservingClient
    app.config.from_object(BaseApplicationSettings)
    app.config.setdefault("LAST_BEAT_AT", None)
    app.config.setdefault("API_TITLE", "nolumia API")
    app.config.setdefault("API_VERSION", "1.0.0")
    app.config.setdefault("OPENAPI_VERSION", "3.0.3")
    app.config.setdefault("OPENAPI_URL_PREFIX", "/api")
    app.config.setdefault("OPENAPI_JSON_PATH", "openapi.json")
    app.config.setdefault("OPENAPI_SWAGGER_UI_PATH", "docs")
    app.config.setdefault("OPENAPI_OVERVIEW_PATH", "overview")
    app.config.setdefault("OPENAPI_OVERVIEW_TITLE", "API一覧")
    app.config.setdefault(
        "OPENAPI_SWAGGER_UI_URL",
        "https://cdn.jsdelivr.net/npm/swagger-ui-dist/",
    )
    api_spec_options = app.config.setdefault("API_SPEC_OPTIONS", {})
    info_options = api_spec_options.setdefault("info", {})
    info_options.setdefault(
        "description",
        "Nolumia API provides authentication, media management, and Google Photos integration endpoints.",
    )
    swagger_ui_config = app.config.setdefault("OPENAPI_SWAGGER_UI_CONFIG", {})
    swagger_ui_config.setdefault("persistAuthorization", True)

    # リバースプロキシ（nginx等）使用時のHTTPS検出
    # ProxyFixをカスタマイズしてデバッグ情報を追加
    from werkzeug.middleware.proxy_fix import ProxyFix
    
    class DebugProxyFix(ProxyFix):
        def __call__(self, environ, start_response):
            app.logger.debug(f"ProxyFix - Original scheme: {environ.get('wsgi.url_scheme')}")
            app.logger.debug(f"ProxyFix - X-Forwarded-Proto: {environ.get('HTTP_X_FORWARDED_PROTO')}")
            app.logger.debug(f"ProxyFix - X-Forwarded-Host: {environ.get('HTTP_X_FORWARDED_HOST')}")
            result = super().__call__(environ, start_response)
            app.logger.debug(f"ProxyFix - Final scheme: {environ.get('wsgi.url_scheme')}")
            return result
    
    app.wsgi_app = DebugProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    # 拡張初期化
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    with app.app_context():
        _apply_persisted_settings(app)
        database_uri = settings.sqlalchemy_database_uri
        testing_mode = settings.testing

    if testing_mode and isinstance(database_uri, str) and database_uri.startswith("sqlite:///"):
        db_path = database_uri.replace("sqlite:///", "", 1)
        if db_path and db_path != ":memory:":
            try:
                os.remove(db_path)
            except FileNotFoundError:
                pass

    env_overrides = {
        "MEDIA_TEMP_DIRECTORY": settings.tmp_directory_configured,
        "MEDIA_ORIGINALS_DIRECTORY": settings.media_originals_directory,
        "MEDIA_PLAYBACK_DIRECTORY": settings.media_play_directory,
        "MEDIA_THUMBNAILS_DIRECTORY": settings.media_thumbs_directory,
        "MEDIA_LOCAL_IMPORT_DIRECTORY": settings.local_import_directory_configured,
        "MEDIA_DOWNLOAD_SIGNING_KEY": settings.media_download_signing_key,
    }
    for key, value in env_overrides.items():
        if value:
            app.config[key] = value

    babel.init_app(app, locale_selector=_select_locale)
    smorest_api.init_app(app)
    
    # Initialize Flask-Mailman
    from .extensions import mail
    # メール機能が有効な場合のみ設定を適用して初期化
    if settings.mail_enabled:
        app.config['MAIL_SERVER'] = settings.mail_server
        app.config['MAIL_PORT'] = settings.mail_port
        app.config['MAIL_USE_TLS'] = settings.mail_use_tls
        app.config['MAIL_USE_SSL'] = settings.mail_use_ssl
        app.config['MAIL_USERNAME'] = settings.mail_username
        app.config['MAIL_PASSWORD'] = settings.mail_password
        app.config['MAIL_DEFAULT_SENDER'] = settings.mail_default_sender or settings.mail_username
        mail_state = mail.init_app(app)
        mail.state = mail_state
        mail.app = app

    register_error_handlers(app)

    # Local Import監査ロガー初期化
    with app.app_context():
        try:
            from bounded_contexts.photonest.infrastructure.local_import.logging_integration import init_audit_logger
            init_audit_logger()
            app.logger.info("Local Import監査ロガーを初期化しました")
        except Exception as e:
            app.logger.warning(f"Local Import監査ロガー初期化をスキップしました: {e}")

    with app.app_context():
        smorest_api.spec.components.security_scheme(
            "JWTBearerAuth",
            {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
                "description": "Standard JWT bearer authentication. Send `Authorization: Bearer <token>`.",
            },
        )
        smorest_api.spec.components.security_scheme(
            API_KEY_SECURITY_SCHEME_NAME,
            {
                "type": "apiKey",
                "in": "header",
                "name": "Authorization",
                "description": (
                    "Send the service account API key using the Authorization "
                    "header with the `ApiKey <token>` format."
                ),
            },
        )
        smorest_api.spec.options.setdefault("security", [{"JWTBearerAuth": []}])

    _configure_cors(app)

    with app.app_context():
        configured_servers = (settings.api_spec_options or {}).get("servers")

    @app.before_request
    def _refresh_openapi_server_urls():
        if configured_servers:
            return
        spec = getattr(smorest_api, "spec", None)
        if spec is None:
            return
        prefix = _normalize_openapi_prefix(settings.openapi_url_prefix)
        server_urls = _calculate_openapi_server_urls(prefix)
        spec.options["servers"] = [{"url": url} for url in server_urls]

    # ★ Jinja から get_locale() を使えるようにする
    app.jinja_env.globals["get_locale"] = get_locale

    # テンプレートコンテキストプロセッサ：バージョン情報とタイムゾーンを追加
    from core.version import get_version_string

    @app.before_request
    def _set_request_timezone():
        tz_cookie = request.cookies.get("tz")
        fallback = settings.babel_default_timezone
        tz_name, tzinfo = resolve_timezone(tz_cookie, fallback)
        g.user_timezone_name = tz_name
        g.user_timezone = tzinfo

    @app.before_request
    def _apply_service_login_scope():
        if not session.get(SERVICE_LOGIN_SESSION_KEY):
            return
        if getattr(g, "current_token_scope", None) is not None:
            return

        token = request.cookies.get("access_token")
        if not token:
            g.current_token_scope = set()
            session.pop(SERVICE_LOGIN_SESSION_KEY, None)
            session.pop(SERVICE_LOGIN_TOKEN_SESSION_KEY, None)
            logout_user()
            g.service_login_clear_cookie = True
            return

        principal = TokenService.create_principal_from_token(token)
        if not principal:
            g.current_token_scope = set()
            session.pop(SERVICE_LOGIN_SESSION_KEY, None)
            session.pop(SERVICE_LOGIN_TOKEN_SESSION_KEY, None)
            logout_user()
            g.service_login_clear_cookie = True
            return

        principal_scope = principal.scope if principal else frozenset()
        if current_user.is_authenticated and hasattr(current_user, "get_id"):
            current_id = str(current_user.get_id())
            if current_id != str(principal.get_id()):
                current_app.logger.warning(
                    "Service login token subject mismatch; ignoring token scope",
                    extra={"event": "auth.service_login", "path": request.path},
                )
                logout_user()
                session.pop(SERVICE_LOGIN_SESSION_KEY, None)
                session.pop(SERVICE_LOGIN_TOKEN_SESSION_KEY, None)
                g.current_token_scope = set()
                g.service_login_clear_cookie = True
                return

        if principal.is_service_account:
            session[SERVICE_LOGIN_TOKEN_SESSION_KEY] = token
        g.current_token_scope = set(principal_scope)

    @app.after_request
    def _clear_service_login_cookie(response):
        if getattr(g, "service_login_clear_cookie", False):
            response.delete_cookie("access_token")
        return response

    @app.context_processor
    def inject_version():
        languages = [str(lang).strip() for lang in settings.languages if str(lang).strip()]
        if not languages:
            default_language = settings.babel_default_locale or "en"
            if default_language:
                languages = [default_language]

        default_language = settings.babel_default_locale or (
            languages[0] if languages else "en"
        )

        locale_obj = get_locale()
        current_language = str(locale_obj) if locale_obj else default_language
        if "_" in current_language:
            short_lang = current_language.split("_")[0]
            if short_lang in languages:
                current_language = short_lang
        if current_language not in languages and languages:
            current_language = languages[0]

        language_labels = {
            "ja": _("Japanese"),
            "en": _("English"),
        }
        for lang in languages:
            language_labels.setdefault(lang, lang.upper())

        return dict(
            app_version=get_version_string(),
            current_timezone=getattr(g, "user_timezone", timezone.utc),
            current_timezone_name=getattr(g, "user_timezone_name", "UTC"),
            language_selector_languages=languages,
            language_labels=language_labels,
            current_language=current_language,
        )

    @app.template_filter("localtime")
    def _localtime_filter(value, fmt="%Y/%m/%d %H:%M"):
        """Render *value* in the user's preferred time zone."""

        if value is None:
            return ""
        if not isinstance(value, datetime):
            return value

        tzinfo = getattr(g, "user_timezone", timezone.utc)
        localized = convert_to_timezone(value, tzinfo)
        if localized is None:
            return ""
        if fmt is None:
            return localized
        return localized.strftime(fmt)

    @app.template_filter("escapejs")
    def _escapejs_filter(value):
        """Escape a string for safe embedding inside JavaScript strings."""

        if value is None:
            return ""

        if not isinstance(value, str):
            value = str(value)

        # ``json.dumps`` provides the necessary escaping for characters that
        # would otherwise break out of a JavaScript string literal (quotes,
        # newlines, etc.). The surrounding quotes added by ``json.dumps`` are
        # removed because the template already provides them.
        return json.dumps(value, ensure_ascii=False)[1:-1]

    disable_db_logging = testing_mode or settings.testing

    # Logging configuration
    if not disable_db_logging:
        if not any(isinstance(h, DBLogHandler) for h in app.logger.handlers):
            db_handler = DBLogHandler(app=app)
            db_handler.setLevel(logging.INFO)
            app.logger.addHandler(db_handler)

        ensure_appdb_file_logging(app.logger)

        should_bind_db_handlers = True
        logging_database_uri = database_uri
        if logging_database_uri:
            try:
                url = make_url(logging_database_uri)
            except Exception:  # pragma: no cover - invalid URI should not block logging
                url = None
            if url is not None and url.get_backend_name() == "sqlite":
                if url.database in (None, "", ":memory:"):
                    should_bind_db_handlers = False

        if should_bind_db_handlers:
            for handler in app.logger.handlers:
                if isinstance(handler, DBLogHandler):
                    handler.bind_to_app(app)
    elif app.logger.level == logging.NOTSET:
        app.logger.setLevel(logging.INFO)
    
    # デバッグモードでは詳細ログを有効化
    if app.debug:
        app.logger.setLevel(logging.DEBUG)
        # コンソールハンドラーも追加
        import sys
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(formatter)
        app.logger.addHandler(console_handler)
    else:
        app.logger.setLevel(logging.INFO)



    # モデル import（migrate 用に認識させる）
    from core.models import user as _user  # noqa: F401
    from core.models import google_account as _google_account  # noqa: F401
    from core.models import photo_models as _photo_models    # noqa: F401
    from core.models import job_sync as _job_sync    # noqa: F401
    from core.models import picker_session as _picker_session  # noqa: F401
    from core.models import picker_import_task as _picker_import_task  # noqa: F401
    from core.models import log as _log  # noqa: F401
    from core.models.wiki import models as _wiki_models  # noqa: F401
    from core.models import totp as _totp_models  # noqa: F401
    from bounded_contexts.certs.infrastructure import models as _cert_models  # noqa: F401


    # Blueprint 登録
    from .auth import bp as auth_bp
    from .auth.routes import picker as picker_view  # 最初にインポート
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.add_url_rule("/picker/<int:account_id>", view_func=picker_view, endpoint="picker")

    from .dashboard import bp as dashboard_bp
    app.register_blueprint(dashboard_bp, url_prefix="/dashboard")

    from .admin.routes import bp as admin_bp
    app.register_blueprint(admin_bp, url_prefix="/admin")

    from bounded_contexts.photonest.presentation.photo_view import bp as photo_view_bp
    app.register_blueprint(photo_view_bp)

    from .api import bp as api_bp
    api_url_prefix = "/api"
    smorest_api.register_blueprint(api_bp, url_prefix=api_url_prefix)
    
    # CDN admin API
    from webapp.api.admin.cdn import bp as cdn_admin_bp
    smorest_api.register_blueprint(cdn_admin_bp)
    
    # Blob admin API
    from webapp.api.admin.blob import bp as blob_admin_bp
    smorest_api.register_blueprint(blob_admin_bp)
    
    _strip_openapi_path_prefix(smorest_api.spec, api_url_prefix)

    from presentation.web.api import routes as api_routes

    app.add_url_rule(
        "/media/thumbs/<path:rel>",
        endpoint="media_thumb_fallback",
        view_func=api_routes.api_download_thumb_fallback,
        methods=["GET", "HEAD"],
    )
    app.add_url_rule(
        "/media/playback/<path:rel>",
        endpoint="media_playback_fallback",
        view_func=api_routes.api_download_playback_fallback,
        methods=["GET", "HEAD"],
    )
    app.add_url_rule(
        "/media/originals/<path:rel>",
        endpoint="media_original_fallback",
        view_func=api_routes.api_download_original_fallback,
        methods=["GET", "HEAD"],
    )
    _ensure_openapi_success_responses(smorest_api.spec)

    # 認証なしの健康チェック用Blueprint
    from .health import health_bp
    app.register_blueprint(health_bp, url_prefix="/health")

    # デバッグ用Blueprint（開発環境のみ）
    if app.debug or testing_mode:
        from .debug_routes import debug_bp
        app.register_blueprint(debug_bp, url_prefix="/debug")

    from bounded_contexts.wiki.presentation.wiki import bp as wiki_bp
    app.register_blueprint(wiki_bp, url_prefix="/wiki")

    from bounded_contexts.totp.presentation import bp as totp_bp
    app.register_blueprint(totp_bp, url_prefix="/totp")

    from bounded_contexts.certs.presentation.ui import certs_ui_bp
    app.register_blueprint(certs_ui_bp, url_prefix="/certs")

    from bounded_contexts.certs.presentation.api import certs_api_bp
    app.register_blueprint(certs_api_bp, url_prefix="/api")

    # Local Import状態管理API
    from bounded_contexts.photonest.presentation.local_import_status_api import bp as local_import_status_bp
    app.register_blueprint(local_import_status_bp)

    # React アプリケーション用ルート登録
    from .react_routes import register_react_routes
    register_react_routes(app)

    # CLI コマンド登録
    register_cli_commands(app)

    @app.before_request
    def _apply_login_disabled_for_testing():
        if settings.testing:
            app.config['LOGIN_DISABLED'] = True

    @app.before_request
    def start_timer():
        g.start_time = time.perf_counter()

    @app.before_request
    def log_api_request():
        if request.path.startswith("/api"):
            req_id = str(uuid4())
            g.request_id = req_id
            # Inputログ
            try:
                input_json = request.get_json(silent=True)
            except Exception:
                input_json = None

            log_dict = {
                "method": request.method,
            }
            args_dict = request.args.to_dict()
            if args_dict:
                log_dict["args"] = _mask_sensitive_data(args_dict)
            form_dict = _format_form_parameters_for_logging(request.form)
            if form_dict:
                log_dict["form"] = _mask_sensitive_data(form_dict)
            files_dict = _format_file_parameters_for_logging(request.files)
            if files_dict:
                log_dict["files"] = _mask_sensitive_data(files_dict)
            if input_json is not None:
                processed_json = (
                    _truncate_long_parameter_values(input_json)
                    if request.method.upper() == "POST"
                    else input_json
                )
                log_dict["json"] = _mask_sensitive_data(processed_json)
            _, serialized_payload = _prepare_log_payload(
                log_dict,
                keys_to_summarize=("json", "form", "args", "files"),
            )
            app.logger.info(
                serialized_payload,
                extra={
                    "event": "api.input",
                    "request_id": req_id,
                    "path": request.path,
                }
            )

    @app.after_request
    def log_api_response(response):
        if request.path.startswith("/api"):
            req_id = getattr(g, "request_id", None)
            resp_json = None
            if response.mimetype == "application/json":
                try:
                    resp_json = response.get_json()
                except Exception as e:
                    print(f"Error parsing JSON response {request.path}:", e)
                    resp_json = None
            masked_json = (
                _mask_sensitive_data(resp_json) if resp_json is not None else None
            )
            base_payload = {
                "status": response.status_code,
                "json": masked_json,
            }
            _, log_payload = _prepare_log_payload(
                base_payload,
                keys_to_summarize=("json",),
            )
            log_extra = {
                "event": "api.output",
                "request_id": req_id,
                "path": request.path,
            }
            if response.status_code >= 400:
                app.logger.warning(log_payload, extra=log_extra)
            else:
                app.logger.info(log_payload, extra=log_extra)
        return response

    @app.after_request
    def log_server_error(response):
        if response.status_code >= 500 and not getattr(g, "exception_logged", False):
            try:
                input_json = request.get_json(silent=True)
            except Exception:
                input_json = None
            log_dict = {
                "status": response.status_code,
                "method": request.method,
                "user_agent": request.user_agent.string,
            }
            qs = request.query_string.decode()
            if qs:
                log_dict["query_string"] = qs
            form_dict = request.form.to_dict()
            if form_dict:
                log_dict["form"] = _mask_sensitive_data(form_dict)
            if input_json is not None:
                log_dict["json"] = _mask_sensitive_data(input_json)
            app.logger.error(
                json.dumps(log_dict, ensure_ascii=False),
                extra={
                    "event": "api.server_error",
                    "path": request.url,
                    "request_id": getattr(g, "request_id", None),
                },
            )
        return response

    @app.after_request
    def add_server_timing(response):
        start = getattr(g, "start_time", None)
        if start is not None:
            duration = (time.perf_counter() - start) * 1000
            response.headers["Server-Timing"] = f"app;dur={duration:.2f}"
        return response

    @app.after_request
    def inject_server_time(response):
        server_time_value = utc_now_isoformat()
        response.headers["X-Server-Time"] = server_time_value

        if response.mimetype == "application/json":
            try:
                payload = response.get_json()
            except Exception:
                payload = None

            if isinstance(payload, dict):
                payload["server_time"] = server_time_value
                response.set_data(app.json.dumps(payload))
                response.mimetype = "application/json"

        return response

    # 注意：既存のルートは削除し、Reactアプリケーションが処理します
    # ルート "/" は react_routes.py で処理される

    # テストページ（デバッグ用）
    @app.route("/test/session-refresh")
    def test_session_refresh():
        return render_template("test_session_refresh.html")

    # 言語切替（/lang/ja, /lang/en）
    @app.get("/lang/<lang_code>")
    def set_lang(lang_code):
        if lang_code not in app.config["LANGUAGES"]:
            lang_code = app.config["BABEL_DEFAULT_LOCALE"]
        resp = make_response(redirect(request.headers.get("Referer", url_for("index"))))
        # 30日保持
        resp.set_cookie(
            "lang",
            lang_code,
            max_age=60 * 60 * 24 * 30,
            httponly=False,
            path="/",
        )
        return resp
    
    @login_manager.unauthorized_handler
    def unauthorized():
        existing_request_id = getattr(g, "request_id", None)
        request_id = existing_request_id or str(uuid4())
        if existing_request_id is None:
            g.request_id = request_id

        raw_user_id = session.get("_user_id")
        user_hash = None
        if raw_user_id is not None:
            user_hash = hashlib.sha256(str(raw_user_id).encode("utf-8")).hexdigest()

        forwarded_for = request.headers.get("X-Forwarded-For")
        client_ip = None
        if forwarded_for:
            client_ip = forwarded_for.split(",")[0].strip()
        if not client_ip:
            client_ip = request.remote_addr

        session_cookie_name = app.config.get("SESSION_COOKIE_NAME", "session")
        session_cookie_value = request.cookies.get(session_cookie_name)
        session_info = {
            "cookie_name": session_cookie_name,
            "cookie_present": session_cookie_value is not None,
            "session_new": getattr(session, "new", None),
            "session_permanent": session.permanent,
            "fresh_login": session.get("_fresh"),
            "remember_token_present": "_remember" in session,
            "user_id_present": raw_user_id is not None,
        }

        if not session_info["cookie_present"]:
            login_state = "session_cookie_missing"
        elif not session_info["user_id_present"]:
            login_state = "session_cookie_without_user_id"
        elif session_info["fresh_login"] is False:
            login_state = "session_not_fresh"
        else:
            login_state = "unknown"

        diagnostics = {
            "login_state": login_state,
            "session_keys": sorted(key for key in session.keys()),
        }

        log_payload = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "id": request_id,
            "event": "auth.unauthorized",
            "message": "Redirected to login due to unauthorized access.",
            "user": {
                "id_hash": user_hash,
                "is_authenticated": raw_user_id is not None,
            },
            "request": {
                "method": request.method,
                "path": request.path,
                "full_path": request.full_path,
                "ip": client_ip,
                "forwarded_for": forwarded_for,
                "user_agent": request.user_agent.string,
            },
            "session": session_info,
            "diagnostics": diagnostics,
        }

        app.logger.warning(
            json.dumps(log_payload, ensure_ascii=False),
            extra={
                "event": "auth.unauthorized",
                "path": request.path,
                "request_id": request_id,
            },
        )

        wants_json = (
            request.is_json
            or request.accept_mimetypes.best_match(["application/json", "text/html"]) == "application/json"
        )
        is_ajax = wants_json or request.headers.get("X-Requested-With") == "XMLHttpRequest"

        if is_ajax:
            response_payload = {
                "status": "error",
                "error": "unauthorized",
                "message": _("Please log in to access this page."),
                "login_state": login_state,
            }
            response = jsonify(response_payload)
            response.status_code = 401
            response.headers["X-Session-Expired"] = "1"
            return response

        # i18nメッセージを自分で出す（カテゴリも自由）
        flash(_("Please log in to access this page."), "error")
        # 元のURLへ戻れるよう next を付ける
        next_url = request.full_path if request.query_string else request.path
        return redirect(url_for("auth.login", next=next_url))

    @app.get("/i18n-probe")
    def i18n_probe():
        return {
            "cookie": request.cookies.get("lang"),
            "locale": str(_select_locale()),
            "t_Login": _("Login"),
            "t_Home": _("Home"),
            "t_LoginMessage": _("Please log in to access this page."),
        }

    @app.route("/.well-known/appspecific/com.chrome.devtools.json")
    def chrome_devtools_json():
        return {}, 204  # 空レスポンスを返す

    with app.app_context():
        db_uri = settings.sqlalchemy_database_uri or ""
        if isinstance(db_uri, str) and db_uri.startswith("sqlite://"):
            db.create_all()

    return app


def _select_locale():
    """1) cookie lang 2) Accept-Language 3) default"""
    from flask import current_app

    if not has_request_context():
        return settings.babel_default_locale or "en"

    cookie_lang = request.cookies.get("lang")
    languages = [lang for lang in settings.languages if lang]
    if cookie_lang in languages:
        return cookie_lang

    best_match = request.accept_languages.best_match(languages) if languages else None
    if best_match:
        return best_match

    return settings.babel_default_locale or "en"


def register_cli_commands(app):
    """CLI コマンドを登録"""
    import click
    from datetime import datetime, timezone
    from core.models.user import User, Role, Permission

    @app.cli.command("version")
    def show_version():
        """アプリケーションのバージョン情報を表示"""
        from core.version import get_version_info, get_version_string
        
        click.echo(_("=== %(app_name)s Version Information ===", app_name=_("AppName")))
        version_info = get_version_info()
        
        click.echo(f"Version: {get_version_string()}")
        click.echo(f"Commit Hash: {version_info['commit_hash']}")
        click.echo(f"Branch: {version_info['branch']}")
        click.echo(f"Commit Date: {version_info['commit_date']}")
        click.echo(f"Build Date: {version_info['build_date']}")

    @app.cli.command("seed-master")
    @click.option('--force', is_flag=True, help='既存データがあっても強制実行')
    def seed_master_data(force):
        """マスタデータを投入"""
        from scripts.seed_master_data import (
            seed_roles, seed_permissions, seed_role_permissions, seed_admin_user
        )
        
        click.echo(_("=== %(app_name)s Master Data Seeding ===", app_name=_("AppName")))
        
        # 既存データチェック
        if not force:
            if Role.query.first() or Permission.query.first():
                click.echo("Warning: Master data already exists. Use --force to override.")
                return
        
        try:
            click.echo("\n1. Seeding roles...")
            seed_roles()
            
            click.echo("\n2. Seeding permissions...")
            seed_permissions()
            
            db.session.commit()
            
            click.echo("\n3. Seeding role-permission relationships...")
            seed_role_permissions()
            
            click.echo("\n4. Seeding admin user...")
            seed_admin_user()
            
            db.session.commit()
            click.echo("\n=== Seeding completed successfully! ===")
            
        except Exception as e:
            db.session.rollback()
            click.echo(f"\n=== Seeding failed: {e} ===", err=True)
            raise click.ClickException(str(e))


def __getattr__(name: str):
    if name == "api":
        module = importlib.import_module("webapp.api")
        globals()[name] = module
        return module
    if name == "auth":
        module = importlib.import_module("webapp.auth")
        globals()[name] = module
        return module
    raise AttributeError(f"module 'webapp' has no attribute {name!r}")

