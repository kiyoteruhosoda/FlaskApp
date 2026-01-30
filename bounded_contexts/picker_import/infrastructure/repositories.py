"""Picker Import repositories - Infrastructure layer.

PickerSession / PickerSelection の永続化を担当するリポジトリ群です。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Final

from sqlalchemy import update

from shared.kernel.database.db import db
from core.models.picker_session import PickerSession
from core.models.photo_models import Media, PickerSelection
from bounded_contexts.picker_import.domain.entities import ImportSelection, ImportSession
from shared.infrastructure.repositories.base import BaseRepository, Mapper, UnitOfWork


@dataclass(frozen=True, slots=True)
class PickerSelectionMapper(Mapper[PickerSelection, ImportSelection]):
    """PickerSelection → ImportSelection マッパー."""

    def to_domain(self, model: PickerSelection) -> ImportSelection:
        return ImportSelection(
            selection_id=model.id,
            session_id=model.session_id,
            google_media_id=model.google_media_id,
            status=model.status,
            attempts=model.attempts,
            locked_by=model.locked_by,
            locked_at=model.lock_heartbeat_at,
        )


class PickerSelectionRepository(BaseRepository[PickerSelection]):
    """PickerSelectionに関する永続化操作をカプセル化."""

    # ステータス定数
    STATUS_ENQUEUED: Final[str] = "enqueued"
    STATUS_RUNNING: Final[str] = "running"
    STATUS_FAILED: Final[str] = "failed"

    def __init__(
        self,
        mapper: PickerSelectionMapper | None = None,
        uow: UnitOfWork | None = None,
    ) -> None:
        super().__init__(uow)
        self._mapper = mapper or PickerSelectionMapper()

    def list_by_status(self, status: str) -> list[PickerSelection]:
        """指定ステータスかつ google_media_id を持つ Selection を取得."""
        query = PickerSelection.query.filter(
            PickerSelection.status == status,
            PickerSelection.google_media_id.isnot(None),
        )
        if status == self.STATUS_ENQUEUED:
            query = query.order_by(PickerSelection.id)
        return query.all()

    def list_enqueued(self) -> list[PickerSelection]:
        return self.list_by_status(self.STATUS_ENQUEUED)

    def list_running(self) -> list[PickerSelection]:
        return self.list_by_status(self.STATUS_RUNNING)

    def list_failed(self) -> list[PickerSelection]:
        return self.list_by_status(self.STATUS_FAILED)

    def list_by_session(self, session_id: int) -> list[PickerSelection]:
        return PickerSelection.query.filter_by(session_id=session_id).all()

    def get(self, selection_id: int) -> PickerSelection | None:
        return db.session.get(PickerSelection, selection_id)

    def to_domain(self, model: PickerSelection) -> ImportSelection:
        return self._mapper.to_domain(model)

    def claim(
        self,
        *,
        selection_id: int,
        session_id: int,
        locked_by: str,
        now: datetime,
    ) -> bool:
        """enqueued → running への原子的状態遷移."""
        stmt = (
            update(PickerSelection)
            .where(
                PickerSelection.id == selection_id,
                PickerSelection.session_id == session_id,
                PickerSelection.status == self.STATUS_ENQUEUED,
            )
            .values(
                status=self.STATUS_RUNNING,
                locked_by=locked_by,
                lock_heartbeat_at=now,
                attempts=PickerSelection.attempts + 1,
                started_at=now,
                last_transition_at=now,
            )
        )
        result = db.session.execute(stmt)
        if result.rowcount == 0:
            self.rollback()
            return False
        self.commit()
        return True


@dataclass(frozen=True, slots=True)
class PickerSessionMapper(Mapper[PickerSession, ImportSession]):
    """PickerSession → ImportSession マッパー."""

    def to_domain(self, model: PickerSession) -> ImportSession:
        return ImportSession(
            id=model.id,
            account_id=model.account_id,
            status=model.status,
            session_key=model.session_id,
            selected_count=model.selected_count or 0,
            media_items_set=bool(model.media_items_set),
        )


class PickerSessionRepository(BaseRepository[PickerSession]):
    """PickerSessionの取得と保存を司る."""

    def __init__(
        self,
        mapper: PickerSessionMapper | None = None,
        uow: UnitOfWork | None = None,
    ) -> None:
        super().__init__(uow)
        self._mapper = mapper or PickerSessionMapper()

    def get(self, session_id: int) -> PickerSession | None:
        return db.session.get(PickerSession, session_id)

    def to_domain(self, model: PickerSession) -> ImportSession:
        return self._mapper.to_domain(model)

    def list_importing(self) -> list[PickerSession]:
        return (
            PickerSession.query.filter(
                PickerSession.status == "importing",
                PickerSession.account_id.isnot(None),
            ).all()
        )


class MediaRepository(BaseRepository[Media]):
    """Mediaモデルの永続化."""

    pass


__all__ = [
    "MediaRepository",
    "PickerSelectionMapper",
    "PickerSelectionRepository",
    "PickerSessionMapper",
    "PickerSessionRepository",
]
