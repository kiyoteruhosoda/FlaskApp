"""Picker Queue Service - Application layer.

enqueued状態のSelectionをバックグラウンド処理キューへ転送します。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Protocol, TypeAlias

from core.models.photo_models import PickerSelection
from infrastructure.picker_import.repositories import PickerSelectionRepository


# キュー投入関数の型エイリアス
EnqueueFunc: TypeAlias = Callable[[int, int], None]


class SelectionEnqueuer(Protocol):
    """Selection をキューに投入する契約."""

    def __call__(self, selection_id: int, session_id: int) -> None:
        ...


@dataclass(slots=True)
class PickerQueueService:
    """enqueued状態のSelectionをバックグラウンド処理キューへ転送する。"""

    repository: PickerSelectionRepository
    enqueue_func: EnqueueFunc

    def publish_enqueued(self) -> dict[str, int]:
        """enqueued 状態の Selection をキューへ投入."""
        now = datetime.now(timezone.utc)
        queued = 0

        selections: list[PickerSelection] = self.repository.list_enqueued()
        for selection in selections:
            selection.enqueued_at = selection.enqueued_at or now
            self.enqueue_func(selection.id, selection.session_id)
            queued += 1

        if queued:
            self.repository.commit()

        return {"queued": queued}


__all__ = ["EnqueueFunc", "PickerQueueService", "SelectionEnqueuer"]
