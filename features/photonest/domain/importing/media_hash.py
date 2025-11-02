"""インポートドメインで利用するハッシュ値の値オブジェクト."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MediaHash:
    """メディアの一意性を表現する値オブジェクト."""

    value: str

    def __post_init__(self) -> None:
        if not self.value:
            raise ValueError("ハッシュ値が空です")

    def equals(self, other: "MediaHash" | str) -> bool:
        if isinstance(other, MediaHash):
            return self.value == other.value
        return self.value == other

    def __str__(self) -> str:  # pragma: no cover - dataclass repr 互換用
        return self.value


__all__ = ["MediaHash"]
