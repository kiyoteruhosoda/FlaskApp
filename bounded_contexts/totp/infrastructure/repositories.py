"""TOTP リポジトリ実装"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, List, Optional

from core.db import db
from core.models.totp import TOTPCredential as TOTPCredentialModel
from bounded_contexts.totp.domain.entities import TOTPCredentialEntity


class TOTPCredentialRepository:
    """TOTP シークレットの永続化"""

    def _to_entity(self, model: TOTPCredentialModel) -> TOTPCredentialEntity:
        return TOTPCredentialEntity(
            id=model.id,
            user_id=model.user_id,
            account=model.account,
            issuer=model.issuer,
            secret=model.secret,
            description=model.description,
            algorithm=model.algorithm,
            digits=model.digits,
            period=model.period,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def list_all(self, *, user_id: int) -> List[TOTPCredentialEntity]:
        models = (
            TOTPCredentialModel.query.filter_by(user_id=user_id)
            .order_by(TOTPCredentialModel.issuer.asc(), TOTPCredentialModel.account.asc())
            .all()
        )
        return [self._to_entity(m) for m in models]

    def find_by_id(self, credential_id: int, *, user_id: int) -> Optional[TOTPCredentialEntity]:
        model = self.find_model_by_id(credential_id, user_id=user_id)
        if not model:
            return None
        return self._to_entity(model)

    def find_model_by_id(self, credential_id: int, *, user_id: int) -> Optional[TOTPCredentialModel]:
        return (
            TOTPCredentialModel.query.filter_by(id=credential_id, user_id=user_id)
            .first()
        )
    def find_by_account_and_issuer(
        self, account: str, issuer: str, *, user_id: int
    ) -> Optional[TOTPCredentialEntity]:
        model = (
            TOTPCredentialModel.query.filter_by(account=account, issuer=issuer, user_id=user_id)
            .order_by(TOTPCredentialModel.id.asc())
            .first()
        )
        if not model:
            return None
        return self._to_entity(model)

    def create(
        self,
        *,
        user_id: int,
        account: str,
        issuer: str,
        secret: str,
        description: str | None,
        algorithm: str,
        digits: int,
        period: int,
    ) -> TOTPCredentialEntity:
        now = datetime.now(timezone.utc)
        model = TOTPCredentialModel(
            user_id=user_id,
            account=account,
            issuer=issuer,
            secret=secret,
            description=description,
            algorithm=algorithm,
            digits=digits,
            period=period,
            created_at=now,
            updated_at=now,
        )
        db.session.add(model)
        db.session.commit()
        return self._to_entity(model)

    def update(
        self,
        model: TOTPCredentialModel,
        *,
        account: str,
        issuer: str,
        description: str | None,
        algorithm: str,
        digits: int,
        period: int,
        secret: str | None = None,
    ) -> TOTPCredentialEntity:
        model.account = account
        model.issuer = issuer
        model.description = description
        model.algorithm = algorithm
        model.digits = digits
        model.period = period
        if secret is not None:
            model.secret = secret
        model.touch()
        db.session.add(model)
        db.session.commit()
        return self._to_entity(model)

    def delete(self, model: TOTPCredentialModel) -> None:
        db.session.delete(model)
        db.session.commit()

    def bulk_upsert(self, items: Iterable[dict], *, user_id: int) -> List[TOTPCredentialEntity]:
        """インポート用の一括アップサート"""

        now = datetime.now(timezone.utc)
        entities: List[TOTPCredentialEntity] = []
        for item in items:
            account = item["account"]
            issuer = item["issuer"]
            existing = (
                TOTPCredentialModel.query.filter_by(account=account, issuer=issuer, user_id=user_id)
                .first()
            )
            if existing:
                existing.secret = item["secret"]
                existing.description = item.get("description")
                existing.algorithm = item.get("algorithm", existing.algorithm)
                existing.digits = item.get("digits", existing.digits)
                existing.period = item.get("period", existing.period)
                created_at = item.get("created_at")
                if created_at:
                    existing.created_at = created_at
                existing.updated_at = now
                model = existing
            else:
                model = TOTPCredentialModel(
                    user_id=user_id,
                    account=account,
                    issuer=issuer,
                    secret=item["secret"],
                    description=item.get("description"),
                    algorithm=item.get("algorithm", "SHA1"),
                    digits=item.get("digits", 6),
                    period=item.get("period", 30),
                    created_at=item.get("created_at") or now,
                    updated_at=now,
                )
                db.session.add(model)
            entities.append(model)
        db.session.commit()
        return [self._to_entity(model) for model in entities]
