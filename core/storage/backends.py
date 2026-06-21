"""未実装ストレージバックエンドのプレースホルダー実装.

Azure Blob / 外部 REST バックエンドは未提供のため、呼び出し時に明示的な
``NotImplementedError`` を送出して契約違反を早期に顕在化させる。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import (
    IO,
    Any,
    Callable,
    Iterator,
    NoReturn,
    Sequence,
)

from bounded_contexts.storage.domain import (
    StorageBackendType,
    StorageDomain,
    StorageIntent,
)

from .contract import PathPart, ResolvedPath, StorageArea, StorageSelector


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
    ) -> ResolvedPath:  # noqa: D401,ARG002
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
