"""メディアエンティティの生成を担当するファクトリ."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict

from ..local_import.media_file import MediaFileAnalyzer
from .media import Media


@dataclass(slots=True)
class MediaFactory:
    """生ファイルからドメインエンティティを生成する."""

    analyzer: MediaFileAnalyzer = field(default_factory=MediaFileAnalyzer)

    def create_from_path(self, file_path: str, *, origin: str, extras: Dict[str, Any] | None = None) -> Media:
        analysis = self.analyzer.analyze(file_path)
        return Media(analysis=analysis, origin=origin, extras=extras or {})


__all__ = ["MediaFactory"]
