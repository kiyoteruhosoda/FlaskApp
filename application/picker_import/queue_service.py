from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Dict

from core.models.photo_models import PickerSelection
from infrastructure.picker_import.repositories import PickerSelectionRepository


EnqueueFunc = Callable[[int, int], None]


@dataclass
class PickerQueueService:
    """enqueued状態のSelectionをバックグラウンド処理キューへ転送する。"""

    repository: PickerSelectionRepository
    enqueue_func: EnqueueFunc

    def publish_enqueued(self) -> Dict[str, int]:
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
