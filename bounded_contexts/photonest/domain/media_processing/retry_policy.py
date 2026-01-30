"""サムネイル再試行に関するドメインポリシー."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ThumbnailRetryDecision:
    """再試行の可否を表す値オブジェクト."""

    can_retry: bool
    attempt_number: int
    reason: Optional[str] = None
    keep_record: bool = False


class ThumbnailRetryPolicy:
    """サムネイル生成の再試行回数を管理するドメインポリシー."""

    def __init__(self, max_attempts: int) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        self._max_attempts = max_attempts

    @property
    def max_attempts(self) -> int:
        return self._max_attempts

    def decide(self, attempts_so_far: int) -> ThumbnailRetryDecision:
        """現在の試行回数から次回のアクションを決定する."""

        if attempts_so_far < 0:
            raise ValueError("attempts_so_far must be >= 0")

        if attempts_so_far >= self._max_attempts:
            return ThumbnailRetryDecision(
                can_retry=False,
                attempt_number=attempts_so_far,
                reason="max_attempts",
                keep_record=True,
            )

        return ThumbnailRetryDecision(
            can_retry=True,
            attempt_number=attempts_so_far + 1,
        )
