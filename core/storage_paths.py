"""Utility helpers for resolving NAS storage paths used across the app.

These helpers mirror the logic previously embedded in the web routes so that
background tasks (such as the local import and thumbnail workers) can resolve
container-friendly storage paths without duplicating code."""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Tuple

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from core.settings import ApplicationSettings

# Mapping of config keys to environment variable fallbacks (in priority order).
_STORAGE_ENV_FALLBACKS: dict[str, Tuple[str, ...]] = {
    "FPV_NAS_THUMBS_DIR": (
        "FPV_NAS_THUMBS_CONTAINER_DIR",
        "FPV_NAS_THUMBS_DIR",
    ),
    "FPV_NAS_PLAY_DIR": (
        "FPV_NAS_PLAY_CONTAINER_DIR",
        "FPV_NAS_PLAY_DIR",
    ),
    "FPV_NAS_ORIGINALS_DIR": (
        "FPV_NAS_ORIGINALS_CONTAINER_DIR",
        "FPV_NAS_ORIGINALS_DIR",
    ),
    "LOCAL_IMPORT_DIR": (
        "LOCAL_IMPORT_CONTAINER_DIR",
        "LOCAL_IMPORT_DIR",
    ),
}

# Default fallback paths (ordered) when config/environment do not provide
# anything usable.  These defaults prefer the container mount points but also
# keep legacy fallbacks for backwards compatibility.
_STORAGE_DEFAULTS: dict[str, Tuple[str, ...]] = {
    "FPV_NAS_THUMBS_DIR": ("/app/data/thumbs", "/tmp/fpv_thumbs"),
    "FPV_NAS_PLAY_DIR": ("/app/data/playback", "/tmp/fpv_play"),
    "FPV_NAS_ORIGINALS_DIR": ("/app/data/media", "/tmp/fpv_orig"),
    "LOCAL_IMPORT_DIR": ("/tmp/local_import",),
}


def _active_settings() -> "ApplicationSettings":
    from core.settings import settings as app_settings

    return app_settings


def _config_value(config_key: str) -> str | None:
    """Return the configured value for *config_key* if available."""

    settings = _active_settings()
    value = settings.storage.configured(config_key)
    if value:
        return value
    return None


def storage_path_candidates(config_key: str) -> List[str]:
    """Return an ordered list of candidate paths for *config_key*."""

    seen: set[str] = set()
    candidates: List[str] = []

    config_value = _config_value(config_key)
    if config_value and config_value not in seen:
        candidates.append(config_value)
        seen.add(config_value)

    settings = _active_settings()
    for env_name in _STORAGE_ENV_FALLBACKS.get(config_key, (config_key,)):
        env_value = settings.storage.environment(env_name)
        if env_value and env_value not in seen:
            candidates.append(env_value)
            seen.add(env_value)

    for default_value in _STORAGE_DEFAULTS.get(config_key, ()):  # type: ignore[arg-type]
        if default_value and default_value not in seen:
            candidates.append(default_value)
            seen.add(default_value)

    return [candidate for candidate in candidates if candidate]


def first_existing_storage_path(config_key: str) -> str | None:
    """Return the first candidate path that exists for *config_key*.

    If none of the candidates currently exist, the first candidate (if any) is
    returned so that callers can create the directory proactively.
    """

    candidates = storage_path_candidates(config_key)
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate

    return candidates[0] if candidates else None


PathPart = str | os.PathLike[str] | bytes


def _normalise_path_parts(path_parts: Tuple[PathPart, ...]) -> Tuple[str, ...] | None:
    """Return a tuple of normalised path parts or ``None`` if invalid."""

    if not path_parts:
        return ()

    normalised: List[str] = []
    for part in path_parts:
        if part is None:  # type: ignore[comparison-overlap]
            return None
        try:
            part_str = os.fsdecode(part)
        except TypeError:
            return None
        if not part_str:
            return None
        normalised.append(part_str)

    return tuple(normalised)


def resolve_storage_file(
    config_key: str, *path_parts: PathPart
) -> Tuple[str | None, str | None, bool]:
    """Resolve a file path relative to *config_key* storage directories.

    Returns a tuple of ``(base_path, resolved_path, exists)`` where ``exists``
    indicates whether the resolved path is present on disk.
    """

    candidates = storage_path_candidates(config_key)

    normalised_parts = _normalise_path_parts(path_parts)
    if normalised_parts is None:
        return None, None, False

    if not normalised_parts:
        for base in candidates:
            if os.path.exists(base):
                return base, base, True
        fallback_base = candidates[0] if candidates else None
        return fallback_base, fallback_base, False

    for base in candidates:
        candidate_path = os.path.join(base, *normalised_parts)
        if os.path.exists(candidate_path):
            return base, candidate_path, True

    fallback_base = candidates[0] if candidates else None
    fallback_path = (
        os.path.join(fallback_base, *normalised_parts) if fallback_base else None
    )
    return fallback_base, fallback_path, False


def ensure_directory(path: str | Path) -> Path:
    """Ensure that *path* exists as a directory and return it as ``Path``."""

    directory = Path(path)
    directory.mkdir(parents=True, exist_ok=True)
    return directory
