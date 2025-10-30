"""ストレージアクセスを統制するサービス実装."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import (
    IO,
    Any,
    Callable,
    Iterable,
    Iterator,
    NoReturn,
    Optional,
    Protocol,
    Sequence,
    runtime_checkable,
)

from domain.storage import (
    StorageBackendType,
    StorageDomain,
    StorageIntent,
    StorageResolution,
)

PathPart = str | os.PathLike[str] | bytes
StorageSelector = StorageDomain | str


@dataclass(frozen=True)
class _StorageSpec:
    domain: StorageDomain
    config_key: str
    env_fallbacks: tuple[str, ...]
    defaults: tuple[str, ...]


@runtime_checkable
class StorageArea(Protocol):
    """特定ドメインのストレージ操作を提供するハンドル."""

    domain: StorageDomain
    config_key: str

    def candidates(self, *, intent: StorageIntent = StorageIntent.READ) -> list[str]:
        ...

    def first_existing(self, *, intent: StorageIntent = StorageIntent.READ) -> str | None:
        ...

    def resolve(
        self,
        *path_parts: PathPart,
        intent: StorageIntent = StorageIntent.READ,
    ) -> StorageResolution:
        ...

    def ensure_base(self) -> str | None:
        ...


@runtime_checkable
class StorageService(Protocol):
    """ストレージ操作抽象."""

    def exists(self, path: str) -> bool:
        ...

    def size(self, path: str) -> int:
        ...

    def join(self, base: str, *parts: str) -> str:
        ...

    def normalize_path(self, relative_path: str) -> str:
        ...

    def ensure_parent(self, path: str) -> None:
        ...

    def ensure_directory(self, path: str | os.PathLike[str]) -> Path:
        ...

    def copy(self, source: str, destination: str) -> None:
        ...

    def remove(self, path: str) -> None:
        ...

    def remove_tree(self, path: str) -> None:
        ...

    def open(self, path: str, mode: str = "rb", **kwargs: Any) -> IO[Any]:
        ...

    def walk(self, top: str) -> Iterator[tuple[str, list[str], list[str]]]:
        ...

    def for_domain(self, domain: StorageDomain) -> StorageArea:
        ...

    def for_key(self, config_key: str) -> StorageArea:
        ...

    def candidates(
        self,
        selector: StorageSelector,
        *,
        intent: StorageIntent = StorageIntent.READ,
    ) -> list[str]:
        ...

    def first_existing(
        self,
        selector: StorageSelector,
        *,
        intent: StorageIntent = StorageIntent.READ,
    ) -> str | None:
        ...

    def resolve_path(
        self,
        selector: StorageSelector,
        *path_parts: PathPart,
        intent: StorageIntent = StorageIntent.READ,
    ) -> StorageResolution:
        ...

    def set_defaults(self, config_key: str, defaults: Sequence[str]) -> None:
        ...

    def defaults(self, config_key: str) -> tuple[str, ...]:
        ...


class _UnimplementedStorageService:
    """未実装バックエンドのプレースホルダー."""

    def __init__(
        self,
        *,
        backend: StorageBackendType,
        config_resolver: Callable[[str], str | None] | None = None,
        env_resolver: Callable[[str], str | None] | None = None,
    ) -> None:
        self._backend = backend
        self._config_resolver = config_resolver
        self._env_resolver = env_resolver

    # ------------------------------------------------------------------
    # StorageService interface - low level operations
    # ------------------------------------------------------------------
    def exists(self, path: str) -> bool:  # noqa: D401,ARG002
        self._raise()

    def size(self, path: str) -> int:  # noqa: D401,ARG002
        self._raise()

    def join(self, base: str, *parts: str) -> str:  # noqa: D401,ARG002
        self._raise()

    def normalize_path(self, relative_path: str) -> str:  # noqa: D401,ARG002
        self._raise()

    def ensure_parent(self, path: str) -> None:  # noqa: D401,ARG002
        self._raise()

    def ensure_directory(self, path: str | os.PathLike[str]) -> Path:  # noqa: D401,ARG002
        self._raise()

    def copy(self, source: str, destination: str) -> None:  # noqa: D401,ARG002
        self._raise()

    def remove(self, path: str) -> None:  # noqa: D401,ARG002
        self._raise()

    def remove_tree(self, path: str) -> None:  # noqa: D401,ARG002
        self._raise()

    def open(self, path: str, mode: str = "rb", **kwargs: Any) -> IO[Any]:  # noqa: D401,ARG002
        self._raise()

    def walk(self, top: str) -> Iterator[tuple[str, list[str], list[str]]]:  # noqa: D401,ARG002
        self._raise()

    # ------------------------------------------------------------------
    # StorageService interface - domain operations
    # ------------------------------------------------------------------
    def for_domain(self, domain: StorageDomain) -> StorageArea:  # noqa: D401,ARG002
        self._raise()

    def for_key(self, config_key: str) -> StorageArea:  # noqa: D401,ARG002
        self._raise()

    def candidates(
        self,
        selector: StorageSelector,
        *,
        intent: StorageIntent = StorageIntent.READ,
    ) -> list[str]:  # noqa: D401,ARG002
        self._raise()

    def first_existing(
        self,
        selector: StorageSelector,
        *,
        intent: StorageIntent = StorageIntent.READ,
    ) -> str | None:  # noqa: D401,ARG002
        self._raise()

    def resolve_path(
        self,
        selector: StorageSelector,
        *path_parts: PathPart,
        intent: StorageIntent = StorageIntent.READ,
    ) -> StorageResolution:  # noqa: D401,ARG002
        self._raise()

    def set_defaults(self, config_key: str, defaults: Sequence[str]) -> None:  # noqa: D401,ARG002
        self._raise()

    def defaults(self, config_key: str) -> tuple[str, ...]:  # noqa: D401,ARG002
        self._raise()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _raise(self) -> NoReturn:
        raise NotImplementedError(
            "Storage backend '%s' is not implemented yet" % self._backend.value
        )


class AzureBlobStorageService(_UnimplementedStorageService):
    """Azure Blob Storage バックエンドの未実装プレースホルダー."""

    def __init__(
        self,
        *,
        config_resolver: Callable[[str], str | None] | None = None,
        env_resolver: Callable[[str], str | None] | None = None,
    ) -> None:
        super().__init__(
            backend=StorageBackendType.AZURE_BLOB,
            config_resolver=config_resolver,
            env_resolver=env_resolver,
        )


class ExternalRestStorageService(_UnimplementedStorageService):
    """外部 REST ストレージバックエンドの未実装プレースホルダー."""

    def __init__(
        self,
        *,
        config_resolver: Callable[[str], str | None] | None = None,
        env_resolver: Callable[[str], str | None] | None = None,
    ) -> None:
        super().__init__(
            backend=StorageBackendType.EXTERNAL_REST,
            config_resolver=config_resolver,
            env_resolver=env_resolver,
        )


_KNOWN_SPECS: tuple[_StorageSpec, ...] = (
    _StorageSpec(
        domain=StorageDomain.MEDIA_ORIGINALS,
        config_key="MEDIA_ORIGINALS_DIRECTORY",
        env_fallbacks=(
            "MEDIA_ORIGINALS_CONTAINER_DIRECTORY",
            "MEDIA_ORIGINALS_DIRECTORY",
            "FPV_NAS_ORIGINALS_CONTAINER_DIR",
            "FPV_NAS_ORIGINALS_DIR",
        ),
        defaults=("/app/data/media", "/tmp/fpv_orig"),
    ),
    _StorageSpec(
        domain=StorageDomain.MEDIA_PLAYBACK,
        config_key="MEDIA_PLAYBACK_DIRECTORY",
        env_fallbacks=(
            "MEDIA_PLAYBACK_CONTAINER_DIRECTORY",
            "MEDIA_PLAYBACK_DIRECTORY",
            "FPV_NAS_PLAY_CONTAINER_DIR",
            "FPV_NAS_PLAY_DIR",
        ),
        defaults=("/app/data/playback", "/tmp/fpv_play"),
    ),
    _StorageSpec(
        domain=StorageDomain.MEDIA_THUMBNAILS,
        config_key="MEDIA_THUMBNAILS_DIRECTORY",
        env_fallbacks=(
            "MEDIA_THUMBNAILS_CONTAINER_DIRECTORY",
            "MEDIA_THUMBNAILS_DIRECTORY",
            "FPV_NAS_THUMBS_CONTAINER_DIR",
            "FPV_NAS_THUMBS_DIR",
        ),
        defaults=("/app/data/thumbs", "/tmp/fpv_thumbs"),
    ),
    _StorageSpec(
        domain=StorageDomain.MEDIA_IMPORT,
        config_key="MEDIA_LOCAL_IMPORT_DIRECTORY",
        env_fallbacks=(
            "MEDIA_LOCAL_IMPORT_CONTAINER_DIRECTORY",
            "MEDIA_LOCAL_IMPORT_DIRECTORY",
            "LOCAL_IMPORT_CONTAINER_DIR",
            "LOCAL_IMPORT_DIR",
        ),
        defaults=("/tmp/local_import",),
    ),
)


class _LocalStorageArea(StorageArea):
    def __init__(self, service: "LocalFilesystemStorageService", spec: _StorageSpec) -> None:
        self._service = service
        self._spec = spec

    @property
    def domain(self) -> StorageDomain:
        return self._spec.domain

    @property
    def config_key(self) -> str:
        return self._spec.config_key

    def candidates(self, *, intent: StorageIntent = StorageIntent.READ) -> list[str]:  # noqa: ARG002
        return self._service._candidates(self._spec)

    def first_existing(self, *, intent: StorageIntent = StorageIntent.READ) -> str | None:  # noqa: ARG002
        candidates = self.candidates(intent=intent)
        for candidate in candidates:
            if self._service.exists(candidate):
                return candidate
        return candidates[0] if candidates else None

    def resolve(
        self,
        *path_parts: PathPart,
        intent: StorageIntent = StorageIntent.READ,  # noqa: ARG002
    ) -> StorageResolution:
        candidates = self.candidates(intent=intent)
        normalised = self._service._normalise_parts(path_parts)
        if normalised is None:
            return StorageResolution(None, None, False)

        if not normalised:
            for candidate in candidates:
                if self._service.exists(candidate):
                    return StorageResolution(candidate, candidate, True)
            fallback = candidates[0] if candidates else None
            return StorageResolution(fallback, fallback, False)

        for base in candidates:
            candidate_path = self._service.join(base, *normalised)
            if self._service.exists(candidate_path):
                return StorageResolution(base, candidate_path, True)

        fallback_base = candidates[0] if candidates else None
        fallback_path = (
            self._service.join(fallback_base, *normalised) if fallback_base else None
        )
        return StorageResolution(fallback_base, fallback_path, False)

    def ensure_base(self) -> str | None:
        candidates = self.candidates(intent=StorageIntent.WRITE)
        if not candidates:
            return None
        target = candidates[0]
        self._service.ensure_directory(target)
        return target


class LocalFilesystemStorageService:
    """ローカルファイルシステム上での ``StorageService`` 実装."""

    def __init__(
        self,
        config_resolver: Callable[[str], str | None] | None = None,
        env_resolver: Callable[[str], str | None] | None = None,
    ) -> None:
        self._config_resolver = config_resolver
        self._env_resolver = env_resolver
        self._defaults: dict[str, tuple[str, ...]] = {
            spec.config_key: spec.defaults for spec in _KNOWN_SPECS
        }

    def spawn(self) -> "LocalFilesystemStorageService":
        clone = LocalFilesystemStorageService(
            config_resolver=self._config_resolver,
            env_resolver=self._env_resolver,
        )
        clone._defaults = dict(self._defaults)
        return clone

    # ------------------------------------------------------------------
    # StorageService interface - low level operations
    # ------------------------------------------------------------------
    def exists(self, path: str) -> bool:
        return os.path.exists(path)

    def size(self, path: str) -> int:
        return os.path.getsize(path)

    def join(self, base: str, *parts: str) -> str:
        clean_parts = [part for part in parts if part]
        return os.path.join(base, *clean_parts) if clean_parts else base

    def normalize_path(self, relative_path: str) -> str:
        normalized = os.path.normpath(relative_path)
        if normalized in {".", ""}:
            return ""
        return normalized.replace(os.sep, "/")

    def ensure_parent(self, path: str) -> None:
        parent = Path(path).parent
        if not parent:
            return
        parent.mkdir(parents=True, exist_ok=True)

    def ensure_directory(self, path: str | os.PathLike[str]) -> Path:
        directory = Path(path)
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def copy(self, source: str, destination: str) -> None:
        self.ensure_parent(destination)
        shutil.copy2(source, destination)

    def remove(self, path: str) -> None:
        os.remove(path)

    def remove_tree(self, path: str) -> None:
        shutil.rmtree(path)

    def open(self, path: str, mode: str = "rb", **kwargs: Any) -> IO[Any]:
        if any(flag in mode for flag in ("w", "a", "+")):
            self.ensure_parent(path)
        return open(path, mode, **kwargs)

    def walk(self, top: str) -> Iterator[tuple[str, list[str], list[str]]]:
        return os.walk(top)

    # ------------------------------------------------------------------
    # StorageService interface - domain operations
    # ------------------------------------------------------------------
    def for_domain(self, domain: StorageDomain) -> StorageArea:
        return _LocalStorageArea(self, self._spec_for_domain(domain))

    def for_key(self, config_key: str) -> StorageArea:
        return _LocalStorageArea(self, self._spec_for_key(config_key))

    def candidates(
        self,
        selector: StorageSelector,
        *,
        intent: StorageIntent = StorageIntent.READ,
    ) -> list[str]:  # noqa: ARG002
        return self._area(selector).candidates(intent=intent)

    def first_existing(
        self,
        selector: StorageSelector,
        *,
        intent: StorageIntent = StorageIntent.READ,
    ) -> str | None:  # noqa: ARG002
        return self._area(selector).first_existing(intent=intent)

    def resolve_path(
        self,
        selector: StorageSelector,
        *path_parts: PathPart,
        intent: StorageIntent = StorageIntent.READ,
    ) -> StorageResolution:  # noqa: ARG002
        return self._area(selector).resolve(*path_parts, intent=intent)

    def set_defaults(self, config_key: str, defaults: Sequence[str]) -> None:
        normalized = tuple(str(value) for value in defaults if value)
        if not normalized:
            return
        self._defaults[config_key] = normalized

    def defaults(self, config_key: str) -> tuple[str, ...]:
        spec = self._spec_for_key(config_key)
        return self._defaults.get(spec.config_key, spec.defaults)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _area(self, selector: StorageSelector) -> _LocalStorageArea:
        if isinstance(selector, StorageDomain):
            return self.for_domain(selector)  # type: ignore[return-value]
        return self.for_key(selector)  # type: ignore[return-value]

    def _spec_for_domain(self, domain: StorageDomain) -> _StorageSpec:
        for spec in _KNOWN_SPECS:
            if spec.domain is domain:
                return spec
        raise KeyError(f"Unsupported storage domain: {domain!s}")

    def _spec_for_key(self, config_key: str) -> _StorageSpec:
        for spec in _KNOWN_SPECS:
            if spec.config_key == config_key:
                return spec
        # 未知のキーはデフォルトを持たない汎用ストレージとして扱う
        return _StorageSpec(
            domain=StorageDomain.DEFAULT,
            config_key=config_key,
            env_fallbacks=(config_key,),
            defaults=self._defaults.get(config_key, tuple()),
        )

    def _candidates(self, spec: _StorageSpec) -> list[str]:
        seen: set[str] = set()
        candidates: list[str] = []

        config_value = self._get_config(spec.config_key)
        if config_value and config_value not in seen:
            candidates.append(config_value)
            seen.add(config_value)

        for env_key in spec.env_fallbacks or (spec.config_key,):
            env_value = self._get_env(env_key)
            if env_value and env_value not in seen:
                candidates.append(env_value)
                seen.add(env_value)

        defaults = self._defaults.get(spec.config_key, spec.defaults)
        for default_value in defaults:
            if default_value and default_value not in seen:
                candidates.append(default_value)
                seen.add(default_value)

        return [candidate for candidate in candidates if candidate]

    def _get_config(self, key: str) -> str | None:
        if self._config_resolver is None:
            return None
        value = self._config_resolver(key)
        return str(value) if value else None

    def _get_env(self, key: str) -> str | None:
        if self._env_resolver is not None:
            value = self._env_resolver(key)
        else:
            value = os.environ.get(key)
        return str(value) if value else None

    @staticmethod
    def _normalise_parts(path_parts: Iterable[PathPart]) -> Optional[tuple[str, ...]]:
        parts = tuple(path_parts)
        if not parts:
            return ()

        normalised: list[str] = []
        for part in parts:
            if part is None:
                return None
            try:
                part_str = os.fspath(part)
            except TypeError:
                return None
            if not part_str:
                return None
            normalised.append(part_str)

        return tuple(normalised)

