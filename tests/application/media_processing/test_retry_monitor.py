from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, List

from application.media_processing.interfaces import ThumbnailRetryEntry, ThumbnailRetryRepository
from application.media_processing.retry_monitor import ThumbnailRetryMonitorService


@dataclass
class StubLogger:
    calls: list

    def info(self, **kwargs):
        self.calls.append(("info", kwargs))

    def warning(self, **kwargs):
        self.calls.append(("warning", kwargs))

    def error(self, **kwargs):  # pragma: no cover - unused
        self.calls.append(("error", kwargs))


class FakeThumbnailService:
    def __init__(self, results: Iterable[dict]) -> None:
        self._results = list(results)
        self.calls: List[dict] = []

    def generate(self, **kwargs):
        self.calls.append(kwargs)
        return self._results.pop(0)


class FakeRepository(ThumbnailRetryRepository):
    def __init__(self, *, pending: List[ThumbnailRetryEntry], disabled: List[ThumbnailRetryEntry]):
        self._pending = list(pending)
        self._disabled = list(disabled)
        self.running: List[int] = []
        self.canceled: List[int] = []
        self.finished: List[tuple] = []
        self.reported: List[int] = []

    def get_or_create(self, media_id: int):  # pragma: no cover - not used
        raise NotImplementedError

    def persist_scheduled(self, *args, **kwargs):  # pragma: no cover - not used
        raise NotImplementedError

    def mark_exhausted(self, *args, **kwargs):  # pragma: no cover - not used
        raise NotImplementedError

    def clear_success(self, media_id: int):  # pragma: no cover - not used
        raise NotImplementedError

    def iter_due(self, limit: int):
        return list(self._pending)[:limit]

    def mark_running(self, entry, *, started_at):
        self.running.append(entry.id)

    def mark_canceled(self, entry, *, finished_at):
        self.canceled.append(entry.id)

    def mark_finished(self, entry, *, finished_at, success):
        self.finished.append((entry.id, success))

    def find_disabled(self, limit: int):
        return list(self._disabled)[:limit]

    def mark_monitor_reported(self, entries):
        for entry in entries:
            self.reported.append(entry.id)


def test_process_due_handles_successful_retry():
    entry = ThumbnailRetryEntry(id=1, media_id=5, attempts=0, payload={"force": False})
    repository = FakeRepository(pending=[entry], disabled=[])
    service = FakeThumbnailService(results=[{"ok": True}])
    logger = StubLogger(calls=[])
    monitor = ThumbnailRetryMonitorService(repository=repository, thumbnail_service=service, logger=logger)

    result = monitor.process_due(limit=10)

    assert result == {"processed": 1, "rescheduled": 0, "cleared": 1, "pending_before": 1}
    assert repository.running == [1]
    assert repository.canceled == []
    assert service.calls[0]["media_id"] == 5
    assert any(call[0] == "info" for call in logger.calls)


def test_process_due_handles_reschedule():
    entry = ThumbnailRetryEntry(id=2, media_id=7, attempts=1, payload={"force": True})
    repository = FakeRepository(pending=[entry], disabled=[])
    service = FakeThumbnailService(results=[{"retry_scheduled": True}])
    logger = StubLogger(calls=[])
    monitor = ThumbnailRetryMonitorService(repository=repository, thumbnail_service=service, logger=logger)

    result = monitor.process_due(limit=5)

    assert result["rescheduled"] == 1


def test_process_due_logs_when_idle():
    disabled_entry = ThumbnailRetryEntry(
        id=3,
        media_id=9,
        attempts=5,
        payload={"retry_disabled": True},
    )
    repository = FakeRepository(pending=[], disabled=[disabled_entry])
    service = FakeThumbnailService(results=[])
    logger = StubLogger(calls=[])
    monitor = ThumbnailRetryMonitorService(repository=repository, thumbnail_service=service, logger=logger)

    result = monitor.process_due(limit=2)

    assert result == {"processed": 0, "rescheduled": 0, "cleared": 0, "pending_before": 0}
    assert repository.reported == [3]
    assert any(call[0] == "warning" for call in logger.calls)
