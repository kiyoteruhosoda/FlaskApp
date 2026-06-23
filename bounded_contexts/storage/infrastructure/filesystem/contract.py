"""ストレージアクセスの契約（値オブジェクトと抽象インターフェース）.

DIP に従い、抽象（Protocol）と値オブジェクトを具象実装から分離する。各バック
エンド実装（local / backends）は本モジュールにのみ依存し、相互には依存しない。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import (
    IO,
    Any,
    Iterator,
    Protocol,
    Sequence,
    runtime_checkable,
)

from bounded_contexts.storage.domain import (
    StorageDomain,
    StorageIntent,
)

PathPart = str | os.PathLike[str] | bytes
StorageSelector = StorageDomain | str


@dataclass(frozen=True)
class ResolvedPath:
    """``StorageArea.resolve`` の結果（解決済みパス情報）.

    ``StorageResolution`` 列挙（サムネイルサイズ）とは別物。base/絶対パスと
    実在有無を保持する。
    """

    base_path: str | None
    absolute_path: str | None
    exists: bool


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
    ) -> ResolvedPath:
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
    ) -> ResolvedPath:
        ...

    def set_defaults(self, config_key: str, defaults: Sequence[str]) -> None:
        ...

    def defaults(self, config_key: str) -> tuple[str, ...]:
        ...
