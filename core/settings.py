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
    Callable,
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

from domain.storage import StorageBackendType, StorageDomain, StorageIntent

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


StorageFactory = Callable[
    [Callable[[str], Optional[str]] | None, Callable[[str], Optional[str]] | None],
    "StorageService",
]


class _StorageAccessor:
    """Helper accessor exposing raw storage configuration values."""

    def __init__(self, settings: "ApplicationSettings") -> None:
        self._settings = settings
        self._service: Optional["StorageService"] = None
        self._service_overridden = False
        self._factories: dict[StorageBackendType, StorageFactory] = {}
        self.register_backend(StorageBackendType.LOCAL, self._create_local_service)
        self.register_backend(
            StorageBackendType.AZURE_BLOB, self._create_azure_blob_service
        )
        self.register_backend(
            StorageBackendType.EXTERNAL_REST, self._create_external_rest_service
        )

    def configured(self, key: str) -> Optional[str]:
        value = self._settings._get(key)
        return str(value) if value else None

    def environment(self, key: str) -> Optional[str]:
        value = self._settings._env.get(key)
        return str(value) if value else None

    def set_service(self, service: "StorageService") -> None:
        """Inject a custom storage service implementation."""

        self._service = service
        self._service_overridden = True

    def register_backend(
        self, backend: StorageBackendType, factory: StorageFactory
    ) -> None:
        """Register a factory used to instantiate a storage backend.

        The registration can happen at application start-up.  When the active
        backend matches *backend*, the cached service instance is cleared so
        that subsequent :meth:`service` calls use the freshly registered
        factory.
        """

        self._factories[backend] = factory
        if (
            not self._service_overridden
            and self._service is not None
            and self._settings.storage_backend is backend
        ):
            self._service = None

    def _create_local_service(
        self,
        config_resolver: Callable[[str], Optional[str]] | None,
        env_resolver: Callable[[str], Optional[str]] | None,
    ) -> "StorageService":
        from core.storage_service import LocalFilesystemStorageService

        return cast(
            "StorageService",
            LocalFilesystemStorageService(
                config_resolver=config_resolver,
                env_resolver=env_resolver,
            ),
        )

    def _create_azure_blob_service(
        self,
        config_resolver: Callable[[str], Optional[str]] | None,
        env_resolver: Callable[[str], Optional[str]] | None,
    ) -> "StorageService":
        from core.storage_service import AzureBlobStorageService

        return cast(
            "StorageService",
            AzureBlobStorageService(
                config_resolver=config_resolver,
                env_resolver=env_resolver,
            ),
        )

    def _create_external_rest_service(
        self,
        config_resolver: Callable[[str], Optional[str]] | None,
        env_resolver: Callable[[str], Optional[str]] | None,
    ) -> "StorageService":
        from core.storage_service import ExternalRestStorageService

        return cast(
            "StorageService",
            ExternalRestStorageService(
                config_resolver=config_resolver,
                env_resolver=env_resolver,
            ),
        )

    def service(self) -> "StorageService":
        """Return the active :class:`StorageService` implementation."""

        if self._service is None:
            backend = self._settings.storage_backend
            factory = self._factories.get(backend)
            if factory is None:
                raise ValueError(f"Storage backend '{backend.value}' is not registered")

            self._service = factory(self.configured, self.environment)
            self._service_overridden = False

        return cast("StorageService", self._service)

    def directory(self, domain: StorageDomain) -> Path:
        """Return a concrete :class:`Path` for *domain*.

        The lookup prioritises configured values, then environment overrides,
        finally falling back to service defaults.  The method intentionally
        mirrors the previous ``ApplicationSettings._storage_directory`` helper
        but keeps the resolution logic co-located with the storage accessor so
        that callers operate on :class:`Path` objects rather than strings.
        """

        service = self.service()
        area = service.for_domain(domain)

        existing = area.first_existing()
        if existing:
            return Path(existing)

        candidates = area.candidates(intent=StorageIntent.WRITE)
        if candidates:
            return Path(candidates[0])

        defaults = service.defaults(area.config_key)
        if defaults:
            return Path(defaults[0])

        raise RuntimeError(f"No storage candidates configured for domain: {domain!s}")


if TYPE_CHECKING:  # pragma: no cover
    from flask import Flask
    from core.storage_service import StorageService


class ApplicationSettings:
    """Domain level representation of configuration values.

    The class favours explicit properties instead of generic ``get`` access so
    that the rest of the application operates on intent-revealing names.  This
    improves discoverability, documents available configuration knobs and keeps
    default values in a single location.
    """

    _LEGACY_KEYS: ClassVar[dict[str, tuple[str, ...]]] = {
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
        return self.storage.directory(StorageDomain.MEDIA_ORIGINALS)

    @property
    def storage_play_directory(self) -> Path:
        return self.storage.directory(StorageDomain.MEDIA_PLAYBACK)

    @property
    def storage_thumbs_directory(self) -> Path:
        return self.storage.directory(StorageDomain.MEDIA_THUMBNAILS)

    @property
    def storage_local_import_directory(self) -> Path:
        return self.storage.directory(StorageDomain.MEDIA_IMPORT)

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

    # ------------------------------------------------------------------
    # Security & Signing
    # ------------------------------------------------------------------
    @property
    def token_encryption_key(self) -> Optional[str]:
        return self._get("ENCRYPTION_KEY")

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

    # ------------------------------------------------------------------
    # Wiki feature configuration
    # ------------------------------------------------------------------
    @property
    def wiki_upload_directory(self) -> Optional[str]:
        value = self._get("WIKI_UPLOAD_DIRECTORY")
        return str(value) if value is not None else None
settings = ApplicationSettings()

__all__ = ["ApplicationSettings", "settings"]
