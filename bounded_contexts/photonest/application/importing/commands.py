"""インポートユースケースの入力コマンド."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional


@dataclass(frozen=True)
class ImportCommand:
    """インポート処理の入力 DTO."""

    source: str
    account_id: Optional[str] = None
    directory_path: Optional[str] = None
    options: Mapping[str, Any] = field(default_factory=dict)

    def option(self, key: str, default: Any = None) -> Any:
        return self.options.get(key, default)


__all__ = ["ImportCommand"]
