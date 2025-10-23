"""ストレージアクセスを抽象化するサービス定義."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class StorageService(Protocol):
    """ファイルシステム／オブジェクトストレージを横断する抽象インターフェース."""

    def exists(self, path: str) -> bool:
        """指定パスが存在するかを返す."""

    def size(self, path: str) -> int:
        """指定パスのバイトサイズを返す."""

    def join(self, base: str, *parts: str) -> str:
        """ストレージ固有の区切りでパスを結合する."""

    def ensure_parent(self, path: str) -> None:
        """パスの親ディレクトリを作成する（必要であれば再帰的に）."""

    def copy(self, source: str, destination: str) -> None:
        """ソースからデスティネーションへ内容をコピーする."""

    def remove(self, path: str) -> None:
        """指定パスを削除する."""


class LocalFilesystemStorageService:
    """ローカルファイルシステム向けの ``StorageService`` 実装."""

    def exists(self, path: str) -> bool:
        return os.path.exists(path)

    def size(self, path: str) -> int:
        return os.path.getsize(path)

    def join(self, base: str, *parts: str) -> str:
        clean_parts = [part for part in parts if part]
        return os.path.join(base, *clean_parts) if clean_parts else base

    def ensure_parent(self, path: str) -> None:
        parent = Path(path).parent
        if not parent:
            return
        parent.mkdir(parents=True, exist_ok=True)

    def copy(self, source: str, destination: str) -> None:
        self.ensure_parent(destination)
        shutil.copy2(source, destination)

    def remove(self, path: str) -> None:
        os.remove(path)

