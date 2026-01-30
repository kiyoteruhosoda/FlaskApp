"""ローカルファイルアクセス用のリポジトリアダプタ."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List

from ...domain.local_import.policies import SUPPORTED_EXTENSIONS


@dataclass(slots=True)
class LocalFileRepository:
    """ローカルディスクから取り込み対象を列挙する."""

    supported_extensions: Iterable[str] = field(
        default_factory=lambda: set(SUPPORTED_EXTENSIONS)
    )

    def list_media(self, directory: str) -> List[str]:
        base = Path(directory)
        if not base.exists():
            return []
        files: List[str] = []
        for entry in base.rglob("*"):
            if not entry.is_file():
                continue
            if entry.suffix.lower() not in self.supported_extensions:
                continue
            files.append(str(entry.resolve()))
        return sorted(files)


__all__ = ["LocalFileRepository"]
