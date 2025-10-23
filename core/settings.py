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

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence, Tuple, TYPE_CHECKING

from flask import current_app

from domain.storage import StorageDomain

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
    """Helper accessor exposing raw storage configuration values."""

    def __init__(self, settings: "ApplicationSettings") -> None:
        self._settings = settings
        self._service: Optional["StorageService"] = None

    def configured(self, key: str) -> Optional[str]:
        value = self._settings._get(key)
        return str(value) if value else None

    def environment(self, key: str) -> Optional[str]:
        value = self._settings._env.get(key)
        return str(value) if value else None

    def set_service(self, service: "StorageService") -> None:
        """Inject a custom storage service implementation."""

        self._service = service

    def service(self) -> "StorageService":
        """Return the active :class:`StorageService` implementation."""

        if self._service is None:
            from core.storage_service import LocalFilesystemStorageService

            self._service = LocalFilesystemStorageService(
                config_resolver=self.configured,
                env_resolver=self.environment,
            )
        return self._service


if TYPE_CHECKING:  # pragma: no cover
    from core.storage_service import StorageService


class ApplicationSettings:
    """Domain level representation of configuration values.

    The class favours explicit properties instead of generic ``get`` access so
    that the rest of the application operates on intent-revealing names.  This
    improves discoverability, documents available configuration knobs and keeps
    default values in a single location.
    """

    def __init__(self, env: Optional[Mapping[str, str]] = None) -> None:
        self._env = _EnvironmentFacade.from_environ(env)
        self._concurrency = _ConcurrencyAccessor(self)
        self._storage = _StorageAccessor(self)

    # ------------------------------------------------------------------
    # Generic helpers
    # ------------------------------------------------------------------
    def _get(self, key: str, default: Optional[str] = None):
        try:
            app = current_app._get_current_object()
        except RuntimeError:
            app = None
        if app is not None and key in app.config:
            return app.config.get(key)
        return self._env.get(key, default)

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
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def get_path(self, key: str, default: Optional[Path | str] = None) -> Optional[Path]:
        """Return a :class:`Path` for the configured value."""

        value = self._get(key)
        if value:
            try:
                return Path(value)
            except TypeError:
                return None
        if default is None:
            return None
        return Path(default)

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

    # ------------------------------------------------------------------
    # Storage paths
    # ------------------------------------------------------------------
    def _storage_directory(self, domain: StorageDomain, fallback: str) -> Path:
        storage = self.storage.service()
        area = storage.for_domain(domain)
        base = area.first_existing()
        if base:
            return Path(base)
        candidates = area.candidates()
        if candidates:
            return Path(candidates[0])
        return Path(fallback)

    @property
    def tmp_directory(self) -> Path:
        return Path(self._get("FPV_TMP_DIR", "/tmp/fpv_tmp"))

    @property
    def tmp_directory_configured(self) -> Optional[str]:
        value = self._get("FPV_TMP_DIR")
        return str(value) if value else None

    @property
    def backup_directory(self) -> Path:
        return Path(self._get("BACKUP_DIR", "/app/data/backups"))

    @property
    def nas_originals_directory(self) -> Path:
        return self._storage_directory(StorageDomain.MEDIA_ORIGINALS, "/tmp/fpv_orig")

    @property
    def nas_play_directory(self) -> Path:
        return self._storage_directory(StorageDomain.MEDIA_PLAYBACK, "/tmp/fpv_play")

    @property
    def nas_thumbs_directory(self) -> Path:
        return self._storage_directory(StorageDomain.MEDIA_THUMBNAILS, "/tmp/fpv_thumbs")

    @property
    def local_import_directory(self) -> Path:
        return self._storage_directory(StorageDomain.MEDIA_IMPORT, "/tmp/local_import")

    @property
    def nas_originals_directory_configured(self) -> Optional[str]:
        value = self._get("FPV_NAS_ORIGINALS_DIR")
        return str(value) if value else None

    @property
    def nas_play_directory_configured(self) -> Optional[str]:
        value = self._get("FPV_NAS_PLAY_DIR")
        return str(value) if value else None

    @property
    def nas_thumbs_directory_configured(self) -> Optional[str]:
        value = self._get("FPV_NAS_THUMBS_DIR")
        return str(value) if value else None

    @property
    def local_import_directory_configured(self) -> Optional[str]:
        value = self._get("LOCAL_IMPORT_DIR")
        return str(value) if value else None

    @property
    def upload_tmp_directory(self) -> Path:
        return Path(self._get("UPLOAD_TMP_DIR", "/app/data/tmp/upload"))

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
    def oauth_token_key(self) -> Optional[str]:
        return self._get("OAUTH_TOKEN_KEY")

    @property
    def oauth_token_key_file(self) -> Optional[str]:
        path = self._get("OAUTH_TOKEN_KEY_FILE")
        if path:
            return path
        return self._get("FPV_OAUTH_TOKEN_KEY_FILE")

    # ------------------------------------------------------------------
    # Service account configuration
    # ------------------------------------------------------------------
    @property
    def service_account_signing_audiences(self) -> Tuple[str, ...]:
        raw = self._get("SERVICE_ACCOUNT_SIGNING_AUDIENCE", "") or ""
        if not raw:
            return ()
        values = [segment.strip() for segment in raw.split(",")]
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
    def fpv_download_signing_key(self) -> Optional[str]:
        value = self._get("FPV_DL_SIGN_KEY")
        return str(value) if value is not None else None

    @property
    def fpv_accel_thumbs_location(self) -> str:
        value = self._get("FPV_ACCEL_THUMBS_LOCATION", "")
        return str(value)

    @property
    def fpv_accel_playback_location(self) -> str:
        value = self._get("FPV_ACCEL_PLAYBACK_LOCATION", "")
        return str(value)

    @property
    def fpv_accel_originals_location(self) -> str:
        value = self._get("FPV_ACCEL_ORIGINALS_LOCATION", "")
        return str(value)

    @property
    def fpv_accel_redirect_enabled(self) -> bool:
        return self.get_bool("FPV_ACCEL_REDIRECT_ENABLED", True)

    # ------------------------------------------------------------------
    # Media URL configuration
    # ------------------------------------------------------------------
    @property
    def fpv_url_ttl_thumb(self) -> int:
        return self.get_int("FPV_URL_TTL_THUMB", 600)

    @property
    def fpv_url_ttl_original(self) -> int:
        return self.get_int("FPV_URL_TTL_ORIGINAL", 600)

    @property
    def fpv_url_ttl_playback(self) -> int:
        return self.get_int("FPV_URL_TTL_PLAYBACK", 600)

    # ------------------------------------------------------------------
    # Upload configuration
    # ------------------------------------------------------------------
    @property
    def upload_max_size(self) -> int:
        return self.get_int("UPLOAD_MAX_SIZE", 100 * 1024 * 1024)

    # ------------------------------------------------------------------
    # Database configuration (extended)
    # ------------------------------------------------------------------
    @property
    def sqlalchemy_database_uri(self) -> Optional[str]:
        value = self._get("SQLALCHEMY_DATABASE_URI")
        return str(value) if value is not None else None

    # ------------------------------------------------------------------
    # Wiki feature configuration
    # ------------------------------------------------------------------
    @property
    def wiki_upload_directory(self) -> Optional[str]:
        value = self._get("WIKI_UPLOAD_DIR")
        return str(value) if value is not None else None
settings = ApplicationSettings()

__all__ = ["ApplicationSettings", "settings"]
