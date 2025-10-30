"""SQLAlchemy repository for managing passkey credentials."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy import select

from core.models.passkey import PasskeyCredential


class SqlAlchemyPasskeyRepository:
    """Persist and retrieve :class:`PasskeyCredential` instances."""

    def __init__(self, session) -> None:
        self._session = session

    def list_for_user(self, user_id: int) -> list[PasskeyCredential]:
        stmt = (
            select(PasskeyCredential)
            .where(PasskeyCredential.user_id == user_id)
            .order_by(PasskeyCredential.created_at.asc())
        )
        return list(self._session.execute(stmt).scalars().all())

    def find_by_credential_id(self, credential_id: str) -> PasskeyCredential | None:
        stmt = select(PasskeyCredential).where(
            PasskeyCredential.credential_id == credential_id
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def find_for_user(self, user_id: int, credential_id: int) -> PasskeyCredential | None:
        stmt = select(PasskeyCredential).where(
            PasskeyCredential.user_id == user_id,
            PasskeyCredential.id == credential_id,
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def add(
        self,
        *,
        user,
        credential_id: str,
        public_key: str,
        sign_count: int,
        transports: Iterable[str] | None = None,
        name: str | None = None,
        attestation_format: str | None = None,
        aaguid: str | None = None,
        backup_eligible: bool = False,
        backup_state: bool = False,
    ) -> PasskeyCredential:
        record = PasskeyCredential(
            user=user,
            credential_id=credential_id,
            public_key=public_key,
            sign_count=sign_count,
            transports=list(transports) if transports else None,
            name=name,
            attestation_format=attestation_format,
            aaguid=aaguid,
            backup_eligible=backup_eligible,
            backup_state=backup_state,
        )
        self._session.add(record)
        self._session.commit()
        self._session.refresh(record)
        return record

    def touch_usage(self, credential: PasskeyCredential, new_sign_count: int) -> None:
        credential.sign_count = new_sign_count
        credential.last_used_at = datetime.now(timezone.utc)
        credential.touch()
        self._session.commit()

    def delete(self, credential: PasskeyCredential) -> None:
        self._session.delete(credential)
        self._session.commit()
