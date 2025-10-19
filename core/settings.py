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
import json
import os
from pathlib import Path
from typing import Iterable, Mapping, Optional, Tuple

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


class ApplicationSettings:
    """Domain level representation of configuration values.

    The class favours explicit properties instead of generic ``get`` access so
    that the rest of the application operates on intent-revealing names.  This
    improves discoverability, documents available configuration knobs and keeps
    default values in a single location.
    """

    def __init__(self, env: Optional[Mapping[str, str]] = None) -> None:
        self._env = _EnvironmentFacade.from_environ(env)

    # ------------------------------------------------------------------
    # Generic helpers
    # ------------------------------------------------------------------
    def _get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        return self._env.get(key, default)

    # ------------------------------------------------------------------
    # Storage paths
    # ------------------------------------------------------------------
    @property
    def tmp_directory(self) -> Path:
        return Path(self._get("FPV_TMP_DIR", "/tmp/fpv_tmp"))

    @property
    def backup_directory(self) -> Path:
        return Path(self._get("BACKUP_DIR", "/app/data/backups"))

    @property
    def nas_originals_directory(self) -> Path:
        from core.storage_paths import first_existing_storage_path

        base = first_existing_storage_path("FPV_NAS_ORIGINALS_DIR")
        if base:
            return Path(base)
        return Path("/tmp/fpv_orig")

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
    def cors_allowed_origins(self) -> Tuple[str, ...]:
        """Return the list of origins allowed for cross-origin requests."""

        candidate_paths = []
        path_value = self._get("CORS_ALLOWED_ORIGINS_FILE")
        if path_value:
            candidate_paths.append(Path(path_value).expanduser())

        candidate_paths.extend(
            [
                Path("/app/config/cors_allowed_origins.txt"),
                Path("/app/config/cors_allowed_origins.json"),
                Path.cwd() / "config" / "cors_allowed_origins.txt",
                Path.cwd() / "config" / "cors_allowed_origins.json",
            ]
        )

        seen: set[Path] = set()
        for candidate in candidate_paths:
            if candidate in seen:
                continue
            seen.add(candidate)
            origins = _load_cors_origins_from_file(candidate)
            if origins:
                return origins

        env_value = self._get("CORS_ALLOWED_ORIGINS")
        if env_value:
            values = [segment.strip() for segment in env_value.split(",")]
            return _normalize_origin_values(values)

        return ()

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
        raw = self._get("FPV_TRANSCODE_CRF")
        try:
            return int(raw) if raw is not None else 20
        except (TypeError, ValueError):
            return 20


# Default settings instance used by the application.
def _normalize_origin_values(values: Iterable[object]) -> Tuple[str, ...]:
    normalized: list[str] = []
    for value in values:
        if value is None:
            continue
        if isinstance(value, bytes):
            candidate = value.decode("utf-8", errors="ignore").strip()
        else:
            candidate = str(value).strip()
        if not candidate or candidate in normalized:
            continue
        normalized.append(candidate)
    return tuple(normalized)


def _load_cors_origins_from_file(path: Path) -> Tuple[str, ...]:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ()
    except OSError:
        return ()

    content = text.strip()
    if not content:
        return ()

    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        pass
    else:
        if isinstance(data, (list, tuple)):
            return _normalize_origin_values(data)
        if isinstance(data, str):
            return _normalize_origin_values([data])

    lines = []
    for raw_line in content.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        lines.append(line)
    return _normalize_origin_values(lines)


settings = ApplicationSettings()

__all__ = ["ApplicationSettings", "settings"]
