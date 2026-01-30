"""メディア後処理アプリケーション層の抽象インターフェース."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Iterable, Optional, Protocol


@dataclass(frozen=True)
class ThumbnailRetryEntry:
    """再試行レコードのスナップショット."""

    id: int
    media_id: Optional[int]
    attempts: int
    payload: Dict[str, object]

    def with_attempts(self, attempts: int) -> "ThumbnailRetryEntry":
        return ThumbnailRetryEntry(
            id=self.id,
            media_id=self.media_id,
            attempts=attempts,
            payload=dict(self.payload),
        )


class ThumbnailRetryRepository(Protocol):
    """再試行レコードの永続化を担当するリポジトリ."""

    def get_or_create(self, media_id: int) -> ThumbnailRetryEntry:
        ...

    def persist_scheduled(
        self,
        entry: ThumbnailRetryEntry,
        *,
        countdown_seconds: int,
        force: bool,
        celery_task_id: Optional[str],
        attempt: int,
        blockers: Optional[Dict[str, object]] = None,
    ) -> None:
        ...

    def mark_exhausted(
        self,
        entry: ThumbnailRetryEntry,
        *,
        force: bool,
        blockers: Optional[Dict[str, object]] = None,
    ) -> None:
        ...

    def clear_success(self, media_id: int) -> None:
        ...

    def iter_due(self, limit: int) -> Iterable[ThumbnailRetryEntry]:
        ...

    def mark_running(self, entry: ThumbnailRetryEntry, *, started_at: datetime) -> None:
        ...

    def mark_canceled(self, entry: ThumbnailRetryEntry, *, finished_at: datetime) -> None:
        ...

    def mark_finished(
        self,
        entry: ThumbnailRetryEntry,
        *,
        finished_at: datetime,
        success: bool,
    ) -> None:
        ...

    def find_disabled(self, limit: int) -> Iterable[ThumbnailRetryEntry]:
        ...

    def mark_monitor_reported(self, entries: Iterable[ThumbnailRetryEntry]) -> None:
        ...


class ThumbnailRetryScheduler(Protocol):
    """再試行ジョブを外部キューに投入するスケジューラ."""

    def schedule(
        self,
        *,
        media_id: int,
        force: bool,
        countdown_seconds: int,
    ) -> Optional[str]:
        ...
