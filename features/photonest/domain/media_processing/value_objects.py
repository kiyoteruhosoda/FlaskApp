"""メディア後処理ドメインの値オブジェクト."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class RetryBlockers:
    """サムネイル再試行を阻害する要因を表す不変値オブジェクト."""

    details: Dict[str, Any]

    @classmethod
    def from_raw(cls, raw: Any) -> Optional["RetryBlockers"]:
        """辞書形式の入力から :class:`RetryBlockers` を生成する."""

        if not isinstance(raw, dict):
            return None
        return cls(details=dict(raw))

    @property
    def reason(self) -> Optional[str]:
        """再試行が止まっている理由 (存在しない場合は ``None``)."""

        raw = self.details.get("reason")
        if raw is None:
            return None
        return str(raw)
