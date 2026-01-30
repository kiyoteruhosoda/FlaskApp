"""Perceptual Hash Calculator - Infrastructure layer.

ローカルファイルから知覚ハッシュを計算するアダプタを提供します。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from bounded_contexts.photonest.domain.local_import.media_metadata import (
    calculate_perceptual_hash,
)


@dataclass(frozen=True, slots=True)
class LocalPerceptualHashCalculator:
    """ローカルファイルから pHash を計算するアダプタ。

    Note:
        Protocol (PerceptualHashCalculator) の構造的部分型付けに準拠。
        明示的な継承は不要です。
    """

    def calculate(
        self,
        *,
        file_path: Path,
        is_video: bool,
        duration_ms: int | None,
    ) -> str | None:
        """知覚ハッシュを計算して返す."""
        return calculate_perceptual_hash(
            str(file_path),
            is_video=is_video,
            duration_ms=duration_ms,
        )


__all__ = ["LocalPerceptualHashCalculator"]
