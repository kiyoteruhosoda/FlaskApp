# webapp/__init__.py
import hashlib
import logging
import importlib
import json
import os
import time
from collections.abc import Mapping, MutableMapping, Sequence
from datetime import datetime, timezone
from uuid import uuid4

from flask import (
    Flask,
    app,
    flash,
    g,
    has_request_context,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from flask_babel import get_locale
from flask_babel import gettext as _
from sqlalchemy.engine import make_url
from typing import Any, Dict, Iterable, List, Optional, Tuple

from werkzeug.datastructures import FileStorage

from .extensions import db, migrate, login_manager, babel, api as smorest_api
from .timezone import resolve_timezone, convert_to_timezone
from core.db_log_handler import DBLogHandler
from core.logging_config import ensure_appdb_file_logging
from core.time import utc_now_isoformat


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


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] == '"':
        return value[1:-1]
    return value


def _parse_forwarded_header(header_value: Optional[str]) -> List[Dict[str, str]]:
    if not header_value:
        return []
    parsed: List[Dict[str, str]] = []
    for part in header_value.split(","):
        params: Dict[str, str] = {}
        for token in part.split(";"):
            token = token.strip()
            if not token or "=" not in token:
                continue
            key, raw_value = token.split("=", 1)
            key = key.strip().lower()
            value = _strip_quotes(raw_value.strip())
            if not key:
                continue
            params[key] = value
        if params:
            parsed.append(params)
    return parsed


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


def _iter_non_empty(values: Iterable[Optional[str]]) -> Iterable[str]:
    for value in values:
        if value:
            stripped = value.strip()
            if stripped:
                yield stripped


def _normalize_scheme(scheme: Optional[str]) -> Optional[str]:
    if not scheme:
        return None
    normalized = scheme.strip().lower()
    return normalized or None


def _split_host_and_port(host: str) -> Tuple[str, Optional[int]]:
    if not host:
        return "", None
    stripped = host.strip()
    if not stripped:
        return "", None
    if stripped.startswith("["):
        closing_index = stripped.find("]")
        if closing_index != -1:
            core = stripped[: closing_index + 1].lower()
            remainder = stripped[closing_index + 1 :]
            if remainder.startswith(":") and remainder[1:].isdigit():
                return core, int(remainder[1:])
            return core, None
        return stripped.lower(), None
    if ":" in stripped:
        host_part, port_part = stripped.rsplit(":", 1)
        if port_part.isdigit():
            return host_part.lower(), int(port_part)
    return stripped.lower(), None


def _default_port_for_scheme(scheme: str) -> Optional[int]:
    scheme_lower = scheme.lower()
    if scheme_lower == "https":
        return 443
    if scheme_lower == "http":
        return 80
    return None


def _calculate_openapi_server_urls(prefix: str) -> List[str]:
    script_root = _normalize_script_root(request.script_root)
    trusted_scheme = request.scheme or ""
    trusted_scheme_lower = trusted_scheme.lower()
    trusted_host = request.host or ""
    normalized_trusted_host, trusted_port = _split_host_and_port(trusted_host)
    default_trusted_port = _default_port_for_scheme(trusted_scheme_lower)

    def is_trusted_host(candidate: Optional[str]) -> bool:
        if not candidate:
            return False
        host_value = _strip_quotes(candidate)
        host, port = _split_host_and_port(host_value)
        if not host or host != normalized_trusted_host:
            return False
        if trusted_port is None:
            if port is None:
                return True
            if default_trusted_port is None:
                return False
            return port == default_trusted_port
        return port == trusted_port

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

    for params in _parse_forwarded_header(request.headers.get("Forwarded")):
        host = params.get("host")
        proto = params.get("proto") or params.get("scheme")
        if host and not is_trusted_host(host):
            continue
        candidate_host = _strip_quotes(host) if host else trusted_host
        candidate_scheme = _normalize_scheme(proto) or trusted_scheme
        if candidate_host and candidate_scheme:
            base = _build_base_url(candidate_scheme, candidate_host, script_root)
            add_url(urls, seen, base)

    forwarded_hosts_header = request.headers.get("X-Forwarded-Host", "")
    forwarded_hosts = list(_iter_non_empty(forwarded_hosts_header.split(",")))
    forwarded_protos_raw = list(
        _iter_non_empty(request.headers.get("X-Forwarded-Proto", "").split(","))
    )

    for forwarded_host in forwarded_hosts:
        if not is_trusted_host(forwarded_host):
            continue
        candidate_host = _strip_quotes(forwarded_host)
        if candidate_host:
            base = _build_base_url(trusted_scheme, candidate_host, script_root)
            add_url(urls, seen, base)

    for proto in forwarded_protos_raw:
        normalized_proto = _normalize_scheme(_strip_quotes(proto))
        if not normalized_proto:
            continue
        base = _build_base_url(normalized_proto, trusted_host, script_root)
        add_url(urls, seen, base)

    url_root_base = request.url_root.rstrip("/")
    if url_root_base:
        add_url(urls, seen, url_root_base)
    else:
        host_base = _build_base_url(request.scheme, request.host, script_root)
        add_url(urls, seen, host_base)

    host_url_base = request.host_url.rstrip("/")
    if host_url_base:
        base = host_url_base
        if script_root and script_root != "/":
            base = f"{base}{script_root}"
        add_url(urls, seen, base)

    return urls or ["/" if not prefix else prefix]


