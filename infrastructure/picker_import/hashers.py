from __future__ import annotations

from pathlib import Path
from typing import Optional

from features.photonest.domain.local_import.media_metadata import (
    calculate_perceptual_hash,
)


class LocalPerceptualHashCalculator:
    """ローカルファイルから pHash を計算するアダプタ。"""

    def calculate(
        self,
        *,
        file_path: Path,
        is_video: bool,
        duration_ms: Optional[int],
    ) -> Optional[str]:
        return calculate_perceptual_hash(
            str(file_path),
            is_video=is_video,
            duration_ms=duration_ms,
        )


__all__ = ["LocalPerceptualHashCalculator"]
