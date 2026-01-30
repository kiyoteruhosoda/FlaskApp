from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Optional

import pytest

from bounded_contexts.photonest.application.media_processing.interfaces import ThumbnailRetryEntry, ThumbnailRetryRepository, ThumbnailRetryScheduler
from bounded_contexts.photonest.application.media_processing.retry_service import RetryScheduleResult, ThumbnailRetryService
from bounded_contexts.photonest.domain.media_processing import ThumbnailRetryPolicy


@dataclass
class StubLogger:
    calls: list

    def info(self, **kwargs):
        self.calls.append(("info", kwargs))

    def warning(self, **kwargs):
        self.calls.append(("warning", kwargs))

    def error(self, **kwargs):
        self.calls.append(("error", kwargs))


class FakeRepository(ThumbnailRetryRepository):
    def __init__(self, *, attempts: int = 0) -> None:
        self._entry = ThumbnailRetryEntry(id=1, media_id=123, attempts=attempts, payload={})
        self.persisted: Optional[Dict[str, object]] = None
        self.exhausted: Optional[Dict[str, object]] = None
        self.cleared_media: Optional[int] = None

    def get_or_create(self, media_id: int) -> ThumbnailRetryEntry:
        return self._entry

    def persist_scheduled(self, entry, *, countdown_seconds, force, celery_task_id, attempt, blockers=None):
        self.persisted = {
            "entry": entry,
            "countdown": countdown_seconds,
            "force": force,
            "celery_task_id": celery_task_id,
            "attempt": attempt,
            "blockers": blockers,
        }
        self._entry = self._entry.with_attempts(attempt)

    def mark_exhausted(self, entry, *, force, blockers=None):
        self.exhausted = {"entry": entry, "force": force, "blockers": blockers}

    def clear_success(self, media_id: int) -> None:
        self.cleared_media = media_id

    def iter_due(self, limit: int) -> Iterable[ThumbnailRetryEntry]:  # pragma: no cover - not used here
        return []

    def mark_running(self, entry, *, started_at):  # pragma: no cover - not used here
        raise NotImplementedError

    def mark_canceled(self, entry, *, finished_at):  # pragma: no cover - not used here
        raise NotImplementedError

    def mark_finished(self, entry, *, finished_at, success):  # pragma: no cover - not used here
        raise NotImplementedError

    def find_disabled(self, limit: int):  # pragma: no cover - not used here
        return []

    def mark_monitor_reported(self, entries):  # pragma: no cover - not used here
        raise NotImplementedError


class FakeScheduler(ThumbnailRetryScheduler):
    def __init__(self, *, celery_task_id: Optional[str] = "task-id", raise_error: bool = False) -> None:
        self.celery_task_id = celery_task_id
        self.raise_error = raise_error
        self.calls = []

    def schedule(self, *, media_id: int, force: bool, countdown_seconds: int) -> Optional[str]:
        if self.raise_error:
            raise RuntimeError("scheduler failure")
        self.calls.append({"media_id": media_id, "force": force, "countdown": countdown_seconds})
        return self.celery_task_id


@pytest.fixture
def policy() -> ThumbnailRetryPolicy:
    return ThumbnailRetryPolicy(max_attempts=3)


def test_schedule_retry_success(policy):
    logger = StubLogger(calls=[])
    repository = FakeRepository(attempts=0)
    scheduler = FakeScheduler()
    service = ThumbnailRetryService(
        policy=policy,
        repository=repository,
        scheduler=scheduler,
        logger=logger,
        countdown_seconds=60,
    )

    result = service.schedule_if_allowed(
        media_id=123,
        force=True,
        operation_id="op-1",
        request_context={"source": "test"},
        blockers={"reason": "pending"},
    )

    assert isinstance(result, RetryScheduleResult)
    assert result.scheduled is True
    assert result.countdown == 60
    assert result.celery_task_id == "task-id"
    assert result.attempts == 1
    assert repository.persisted["attempt"] == 1
    assert repository.persisted["force"] is True
    assert repository.persisted["blockers"] == {"reason": "pending"}
    assert scheduler.calls[0]["media_id"] == 123
    assert any(call[0] == "info" for call in logger.calls)


def test_schedule_retry_exhausted(policy):
    logger = StubLogger(calls=[])
    repository = FakeRepository(attempts=3)
    scheduler = FakeScheduler()
    service = ThumbnailRetryService(
        policy=policy,
        repository=repository,
        scheduler=scheduler,
        logger=logger,
        countdown_seconds=60,
    )

    result = service.schedule_if_allowed(
        media_id=123,
        force=False,
        operation_id="op-2",
        request_context=None,
        blockers=None,
    )

    assert isinstance(result, RetryScheduleResult)
    assert result.scheduled is False
    assert result.keep_record is True
    assert repository.exhausted["force"] is False
    assert scheduler.calls == []
    assert any(call[0] == "warning" for call in logger.calls)


def test_schedule_retry_handles_scheduler_errors(policy):
    logger = StubLogger(calls=[])
    repository = FakeRepository(attempts=0)
    scheduler = FakeScheduler(raise_error=True)
    service = ThumbnailRetryService(
        policy=policy,
        repository=repository,
        scheduler=scheduler,
        logger=logger,
        countdown_seconds=60,
    )

    result = service.schedule_if_allowed(
        media_id=999,
        force=False,
        operation_id="op-3",
        request_context=None,
        blockers=None,
    )

    assert result is None
    assert repository.persisted is None
    assert any(call[0] == "warning" for call in logger.calls)
