"""SQLAlchemy models for recording Celery task executions and schedules."""

from __future__ import annotations

from __future__ import annotations

import enum
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.db import db


BigInt = db.BigInteger().with_variant(db.Integer, "sqlite")


class CeleryTaskStatus(enum.Enum):
    """Lifecycle states for persisted Celery task records."""

    SCHEDULED = "scheduled"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELED = "canceled"


class CeleryTaskRecord(db.Model):
    """Persisted metadata about Celery task invocations and schedules."""

    __tablename__ = "celery_task"

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    task_name: Mapped[str] = mapped_column(db.String(255), nullable=False)
    object_type: Mapped[str | None] = mapped_column(db.String(64), nullable=True)
    object_id: Mapped[str | None] = mapped_column(db.String(255), nullable=True)
    celery_task_id: Mapped[str | None] = mapped_column(db.String(255), nullable=True, unique=True)
    status: Mapped[CeleryTaskStatus] = mapped_column(
        db.Enum(
            CeleryTaskStatus,
            name="celery_task_status",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=CeleryTaskStatus.QUEUED,
        server_default=CeleryTaskStatus.QUEUED.value,
    )
    scheduled_for: Mapped[datetime | None] = mapped_column(db.DateTime, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(db.DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(db.DateTime, nullable=True)
    payload_json: Mapped[str] = mapped_column(
        db.Text,
        nullable=False,
        default="{}",
        server_default="{}",
    )
    result_json: Mapped[str | None] = mapped_column(db.Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(db.Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        db.Index("ix_celery_task_task_name_status", "task_name", "status"),
        db.Index("ix_celery_task_object", "object_type", "object_id"),
    )

    job_syncs: Mapped[list["JobSync"]] = relationship(
        "JobSync",
        back_populates="celery_task",
    )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _safe_dump(data: Any) -> str:
        try:
            return json.dumps(data, ensure_ascii=False, default=str)
        except TypeError:
            return json.dumps(str(data), ensure_ascii=False)

    @staticmethod
    def _safe_load(payload: Optional[str]) -> Dict[str, Any]:
        if not payload:
            return {}
        try:
            loaded = json.loads(payload)
        except json.JSONDecodeError:
            return {}
        return loaded if isinstance(loaded, dict) else {"value": loaded}

    @property
    def payload(self) -> Dict[str, Any]:
        return self._safe_load(self.payload_json)

    def set_payload(self, payload: Dict[str, Any]) -> None:
        self.payload_json = self._safe_dump(payload)

    def update_payload(self, updates: Dict[str, Any]) -> None:
        if not updates:
            return
        merged = self.payload
        merged.update({k: v for k, v in updates.items() if v is not None or k not in merged})
        self.payload_json = self._safe_dump(merged)

    @property
    def result(self) -> Dict[str, Any]:
        return self._safe_load(self.result_json)

    def set_result(self, payload: Dict[str, Any]) -> None:
        self.result_json = self._safe_dump(payload)

    # ------------------------------------------------------------------
    # Factory helpers
    # ------------------------------------------------------------------
    @classmethod
    def get_or_create(
        cls,
        *,
        task_name: str,
        celery_task_id: Optional[str] = None,
        object_identity: Optional[Tuple[Optional[str], Optional[str]]] = None,
    ) -> "CeleryTaskRecord":
        """Return an existing record or create a new one for the provided info."""

        from core.db import db as scoped_db

        record: Optional["CeleryTaskRecord"] = None

        if celery_task_id:
            record = cls.query.filter_by(celery_task_id=celery_task_id).one_or_none()

        if record is None and object_identity is not None:
            obj_type, obj_id = object_identity
            if obj_type is not None and obj_id is not None:
                record = (
                    cls.query.filter_by(
                        task_name=task_name,
                        object_type=obj_type,
                        object_id=obj_id,
                    )
                    .order_by(cls.id.desc())
                    .first()
                )

        if record is None:
            obj_type, obj_id = object_identity or (None, None)
            record = cls(
                task_name=task_name,
                object_type=obj_type,
                object_id=obj_id,
            )
            scoped_db.session.add(record)

        if celery_task_id and record.celery_task_id != celery_task_id:
            record.celery_task_id = celery_task_id

        return record


__all__ = ["CeleryTaskRecord", "CeleryTaskStatus"]
