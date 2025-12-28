from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy import update

from core.db import db
from core.models.picker_session import PickerSession
from core.models.photo_models import Media, PickerSelection
from domain.picker_import.entities import ImportSelection, ImportSession


@dataclass
class PickerSelectionMapper:
    """SQLAlchemyモデルをドメインオブジェクトに変換するマッパー。"""

    def to_domain(self, selection: PickerSelection) -> ImportSelection:
        return ImportSelection(
            selection_id=selection.id,
            session_id=selection.session_id,
            google_media_id=selection.google_media_id,
            status=selection.status,
            attempts=selection.attempts,
            locked_by=selection.locked_by,
            locked_at=selection.lock_heartbeat_at,
        )


class PickerSelectionRepository:
    """PickerSelectionに関する永続化操作をカプセル化。"""

    def __init__(self, mapper: Optional[PickerSelectionMapper] = None) -> None:
        self.mapper = mapper or PickerSelectionMapper()

    def list_enqueued(self) -> list[PickerSelection]:
        return (
            PickerSelection.query.filter(
                PickerSelection.status == "enqueued",
                PickerSelection.google_media_id.isnot(None),
            )
            .order_by(PickerSelection.id)
            .all()
        )

    def list_running(self) -> list[PickerSelection]:
        return (
            PickerSelection.query.filter(
                PickerSelection.status == "running",
                PickerSelection.google_media_id.isnot(None),
            ).all()
        )

    def list_failed(self) -> list[PickerSelection]:
        return (
            PickerSelection.query.filter(
                PickerSelection.status == "failed",
                PickerSelection.google_media_id.isnot(None),
            ).all()
        )

    def list_by_session(self, session_id: int) -> list[PickerSelection]:
        return PickerSelection.query.filter_by(session_id=session_id).all()

    def get(self, selection_id: int) -> Optional[PickerSelection]:
        return PickerSelection.query.get(selection_id)

    def to_domain(self, selection: PickerSelection) -> ImportSelection:
        return self.mapper.to_domain(selection)

    def save(self, selection: PickerSelection) -> None:
        db.session.add(selection)

    def commit(self) -> None:
        db.session.commit()

    def rollback(self) -> None:
        db.session.rollback()

    def claim(
        self,
        *,
        selection_id: int,
        session_id: int,
        locked_by: str,
        now: datetime,
    ) -> bool:
        stmt = (
            update(PickerSelection)
            .where(
                PickerSelection.id == selection_id,
                PickerSelection.session_id == session_id,
                PickerSelection.status == "enqueued",
            )
            .values(
                status="running",
                locked_by=locked_by,
                lock_heartbeat_at=now,
                attempts=PickerSelection.attempts + 1,
                started_at=now,
                last_transition_at=now,
            )
        )
        res = db.session.execute(stmt)
        if res.rowcount == 0:
            db.session.rollback()
            return False
        db.session.commit()
        return True


class PickerSessionRepository:
    """PickerSessionの取得と保存を司る。"""

    def get(self, session_id: int) -> Optional[PickerSession]:
        return PickerSession.query.get(session_id)

    def to_domain(self, model: PickerSession) -> ImportSession:
        return ImportSession(
            id=model.id,
            account_id=model.account_id,
            status=model.status,
            session_key=model.session_id,
            selected_count=model.selected_count or 0,
            media_items_set=bool(model.media_items_set),
        )

    def save(self, model: PickerSession) -> None:
        db.session.add(model)

    def commit(self) -> None:
        db.session.commit()

    def list_importing(self) -> list[PickerSession]:
        return (
            PickerSession.query.filter(
                PickerSession.status == "importing",
                PickerSession.account_id.isnot(None),
            ).all()
        )


class MediaRepository:
    """Mediaモデルの永続化。"""

    def add(self, media: Media) -> None:
        db.session.add(media)

    def commit(self) -> None:
        db.session.commit()


__all__ = [
    "PickerSelectionRepository",
    "PickerSessionRepository",
    "PickerSelectionMapper",
    "MediaRepository",
]
