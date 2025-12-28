from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

import pytest

from features.photonest.application.media_processing.retry_service import RetryScheduleResult
from features.photonest.application.media_processing.thumbnail_service import ThumbnailGenerationService


@dataclass
class StubLogger:
    calls: list

    def info(self, **kwargs):
        self.calls.append(("info", kwargs))

    def warning(self, **kwargs):
        self.calls.append(("warning", kwargs))

    def error(self, **kwargs):  # pragma: no cover - not triggered in tests
        self.calls.append(("error", kwargs))


class StubRetryService:
    def __init__(self, result: Optional[RetryScheduleResult] = None) -> None:
        self.result = result
        self.calls = []
        self.cleared = []

    def schedule_if_allowed(self, **kwargs):
        self.calls.append(kwargs)
        return self.result

    def clear_success(self, media_id: int) -> None:
        self.cleared.append(media_id)


@pytest.fixture
def logger():
    return StubLogger(calls=[])


def test_generate_schedules_retry(logger):
    retry_result = RetryScheduleResult(
        scheduled=True,
        countdown=120,
        celery_task_id="celery-1",
        attempts=2,
        max_attempts=5,
        keep_record=False,
        blockers={"reason": "pending"},
    )
    retry_service = StubRetryService(result=retry_result)

    def generator(**kwargs):
        return {
            "ok": True,
            "generated": [],
            "skipped": [256],
            "notes": "not-ready",
            "retry_blockers": {"reason": "pending"},
        }

    service = ThumbnailGenerationService(
        generator=generator,
        retry_service=retry_service,
        logger=logger,
        playback_not_ready_note="not-ready",
    )

    result = service.generate(media_id=101, force=True, operation_id="op", request_context={"x": 1})

    assert result["retry_scheduled"] is True
    assert result["retry_details"]["celery_task_id"] == "celery-1"
    assert retry_service.calls[0]["media_id"] == 101
    assert 101 not in retry_service.cleared
    assert any(call[0] == "info" for call in logger.calls)


def test_generate_clears_retry_when_not_scheduled(logger):
    retry_service = StubRetryService(result=None)

    def generator(**kwargs):
        return {
            "ok": True,
            "generated": [256],
            "skipped": [],
            "notes": "done",
        }

    service = ThumbnailGenerationService(
        generator=generator,
        retry_service=retry_service,
        logger=logger,
        playback_not_ready_note="not-ready",
    )

    result = service.generate(media_id=202, operation_id="op2", request_context=None)

    assert result["ok"] is True
    assert retry_service.cleared == [202]
    assert retry_service.calls == []


def test_generate_logs_failure(logger):
    retry_service = StubRetryService(result=None)

    def generator(**kwargs):
        return {"ok": False, "notes": "failure"}

    service = ThumbnailGenerationService(
        generator=generator,
        retry_service=retry_service,
        logger=logger,
        playback_not_ready_note="not-ready",
    )

    result = service.generate(media_id=303, operation_id="op3", request_context=None)

    assert result == {"ok": False, "notes": "failure"}
    assert retry_service.cleared == [303]
    assert any(call[0] == "warning" for call in logger.calls)
