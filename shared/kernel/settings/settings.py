"""Centralised application settings abstraction.

This module exposes :class:`ApplicationSettings` which consolidates all
configuration lookups that previously relied on ad-hoc ``os.environ`` access
throughout the codebase.  The class is intentionally lightweight and treats the
process environment (or any mapping provided) as the backing store, returning
value objects and sensible defaults where appropriate.

The global :data:`settings` instance should be used for production code, while
tests can instantiate their own :class:`ApplicationSettings` with a dedicated
mapping to validate behaviour in isolation.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import (
    Any,
    ClassVar,
    Iterable,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    TYPE_CHECKING,
    cast,
)

from flask import current_app, has_app_context

from shared.kernel.storage_types import StorageBackendType

from shared.kernel.settings.system_settings_defaults import DEFAULT_APPLICATION_SETTINGS

_DEFAULT_ACCESS_TOKEN_ISSUER = "fpv-webapp"
_DEFAULT_ACCESS_TOKEN_AUDIENCE = "fpv-webapp"

@dataclass(frozen=True)
class _EnvironmentFacade:
    """Thin wrapper that provides ``Mapping`` compatible access to env vars."""

    source: Mapping[str, str]

    @classmethod
    def from_environ(cls, env: Optional[Mapping[str, str]] = None) -> "_EnvironmentFacade":
        return cls(source=os.environ if env is None else env)

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        return self.source.get(key, default)


class _ConcurrencyAccessor:
    """Specialised accessor for concurrency limiter configuration."""

    def __init__(self, settings: "ApplicationSettings") -> None:
        self._settings = settings

    def limit(self, key: str, default: int = 3) -> int:
        return self._settings.get_int(key, default)

    def retry(self, key: Optional[str], default: float = 1.0) -> float:
        if not key:
            return default
        value = self._settings._get(key)
        try:
            return float(value) if value is not None else default
        except (TypeError, ValueError):
            return default


class _StorageAccessor:
    """設定値へのアクセサ.

    サービス生成責務は ``bounded_contexts.storage.application.filesystem_factory``
    へ移管済み。このクラスは設定値の参照のみを担う。
    """

    def __init__(self, settings: "ApplicationSettings") -> None:
        self._settings = settings

    def configured(self, key: str) -> Optional[str]:
        value = self._settings._get(key)
        return str(value) if value else None

    def environment(self, key: str) -> Optional[str]:
        value = self._settings._env.get(key)
        return str(value) if value else None


if TYPE_CHECKING:  # pragma: no cover
    from flask import Flask


class ApplicationSettings:
    """Domain level representation of configuration values.

    The class favours explicit properties instead of generic ``get`` access so
    that the rest of the application operates on intent-revealing names.  This
    improves discoverability, documents available configuration knobs and keeps
    default values in a single location.
    """

    _LEGACY_KEYS: ClassVar[dict[str, tuple[str, ...]]] = {
        # 旧名はフル URL を保持していた。オリジンへの正規化は
        # presentation/web/utils/url_helpers.py 側で行う。
        "GOOGLE_OAUTH_REDIRECT_ORIGIN": ("GOOGLE_OAUTH_REDIRECT_URI",),
        "MEDIA_DOWNLOAD_SIGNING_KEY": ("FPV_DL_SIGN_KEY",),
        "MEDIA_THUMBNAIL_URL_TTL_SECONDS": ("FPV_URL_TTL_THUMB",),
        "MEDIA_PLAYBACK_URL_TTL_SECONDS": ("FPV_URL_TTL_PLAYBACK",),
        "MEDIA_ORIGINAL_URL_TTL_SECONDS": ("FPV_URL_TTL_ORIGINAL",),
        "MEDIA_TEMP_DIRECTORY": ("FPV_TMP_DIR",),
        "MEDIA_UPLOAD_TEMP_DIRECTORY": ("UPLOAD_TMP_DIR",),
        "MEDIA_UPLOAD_DESTINATION_DIRECTORY": ("UPLOAD_DESTINATION_DIR",),
        "MEDIA_UPLOAD_MAX_SIZE_BYTES": ("UPLOAD_MAX_SIZE",),
        "WIKI_UPLOAD_DIRECTORY": ("WIKI_UPLOAD_DIR",),
        "SYSTEM_BACKUP_DIRECTORY": ("MEDIA_BACKUP_DIRECTORY", "BACKUP_DIR"),
        "MEDIA_THUMBNAILS_DIRECTORY": ("FPV_NAS_THUMBS_DIR",),
        "MEDIA_PLAYBACK_DIRECTORY": ("FPV_NAS_PLAY_DIR",),
        "MEDIA_ORIGINALS_DIRECTORY": ("FPV_NAS_ORIGINALS_DIR",),
        "MEDIA_ACCEL_THUMBNAILS_LOCATION": ("FPV_ACCEL_THUMBS_LOCATION",),
        "MEDIA_ACCEL_PLAYBACK_LOCATION": ("FPV_ACCEL_PLAYBACK_LOCATION",),
        "MEDIA_ACCEL_ORIGINALS_LOCATION": ("FPV_ACCEL_ORIGINALS_LOCATION",),
        "MEDIA_ACCEL_REDIRECT_ENABLED": ("FPV_ACCEL_REDIRECT_ENABLED",),
        "MEDIA_LOCAL_IMPORT_DIRECTORY": ("LOCAL_IMPORT_DIR",),
    }

    def __init__(self, env: Optional[Mapping[str, str]] = None) -> None:
        self._env = _EnvironmentFacade.from_environ(env)
        self._concurrency = _ConcurrencyAccessor(self)
        self._storage = _StorageAccessor(self)

    # ------------------------------------------------------------------
    # Generic helpers
    # ------------------------------------------------------------------
    def _get(self, key: str, default: Optional[str] = None):
        app_config = None
        if has_app_context():
            app = cast("Flask", current_app)
            app_config = app.config
            if key in app_config:
                return app_config.get(key)

        value = self._env.get(key)
        if value is not None:
            return value

        for legacy in self._LEGACY_KEYS.get(key, ()):  # pragma: no cover - legacy path
            if app_config and legacy in app_config:
                return app_config.get(legacy)
            legacy_value = self._env.get(legacy)
            if legacy_value is not None:
                return legacy_value

        return default

    def get(self, key: str, default=None):
        """Return the configured value for *key* or *default* if missing."""

        value = self._get(key)
        return default if value is None else value

    def get_bool(self, key: str, default: bool = False) -> bool:
        """Return a boolean configuration value."""

        value = self._get(key)
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            normalised = value.strip().lower()
            if normalised in {"1", "true", "yes", "on"}:
                return True
            if normalised in {"0", "false", "no", "off"}:
                return False
        return default

    def get_int(self, key: str, default: int = 0) -> int:
        """Return an integer configuration value."""

        value = self._get(key)
        if value is None:
            return default
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def get_path(self, key: str, default: Optional[Path | str] = None) -> Optional[Path]:
        """Return a :class:`Path` for the configured value."""

        value = self._get(key)
        if value is not None:
            try:
                return Path(str(value))
            except (TypeError, ValueError):
                return None
        if default is None:
            return None
        return Path(str(default))

    def _path_or_default(self, key: str, fallback: str) -> Path:
        value = self._get(key)
        if value is None:
            return Path(fallback)
        try:
            return Path(str(value))
        except (TypeError, ValueError):
            return Path(fallback)

    # ------------------------------------------------------------------
    # Generic flags
    # ------------------------------------------------------------------
    @property
    def testing(self) -> bool:
        return self.get_bool("TESTING")

    @property
    def login_disabled(self) -> bool:
        return self.get_bool("LOGIN_DISABLED")

    @property
    def session_cookie_secure(self) -> bool:
        return self.get_bool("SESSION_COOKIE_SECURE", False)

    @property
    def require_password_change_on_first_login(self) -> bool:
        """初回ログイン時にパスワード変更を強制するか（既定 False）。"""
        return self.get_bool("REQUIRE_PASSWORD_CHANGE_ON_FIRST_LOGIN", False)

    # ------------------------------------------------------------------
    # Storage paths
    # ------------------------------------------------------------------
    @property
    def storage_backend(self) -> StorageBackendType:
        """Return the configured storage backend implementation.

        The value is resolved from the ``STORAGE_BACKEND`` environment or
        application configuration variable.  When unset, the local filesystem
        backend is used.
        """

        value = self.get("STORAGE_BACKEND", StorageBackendType.LOCAL.value)
        if value is None:
            return StorageBackendType.LOCAL

        normalised = str(value).strip().lower()
        if not normalised:
            return StorageBackendType.LOCAL

        for backend in StorageBackendType:
            if backend.value == normalised:
                return backend

        raise ValueError(
            f"Unsupported storage backend '{value}'. "
            "Available values: "
            + ", ".join(backend.value for backend in StorageBackendType)
        )

    @property
    def tmp_directory(self) -> Path:
        return self._path_or_default("MEDIA_TEMP_DIRECTORY", "/tmp/fpv_tmp")

    @property
    def tmp_directory_configured(self) -> Optional[str]:
        value = self._get("MEDIA_TEMP_DIRECTORY")
        return str(value) if value else None

    @property
    def backup_directory(self) -> Path:
        return self._path_or_default("SYSTEM_BACKUP_DIRECTORY", "/app/data/backups")

    @property
    def storage_originals_directory(self) -> Path:
        return self._path_or_default("MEDIA_ORIGINALS_DIRECTORY", "/app/data/media")

    @property
    def storage_play_directory(self) -> Path:
        return self._path_or_default("MEDIA_PLAYBACK_DIRECTORY", "/app/data/playback")

    @property
    def storage_thumbs_directory(self) -> Path:
        return self._path_or_default("MEDIA_THUMBNAILS_DIRECTORY", "/app/data/thumbs")

    @property
    def storage_local_import_directory(self) -> Path:
        return self._path_or_default("MEDIA_LOCAL_IMPORT_DIRECTORY", "/tmp/local_import")

    @property
    def local_import_directory(self) -> Path:
        return self.storage_local_import_directory

    @property
    def media_originals_directory(self) -> Optional[str]:
        value = self._get("MEDIA_ORIGINALS_DIRECTORY")
        return str(value) if value else None

    @property
    def media_play_directory(self) -> Optional[str]:
        value = self._get("MEDIA_PLAYBACK_DIRECTORY")
        return str(value) if value else None

    @property
    def media_thumbs_directory(self) -> Optional[str]:
        value = self._get("MEDIA_THUMBNAILS_DIRECTORY")
        return str(value) if value else None

    @property
    def local_import_directory_configured(self) -> Optional[str]:
        value = self._get("MEDIA_LOCAL_IMPORT_DIRECTORY")
        return str(value) if value else None

    @property
    def upload_tmp_directory(self) -> Path:
        return self._path_or_default("MEDIA_UPLOAD_TEMP_DIRECTORY", "/app/data/tmp/upload")

    # ------------------------------------------------------------------
    # Concurrency settings
    # ------------------------------------------------------------------
    @property
    def concurrency(self) -> _ConcurrencyAccessor:
        return self._concurrency

    @property
    def storage(self) -> _StorageAccessor:
        return self._storage

    # ------------------------------------------------------------------
    # Celery configuration
    # ------------------------------------------------------------------
    @property
    def celery_broker_url(self) -> str:
        return (
            self._get("CELERY_BROKER_URL")
            or self._get("REDIS_URL")
            or "redis://localhost:6379/0"
        )

    @property
    def celery_result_backend(self) -> str:
        return (
            self._get("CELERY_RESULT_BACKEND")
            or self._get("REDIS_URL")
            or "redis://localhost:6379/0"
        )

    # ------------------------------------------------------------------
    # Database configuration
    # ------------------------------------------------------------------
    @property
    def logs_database_uri(self) -> str:
        return self._get("DATABASE_URI") or "sqlite:///application_logs.db"

    # ------------------------------------------------------------------
    # OAuth / Google configuration
    # ------------------------------------------------------------------
    @property
    def google_client_id(self) -> str:
        return self._get("GOOGLE_CLIENT_ID", "") or ""

    @property
    def google_client_secret(self) -> str:
        return self._get("GOOGLE_CLIENT_SECRET", "") or ""

    @property
    def google_oauth_redirect_origin(self) -> str:
        """Google OAuth コールバック URL のスキーム・ホスト上書き（例:
        ``https://photos.example.com``）。パスは Flask ルートで固定のため含めない。
        空ならリクエストから自動生成する。

        旧キー ``GOOGLE_OAUTH_REDIRECT_URI``（フル URL）も後方互換で参照する。
        既定値ロードにより canonical キーが空文字で常に存在するため、
        ``_LEGACY_KEYS`` の汎用フォールバックでは到達できず、ここで明示する。
        """
        value = self._get("GOOGLE_OAUTH_REDIRECT_ORIGIN", "") or ""
        value = value.strip() if isinstance(value, str) else ""
        if not value:
            legacy = self._get("GOOGLE_OAUTH_REDIRECT_URI", "") or ""
            value = legacy.strip() if isinstance(legacy, str) else ""
        return value

    _DEFAULT_GOOGLE_PHOTO_PICKER_SCOPES: tuple[str, ...] = (
        "https://www.googleapis.com/auth/photospicker.mediaitems.readonly",
        "https://www.googleapis.com/auth/photoslibrary.readonly.appcreateddata",
        "https://www.googleapis.com/auth/photoslibrary.appendonly",
    )

    @property
    def google_photo_picker_scopes(self) -> Sequence[str]:
        """Photo Picker 連携で要求する OAuth スコープの一覧。"""
        value = self._get("GOOGLE_PHOTO_PICKER_SCOPES")
        if value is None:
            return self._DEFAULT_GOOGLE_PHOTO_PICKER_SCOPES
        if isinstance(value, str):
            scopes = [segment.strip() for segment in value.split(",") if segment.strip()]
            return tuple(scopes) or self._DEFAULT_GOOGLE_PHOTO_PICKER_SCOPES
        if isinstance(value, Iterable):
            cleaned = [str(item).strip() for item in value if str(item).strip()]
            return tuple(cleaned) or self._DEFAULT_GOOGLE_PHOTO_PICKER_SCOPES
        return self._DEFAULT_GOOGLE_PHOTO_PICKER_SCOPES

    # ------------------------------------------------------------------
    # Security & Signing
    # ------------------------------------------------------------------
    @property
    def token_encryption_key(self) -> Optional[str]:
        value = self._get("ENCRYPTION_KEY")
        if isinstance(value, str) and value.strip():
            return value.strip()

        default_value = DEFAULT_APPLICATION_SETTINGS.get("ENCRYPTION_KEY")
        if isinstance(default_value, str) and default_value.strip():
            return default_value

        return None

    @property
    def service_account_signing_audiences(self) -> Tuple[str, ...]:
        raw = self._get("SERVICE_ACCOUNT_SIGNING_AUDIENCE")
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            raw = self._env.get("SERVICE_ACCOUNT_SIGNING_AUDIENCE")

        if not raw:
            return ()

        if isinstance(raw, (list, tuple)):
            values = [str(item).strip() for item in raw]
        else:
            values = [segment.strip() for segment in str(raw).split(",")]

        return tuple(value for value in values if value)

    @property
    def access_token_issuer(self) -> str:
        value = self._get("ACCESS_TOKEN_ISSUER", _DEFAULT_ACCESS_TOKEN_ISSUER)
        if not value:
            return _DEFAULT_ACCESS_TOKEN_ISSUER
        return value.strip() or _DEFAULT_ACCESS_TOKEN_ISSUER

    @property
    def access_token_audience(self) -> str:
        value = self._get("ACCESS_TOKEN_AUDIENCE", _DEFAULT_ACCESS_TOKEN_AUDIENCE)
        if not value:
            return _DEFAULT_ACCESS_TOKEN_AUDIENCE
        return value.strip() or _DEFAULT_ACCESS_TOKEN_AUDIENCE

    @property
    def webauthn_rp_id(self) -> str:
        value = self._get("WEBAUTHN_RP_ID")
        if isinstance(value, str) and value.strip():
            return value.strip()

        server_name = self.server_name
        if server_name:
            return server_name.split(":", 1)[0]

        return "localhost"

    @property
    def webauthn_origin(self) -> str:
        value = self._get("WEBAUTHN_ORIGIN")
        if isinstance(value, str) and value.strip():
            return value.strip()

        server_name = self.server_name
        if server_name:
            if server_name.startswith("http://") or server_name.startswith("https://"):
                return server_name
            scheme = self.preferred_url_scheme or "https"
            return f"{scheme}://{server_name}"

        return "http://localhost:5000"

    @property
    def webauthn_rp_name(self) -> str:
        value = self._get("WEBAUTHN_RP_NAME")
        if isinstance(value, str) and value.strip():
            return value.strip()
        return "Nolumia"

    # ------------------------------------------------------------------
    # Media processing configuration
    # ------------------------------------------------------------------
    @property
    def transcode_crf(self) -> int:
        raw = self._get("TRANSCODE_CRF")
        if raw is None:
            raw = self._get("FPV_TRANSCODE_CRF")
        try:
            return int(raw) if raw is not None else 20
        except (TypeError, ValueError):
            return 20

    # ------------------------------------------------------------------
    # API / web configuration
    # ------------------------------------------------------------------
    @property
    def api_base_url(self) -> Optional[str]:
        value = self._get("API_BASE_URL")
        return str(value) if value is not None else None

    @property
    def preferred_url_scheme(self) -> Optional[str]:
        value = self._get("PREFERRED_URL_SCHEME")
        return str(value) if value is not None else None

    @property
    def server_name(self) -> Optional[str]:
        value = self._get("SERVER_NAME")
        return str(value) if value is not None else None

    @property
    def application_root(self) -> Optional[str]:
        value = self._get("APPLICATION_ROOT")
        return str(value) if value is not None else None

    @property
    def babel_translation_directories(self) -> Sequence[str]:
        value = self._get("BABEL_TRANSLATION_DIRECTORIES")
        if value is None:
            return ()
        if isinstance(value, str):
            candidates = [segment.strip() for segment in value.split(";")]
            return tuple(candidate for candidate in candidates if candidate)
        if isinstance(value, Iterable):
            candidates = [str(segment).strip() for segment in value if str(segment).strip()]
            return tuple(candidates)
        return ()

    @property
    def babel_default_locale(self) -> str:
        value = self._get("BABEL_DEFAULT_LOCALE")
        if not value:
            return "en"
        return str(value)

    @property
    def babel_default_timezone(self) -> str:
        value = self._get("BABEL_DEFAULT_TIMEZONE")
        if not value:
            return "UTC"
        return str(value)

    @property
    def languages(self) -> Sequence[str]:
        value = self._get("LANGUAGES")
        if value is None:
            return ("ja", "en")
        if isinstance(value, str):
            languages = [segment.strip() for segment in value.split(",") if segment.strip()]
            return tuple(languages)
        if isinstance(value, Iterable):
            cleaned = [str(item).strip() for item in value if str(item).strip()]
            return tuple(cleaned)
        return ("ja", "en")

    @property
    def cors_allowed_origins(self) -> Sequence[str]:
        value = self._get("CORS_ALLOWED_ORIGINS")
        if value is None:
            return ()
        if isinstance(value, str):
            origins = [segment.strip() for segment in value.split(",") if segment.strip()]
            return tuple(origins)
        if isinstance(value, Iterable):
            return tuple(str(item) for item in value if str(item))
        return ()

    @property
    def openapi_url_prefix(self) -> str:
        value = self._get("OPENAPI_URL_PREFIX")
        if not value:
            return "/api"
        return str(value)

    @property
    def api_spec_options(self) -> dict:
        value = self._get("API_SPEC_OPTIONS")
        if isinstance(value, dict):
            return value
        return {}

    @property
    def werkzeug_run_main(self) -> Optional[str]:
        value = self._get("WERKZEUG_RUN_MAIN")
        return str(value) if value is not None else None

    # ------------------------------------------------------------------
    # Redis / background services
    # ------------------------------------------------------------------
    @property
    def redis_url(self) -> Optional[str]:
        value = self._get("REDIS_URL")
        return str(value) if value is not None else None

    @property
    def last_beat_at(self) -> Any:
        return self._get("LAST_BEAT_AT")

    # ------------------------------------------------------------------
    # Authentication / signing configuration
    # ------------------------------------------------------------------
    @property
    def jwt_secret_key(self) -> Optional[str]:
        value = self._get("JWT_SECRET_KEY")
        return str(value) if value is not None else None

    @property
    def media_download_signing_key(self) -> Optional[str]:
        value = self._get("MEDIA_DOWNLOAD_SIGNING_KEY")
        return str(value) if value is not None else None

    @property
    def media_accel_thumbnails_location(self) -> str:
        value = self._get("MEDIA_ACCEL_THUMBNAILS_LOCATION", "")
        return str(value)

    @property
    def media_accel_playback_location(self) -> str:
        value = self._get("MEDIA_ACCEL_PLAYBACK_LOCATION", "")
        return str(value)

    @property
    def media_accel_originals_location(self) -> str:
        value = self._get("MEDIA_ACCEL_ORIGINALS_LOCATION", "")
        return str(value)

    @property
    def media_accel_redirect_enabled(self) -> bool:
        # X-Accel-Redirect は環境設定が整っていないと 302 リダイレクトで動画再生が失敗する。
        # そのためデフォルトでは無効化し、明示的に有効化した場合のみ利用する。
        return self.get_bool("MEDIA_ACCEL_REDIRECT_ENABLED", False)

    # ------------------------------------------------------------------
    # Media URL configuration
    # ------------------------------------------------------------------
    @property
    def media_thumbnail_url_ttl_seconds(self) -> int:
        return self.get_int("MEDIA_THUMBNAIL_URL_TTL_SECONDS", 600)

    @property
    def media_original_url_ttl_seconds(self) -> int:
        return self.get_int("MEDIA_ORIGINAL_URL_TTL_SECONDS", 600)

    @property
    def media_playback_url_ttl_seconds(self) -> int:
        return self.get_int("MEDIA_PLAYBACK_URL_TTL_SECONDS", 600)

    # ------------------------------------------------------------------
    # Upload configuration
    # ------------------------------------------------------------------
    @property
    def upload_max_size(self) -> int:
        return self.get_int("MEDIA_UPLOAD_MAX_SIZE_BYTES", 100 * 1024 * 1024)

    # ------------------------------------------------------------------
    # Database configuration (extended)
    # ------------------------------------------------------------------
    @property
    def sqlalchemy_database_uri(self) -> Optional[str]:
        value = self._get("SQLALCHEMY_DATABASE_URI")
        return str(value) if value is not None else None

    @property
    def database_uri(self) -> Optional[str]:
        """``DATABASE_URI`` を返す。

        ``SQLALCHEMY_DATABASE_URI`` の元となる接続文字列の環境変数。
        ``create_app`` が実行時に DB を再解決する際の参照元として用いる。
        """
        value = self._get("DATABASE_URI")
        return str(value) if value is not None else None

    # ------------------------------------------------------------------
    # Wiki feature configuration
    # ------------------------------------------------------------------
    @property
    def wiki_upload_directory(self) -> Optional[str]:
        value = self._get("WIKI_UPLOAD_DIRECTORY")
        return str(value) if value is not None else None

    # ------------------------------------------------------------------
    # Mail configuration
    # ------------------------------------------------------------------
    @property
    def mail_server(self) -> str:
        return self._get("MAIL_SERVER", "") or ""

    @property
    def mail_port(self) -> int:
        return self.get_int("MAIL_PORT", 587)

    @property
    def mail_use_tls(self) -> bool:
        return self.get_bool("MAIL_USE_TLS", True)

    @property
    def mail_use_ssl(self) -> bool:
        return self.get_bool("MAIL_USE_SSL", False)

    @property
    def mail_username(self) -> Optional[str]:
        value = self._get("MAIL_USERNAME")
        return str(value) if value is not None else None

    @property
    def mail_password(self) -> Optional[str]:
        value = self._get("MAIL_PASSWORD")
        return str(value) if value is not None else None

    @property
    def mail_default_sender(self) -> Optional[str]:
        value = self._get("MAIL_DEFAULT_SENDER")
        return str(value) if value is not None else None

    @property
    def mail_enabled(self) -> bool:
        return self.get_bool("MAIL_ENABLED", False)

    @property
    def mail_provider(self) -> str:
        """Return the configured mail provider.
        
        Only 'smtp' is supported in production. Defaults to smtp.
        Note: 'console' provider is only available in test environments.
        """
        value = self._get("MAIL_PROVIDER", "smtp")
        if not value:
            return "smtp"
        
        provider = str(value).lower().strip()
        
        # Validate: only smtp is allowed in production
        if provider != "smtp":
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(
                f"Invalid mail provider '{provider}' configured. Only 'smtp' is supported. "
                f"Falling back to 'smtp'. Note: 'console' is only for tests.",
                extra={"event": "settings.mail_provider.invalid"}
            )
            return "smtp"
        
        return provider

    # ------------------------------------------------------------------
    # CDN configuration  
    # ------------------------------------------------------------------
    @property
    def cdn_enabled(self) -> bool:
        """CDN機能の有効/無効."""
        return self.get_bool("CDN_ENABLED", False)
    
    @property 
    def cdn_provider(self) -> str:
        """CDNプロバイダー (none, azure, cloudflare, generic)."""
        value = self._get("CDN_PROVIDER", "none")
        if not value:
            return "none"
        
        provider = str(value).lower().strip()
        valid_providers = ["none", "azure", "cloudflare", "generic"]
        
        if provider not in valid_providers:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(
                f"Invalid CDN provider '{provider}' configured. "
                f"Valid providers: {valid_providers}. Falling back to 'none'.",
                extra={"event": "settings.cdn_provider.invalid"}
            )
            return "none"
        
        return provider
    
    @property
    def cdn_azure_account_name(self) -> Optional[str]:
        """Azure CDNアカウント名."""
        value = self._get("CDN_AZURE_ACCOUNT_NAME")
        return str(value) if value is not None else None
    
    @property
    def cdn_azure_access_key(self) -> Optional[str]:
        """Azure CDNアクセスキー.""" 
        value = self._get("CDN_AZURE_ACCESS_KEY")
        return str(value) if value is not None else None
    
    @property
    def cdn_azure_profile(self) -> Optional[str]:
        """Azure CDNプロファイル名."""
        value = self._get("CDN_AZURE_PROFILE")
        return str(value) if value is not None else None
    
    @property
    def cdn_azure_endpoint(self) -> Optional[str]:
        """Azure CDNエンドポイント名."""
        value = self._get("CDN_AZURE_ENDPOINT")
        return str(value) if value is not None else None
    
    @property
    def cdn_cloudflare_api_token(self) -> Optional[str]:
        """CloudFlare CDN APIトークン."""
        value = self._get("CDN_CLOUDFLARE_API_TOKEN")
        return str(value) if value is not None else None
    
    @property
    def cdn_cloudflare_zone_id(self) -> Optional[str]:
        """CloudFlare CDN ゾーンID."""
        value = self._get("CDN_CLOUDFLARE_ZONE_ID")
        return str(value) if value is not None else None
    
    @property
    def cdn_cloudflare_origin_hostname(self) -> Optional[str]:
        """CloudFlare CDN オリジンホスト名."""
        value = self._get("CDN_CLOUDFLARE_ORIGIN_HOSTNAME")
        return str(value) if value is not None else None
    
    @property
    def cdn_generic_endpoint(self) -> Optional[str]:
        """汎用CDN APIエンドポイント."""
        value = self._get("CDN_GENERIC_ENDPOINT")
        return str(value) if value is not None else None
    
    @property
    def cdn_generic_api_token(self) -> Optional[str]:
        """汎用CDN APIトークン."""
        value = self._get("CDN_GENERIC_API_TOKEN")
        return str(value) if value is not None else None
    
    @property
    def cdn_cache_ttl(self) -> int:
        """CDNキャッシュTTL（秒）."""
        return self.get_int("CDN_CACHE_TTL", 3600)
    
    @property
    def cdn_enable_compression(self) -> bool:
        """CDN圧縮の有効/無効."""
        return self.get_bool("CDN_ENABLE_COMPRESSION", True)
    
    @property
    def cdn_secure_urls_enabled(self) -> bool:
        """CDNセキュアURL機能の有効/無効."""
        return self.get_bool("CDN_SECURE_URLS_ENABLED", False)
    
    @property
    def cdn_access_key(self) -> Optional[str]:
        """CDNセキュアURL用アクセスキー."""
        value = self._get("CDN_ACCESS_KEY")
        return str(value) if value is not None else None

    # ------------------------------------------------------------------
    # Azure Blob Storage configuration
    # ------------------------------------------------------------------
    @property
    def blob_enabled(self) -> bool:
        """Azure Blob Storage機能の有効/無効."""
        return self.get_bool("BLOB_ENABLED", False)
    
    @property
    def blob_provider(self) -> str:
        """Blobストレージプロバイダー (none, azure, local)."""
        value = self._get("BLOB_PROVIDER", "none")
        if not value:
            return "none"
        
        provider = str(value).lower().strip()
        valid_providers = ["none", "azure", "local"]
        
        if provider not in valid_providers:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(
                f"Invalid Blob provider '{provider}' configured. "
                f"Valid providers: {valid_providers}. Falling back to 'none'.",
                extra={"event": "settings.blob_provider.invalid"}
            )
            return "none"
        
        return provider
    
    @property
    def blob_connection_string(self) -> Optional[str]:
        """Azure Blob Storage接続文字列."""
        value = self._get("BLOB_CONNECTION_STRING")
        return str(value) if value is not None else None
    
    @property
    def blob_container_name(self) -> str:
        """Azure Blobコンテナ名."""
        value = self._get("BLOB_CONTAINER_NAME", "photonest")
        return str(value) if value else "photonest"
    
    @property
    def blob_account_name(self) -> Optional[str]:
        """Azure Blobアカウント名."""
        value = self._get("BLOB_ACCOUNT_NAME")
        return str(value) if value is not None else None
    
    @property
    def blob_access_key(self) -> Optional[str]:
        """Azure Blobアクセスキー."""
        value = self._get("BLOB_ACCESS_KEY")
        return str(value) if value is not None else None
    
    @property
    def blob_sas_token(self) -> Optional[str]:
        """Azure Blob SASトークン."""
        value = self._get("BLOB_SAS_TOKEN")
        return str(value) if value is not None else None
    
    @property
    def blob_endpoint_suffix(self) -> str:
        """Azure Blobエンドポイントサフィックス."""
        value = self._get("BLOB_ENDPOINT_SUFFIX", "core.windows.net")
        return str(value) if value else "core.windows.net"
    
    @property
    def blob_secure_transfer(self) -> bool:
        """Azure Blobセキュア転送要求."""
        return self.get_bool("BLOB_SECURE_TRANSFER", True)
    
    @property
    def blob_create_container_if_not_exists(self) -> bool:
        """コンテナ自動作成の有効/無効."""
        return self.get_bool("BLOB_CREATE_CONTAINER_IF_NOT_EXISTS", True)
    
    @property
    def blob_public_access_level(self) -> str:
        """Blobパブリックアクセスレベル (none, blob, container)."""
        value = self._get("BLOB_PUBLIC_ACCESS_LEVEL", "none")
        if not value:
            return "none"
        
        access_level = str(value).lower().strip()
        valid_levels = ["none", "blob", "container"]
        
        if access_level not in valid_levels:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(
                f"Invalid Blob public access level '{access_level}' configured. "
                f"Valid levels: {valid_levels}. Falling back to 'none'.",
                extra={"event": "settings.blob_access_level.invalid"}
            )
            return "none"
        
        return access_level

settings = ApplicationSettings()

__all__ = ["ApplicationSettings", "settings"]
