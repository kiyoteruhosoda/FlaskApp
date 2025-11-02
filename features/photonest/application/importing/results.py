"""インポート処理の結果 DTO."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ImportResult:
    """インポート処理の出力 DTO."""

    imported_count: int = 0
    skipped_count: int = 0
    duplicates_count: int = 0
    errors: List[str] = field(default_factory=list)
    session_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_error(self, message: str) -> None:
        self.errors.append(message)

    def mark_duplicate(self) -> None:
        self.duplicates_count += 1

    def mark_imported(self) -> None:
        self.imported_count += 1

    def mark_skipped(self) -> None:
        self.skipped_count += 1

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "imported_count": self.imported_count,
            "skipped_count": self.skipped_count,
            "duplicates_count": self.duplicates_count,
            "errors": list(self.errors),
            "session_id": self.session_id,
        }
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        return payload


__all__ = ["ImportResult"]
