"""インポート対象となるメディアエンティティ定義."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from ..local_import.media_file import MediaFileAnalysis
from .media_hash import MediaHash


@dataclass(slots=True)
class Media:
    """解析済みメディアを表すドメインエンティティ."""

    analysis: MediaFileAnalysis
    origin: str
    extras: Dict[str, Any]

    def __post_init__(self) -> None:
        if not self.origin:
            raise ValueError("origin は必須です")

    @property
    def hash(self) -> MediaHash:
        return MediaHash(self.analysis.file_hash)

    @property
    def perceptual_hash(self) -> Optional[str]:
        return self.analysis.perceptual_hash

    @property
    def size_bytes(self) -> int:
        return self.analysis.file_size

    @property
    def relative_path(self) -> str:
        return self.analysis.relative_path

    @property
    def filename(self) -> str:
        return self.analysis.destination_filename


__all__ = ["Media"]
