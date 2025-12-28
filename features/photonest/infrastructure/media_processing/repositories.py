"""SQLAlchemy を利用したサムネイル再試行リポジトリ."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, Optional, Sequence

from features.photonest.application.media_processing.interfaces import ThumbnailRetryEntry, ThumbnailRetryRepository
from core.db import db
from core.models.celery_task import CeleryTaskRecord, CeleryTaskStatus

_THUMBNAIL_RETRY_TASK_NAME = "thumbnail.retry"


def _as_entry(record: CeleryTaskRecord) -> ThumbnailRetryEntry:
    payload = record.payload or {}
    attempts_raw = payload.get("attempts", 0)
    try:
        attempts = int(attempts_raw)
    except (TypeError, ValueError):
        attempts = 0
    return ThumbnailRetryEntry(
        id=record.id,
        media_id=record.object_id,
        attempts=attempts,
        payload=dict(payload),
    )


def _load_record(entry: ThumbnailRetryEntry) -> Optional[CeleryTaskRecord]:
    if entry.id:
        record = CeleryTaskRecord.query.get(entry.id)
        if record is not None:
            return record
    if entry.media_id is None:
        return None
    return (
        CeleryTaskRecord.query.filter_by(
            task_name=_THUMBNAIL_RETRY_TASK_NAME,
            object_type="media",
            object_id=str(entry.media_id),
        )
        .order_by(CeleryTaskRecord.id.desc())
        .first()
    )


class SqlAlchemyThumbnailRetryRepository(ThumbnailRetryRepository):
    """CeleryTaskRecord を利用した再試行リポジトリ."""

    def get_or_create(self, media_id: int) -> ThumbnailRetryEntry:
        record = CeleryTaskRecord.get_or_create(
            task_name=_THUMBNAIL_RETRY_TASK_NAME,
            object_identity=("media", str(media_id)),
        )
        db.session.flush()
        return _as_entry(record)

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
        record = _load_record(entry)
        if record is None:
            return
        record.status = CeleryTaskStatus.SCHEDULED
        record.scheduled_for = datetime.now(timezone.utc) + timedelta(seconds=countdown_seconds)
        record.started_at = None
        record.finished_at = None
        record.celery_task_id = celery_task_id
        payload: Dict[str, object] = {"force": force, "attempts": attempt}
        if blockers is not None:
            payload["blockers"] = blockers
        record.set_payload(payload)
        db.session.commit()

    def mark_exhausted(
        self,
        entry: ThumbnailRetryEntry,
        *,
        force: bool,
        blockers: Optional[Dict[str, object]] = None,
    ) -> None:
        record = _load_record(entry)
        if record is None:
            return
        record.status = CeleryTaskStatus.FAILED
        record.scheduled_for = None
        record.started_at = None
        record.finished_at = datetime.now(timezone.utc)
        record.celery_task_id = None
        payload: Dict[str, object] = {"force": force, "attempts": entry.attempts, "retry_disabled": True}
        if blockers is not None:
            payload["blockers"] = blockers
        record.set_payload(payload)
        db.session.commit()

    def clear_success(self, media_id: int) -> None:
        record = (
            CeleryTaskRecord.query.filter_by(
                task_name=_THUMBNAIL_RETRY_TASK_NAME,
                object_type="media",
                object_id=media_id,
            )
            .order_by(CeleryTaskRecord.id.desc())
            .first()
        )
        if record is None:
            return
        record.status = CeleryTaskStatus.SUCCESS
        record.scheduled_for = None
        record.celery_task_id = None
        record.finished_at = datetime.now(timezone.utc)
        record.set_payload({})
        db.session.commit()

    def iter_due(self, limit: int) -> Iterable[ThumbnailRetryEntry]:
        pending = (
            CeleryTaskRecord.query.filter(
                CeleryTaskRecord.task_name == _THUMBNAIL_RETRY_TASK_NAME,
                CeleryTaskRecord.object_type == "media",
                CeleryTaskRecord.scheduled_for <= datetime.now(timezone.utc),
                CeleryTaskRecord.status == CeleryTaskStatus.SCHEDULED,
            )
            .order_by(CeleryTaskRecord.scheduled_for)
            .limit(limit)
            .all()
        )
        for record in pending:
            yield _as_entry(record)

    def mark_running(self, entry: ThumbnailRetryEntry, *, started_at: datetime) -> None:
        record = _load_record(entry)
        if record is None:
            return
        record.status = CeleryTaskStatus.RUNNING
        record.started_at = started_at
        db.session.commit()

    def mark_canceled(self, entry: ThumbnailRetryEntry, *, finished_at: datetime) -> None:
        record = _load_record(entry)
        if record is None:
            return
        record.status = CeleryTaskStatus.CANCELED
        record.finished_at = finished_at
        db.session.commit()

    def mark_finished(self, entry: ThumbnailRetryEntry, *, finished_at: datetime, success: bool) -> None:
        record = _load_record(entry)
        if record is None:
            return
        record.status = CeleryTaskStatus.SUCCESS if success else CeleryTaskStatus.FAILED
        record.finished_at = finished_at
        record.celery_task_id = None
        db.session.commit()

    def find_disabled(self, limit: int) -> Iterable[ThumbnailRetryEntry]:
        records = (
            CeleryTaskRecord.query.filter(
                CeleryTaskRecord.task_name == _THUMBNAIL_RETRY_TASK_NAME,
                CeleryTaskRecord.object_type == "media",
                CeleryTaskRecord.status == CeleryTaskStatus.FAILED,
            )
            .order_by(CeleryTaskRecord.updated_at.desc())
            .limit(limit)
            .all()
        )
        for record in records:
            yield _as_entry(record)

    def mark_monitor_reported(self, entries: Sequence[ThumbnailRetryEntry]) -> None:
        if not entries:
            return
        entry_ids = [entry.id for entry in entries]
        records = CeleryTaskRecord.query.filter(CeleryTaskRecord.id.in_(entry_ids)).all()
        for record in records:
            payload = dict(record.payload or {})
            payload["monitor_reported"] = True
            record.set_payload(payload)
        db.session.commit()