# エラーハンドラ
from werkzeug.exceptions import HTTPException


def create_app():
    """アプリケーションファクトリ"""
    from dotenv import load_dotenv
    from .config import Config
    from werkzeug.middleware.proxy_fix import ProxyFix

    # .env を読み込む（環境変数が未設定の場合のみ）
    load_dotenv()

    app = Flask(__name__)
    app.config.from_object(Config)
    app.config.setdefault("LAST_BEAT_AT", None)
    app.config.setdefault("API_TITLE", "nolumia API")
    app.config.setdefault("API_VERSION", "1.0.0")
    app.config.setdefault("OPENAPI_VERSION", "3.0.3")
    app.config.setdefault("OPENAPI_URL_PREFIX", "/api")
    app.config.setdefault("OPENAPI_JSON_PATH", "openapi.json")
    app.config.setdefault("OPENAPI_SWAGGER_UI_PATH", "docs")
    app.config.setdefault(
        "OPENAPI_SWAGGER_UI_URL",
        "https://cdn.jsdelivr.net/npm/swagger-ui-dist/",
    )
    app.config.setdefault("API_SPEC_OPTIONS", {})

    database_uri = app.config.get("SQLALCHEMY_DATABASE_URI")
    testing_mode = app.config.get("TESTING") or str(os.environ.get("TESTING", "")).lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if testing_mode and database_uri and database_uri.startswith("sqlite:///"):
        db_path = database_uri.replace("sqlite:///", "", 1)
        if db_path and db_path != ":memory:":
            try:
                os.remove(db_path)
            except FileNotFoundError:
                pass

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
    babel.init_app(app, locale_selector=_select_locale)
    smorest_api.init_app(app)

    configured_servers = app.config.get("API_SPEC_OPTIONS", {}).get("servers")

    @app.before_request
    def _refresh_openapi_server_urls():
        if configured_servers:
            return
        spec = getattr(smorest_api, "spec", None)
        if spec is None:
            return
        prefix = _normalize_openapi_prefix(app.config.get("OPENAPI_URL_PREFIX", "/api"))
        server_urls = _calculate_openapi_server_urls(prefix)
        spec.options["servers"] = [{"url": url} for url in server_urls]

    # ★ Jinja から get_locale() を使えるようにする
    app.jinja_env.globals["get_locale"] = get_locale

    # テンプレートコンテキストプロセッサ：バージョン情報とタイムゾーンを追加
    from core.version import get_version_string

    @app.before_request
    def _set_request_timezone():
        tz_cookie = request.cookies.get("tz")
        fallback = app.config.get("BABEL_DEFAULT_TIMEZONE", "UTC")
        tz_name, tzinfo = resolve_timezone(tz_cookie, fallback)
        g.user_timezone_name = tz_name
        g.user_timezone = tzinfo

    @app.context_processor
    def inject_version():
        languages = [str(lang).strip() for lang in app.config.get("LANGUAGES", ["ja", "en"]) if lang]
        if not languages:
            default_language = app.config.get("BABEL_DEFAULT_LOCALE", "en")
            if default_language:
                languages = [default_language]

        default_language = app.config.get("BABEL_DEFAULT_LOCALE", languages[0] if languages else "en")

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

    testing_env = os.environ.get("TESTING", "").strip().lower()
    disable_db_logging = app.config.get("TESTING") or testing_env in {"1", "true", "yes", "on"}

    # Logging configuration
    if not disable_db_logging:
        if not any(isinstance(h, DBLogHandler) for h in app.logger.handlers):
            db_handler = DBLogHandler(app=app)
            db_handler.setLevel(logging.INFO)
            app.logger.addHandler(db_handler)

        ensure_appdb_file_logging(app.logger)

        should_bind_db_handlers = True
        database_uri = app.config.get("SQLALCHEMY_DATABASE_URI")
        if database_uri:
            try:
                url = make_url(database_uri)
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
    from features.certs.infrastructure import models as _cert_models  # noqa: F401


    # Blueprint 登録
    from .auth import bp as auth_bp
    app.register_blueprint(auth_bp, url_prefix="/auth")
    from .auth.routes import picker as picker_view
    app.add_url_rule("/picker/<int:account_id>", view_func=picker_view, endpoint="picker")

    from .dashboard import bp as dashboard_bp
    app.register_blueprint(dashboard_bp, url_prefix="/dashboard")

    from .admin.routes import bp as admin_bp
    app.register_blueprint(admin_bp, url_prefix="/admin")

    from features.photonest.presentation.photo_view import bp as photo_view_bp
    app.register_blueprint(photo_view_bp)

    from .api import bp as api_bp
    api_url_prefix = "/api"
    smorest_api.register_blueprint(api_bp, url_prefix=api_url_prefix)
    _strip_openapi_path_prefix(smorest_api.spec, api_url_prefix)

    # 認証なしの健康チェック用Blueprint
    from .health import health_bp
    app.register_blueprint(health_bp, url_prefix="/health")

    # デバッグ用Blueprint（開発環境のみ）
    if app.debug or app.config.get('TESTING'):
        from .debug_routes import debug_bp
        app.register_blueprint(debug_bp, url_prefix="/debug")

    from features.wiki.presentation.wiki import bp as wiki_bp
    app.register_blueprint(wiki_bp, url_prefix="/wiki")

    from features.totp.presentation import bp as totp_bp
    app.register_blueprint(totp_bp, url_prefix="/totp")

    from features.certs.presentation.ui import certs_ui_bp
    app.register_blueprint(certs_ui_bp, url_prefix="/certs")

    from features.certs.presentation.api import certs_api_bp
    app.register_blueprint(certs_api_bp, url_prefix="/api")

    # CLI コマンド登録
    register_cli_commands(app)

    @app.before_request
    def _apply_login_disabled_for_testing():
        if app.config.get("TESTING"):
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

    # 404だけ個別に（テンプレでもJSONでも可）
    @app.errorhandler(404)
    def handle_404(e):
        app.logger.warning(
            "404 path=%s full=%s ua=%s",
            request.path,
            request.full_path,
            request.user_agent,
        )
        # return render_template("404.html"), 404
        return jsonify(error="Not Found"), 404

    @app.errorhandler(Exception)
    def handle_exception(e):
        is_http = isinstance(e, HTTPException)
        code = e.code if is_http else 500
        # 外部公開メッセージ：5xxは伏せる（内部情報漏えい対策）
        public_message = e.description if (is_http and code < 500) else "Internal Server Error"

        # ログ用の詳細（必要に応じてマスキング）
        try:
            input_json = request.get_json(silent=True)
        except Exception:
            input_json = None

        log_dict = {
            "method": request.method,
            "path": request.path,
            "full_path": request.full_path,
            "ua": request.user_agent.string,
            "status": code,
        }
        qs = request.query_string.decode()
        if qs:
            log_dict["query_string"] = qs

        form_dict = request.form.to_dict()
        if form_dict:
            log_dict["form"] = _mask_sensitive_data(form_dict)

        if input_json is not None:
            log_dict["json"] = _mask_sensitive_data(input_json)

        # ★ ログ出力方針：4xxはstackなし、5xxはstack付き
        if is_http and 400 <= code < 500:
            app.logger.warning(json.dumps(log_dict, ensure_ascii=False),
                            extra={"event": "api.http_4xx", "request_id": getattr(g, "request_id", None)})
        else:
            # 5xxのみ stacktrace
            app.logger.exception(json.dumps(log_dict, ensure_ascii=False),
                                extra={"event": "api.http_5xx", "request_id": getattr(g, "request_id", None)})

        g.exception_logged = True

        # レスポンス
        if request.path.startswith("/api"):
            # 5xxの詳細messageは返さない（public_messageに統一）
            return jsonify({"error": "error", "message": public_message}), code

        # HTML（5xxはgenericに）
        return render_template("error.html", message=public_message), code

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

    # ルート
    @app.route("/")
    def index():
        # HTML レスポンスを生成
        return make_response(render_template("index.html"))

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
        }

        app.logger.warning(
            json.dumps(log_payload, ensure_ascii=False),
            extra={
                "event": "auth.unauthorized",
                "path": request.path,
                "request_id": request_id,
            },
        )

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

    db_uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
    if db_uri.startswith("sqlite://"):
        with app.app_context():
            db.create_all()

    return app


def _select_locale():
    """1) cookie lang 2) Accept-Language 3) default"""
    from flask import current_app

    if not has_request_context():
        return current_app.config.get("BABEL_DEFAULT_LOCALE", "en")

    cookie_lang = request.cookies.get("lang")
    if cookie_lang in current_app.config["LANGUAGES"]:
        return cookie_lang
    return request.accept_languages.best_match(current_app.config["LANGUAGES"])


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

