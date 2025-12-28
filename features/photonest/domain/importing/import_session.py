"""インポートセッションエンティティ."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional


@dataclass(slots=True)
class ImportSession:
    """インポート処理の状態を管理するエンティティ."""

    session_id: str
    source: str
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    status: str = "pending"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def mark_running(self) -> None:
        self.status = "running"
        self.metadata["started_at"] = self.started_at.isoformat()

    def mark_completed(self) -> None:
        self.status = "completed"
        self.metadata["completed_at"] = datetime.now(timezone.utc).isoformat()

    def mark_failed(self, message: str) -> None:
        self.status = "failed"
        self.metadata.setdefault("errors", []).append(message)

    def to_dict(self) -> Dict[str, Any]:
        payload = dict(self.metadata)
        payload.update({
            "session_id": self.session_id,
            "source": self.source,
            "status": self.status,
        })
        return payload


__all__ = ["ImportSession"]
