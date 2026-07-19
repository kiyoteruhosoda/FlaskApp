"""TOTP リポジトリ実装"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, List, Optional

from shared.kernel.database.db import db
from bounded_contexts.totp.infrastructure.totp_models import TOTPCredential as TOTPCredentialModel
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

    def _find_models_by_account_and_issuer(
        self, pairs: Iterable[tuple[str, str]], *, user_id: int
    ) -> dict[tuple[str, str], TOTPCredentialModel]:
        """(account, issuer) の組ごとに既存モデルを1クエリで取得.

        各組につき id 昇順の先頭を返す（``find_by_account_and_issuer`` と同じ）。
        """
        wanted = set(pairs)
        if not wanted:
            return {}
        models = (
            TOTPCredentialModel.query.filter(
                TOTPCredentialModel.user_id == user_id,
                TOTPCredentialModel.account.in_({account for account, _ in wanted}),
            )
            .order_by(TOTPCredentialModel.id.asc())
            .all()
        )
        result: dict[tuple[str, str], TOTPCredentialModel] = {}
        for model in models:
            key = (model.account, model.issuer)
            if key in wanted and key not in result:
                result[key] = model
        return result

    def find_existing_by_account_and_issuer(
        self, pairs: Iterable[tuple[str, str]], *, user_id: int
    ) -> dict[tuple[str, str], TOTPCredentialEntity]:
        """(account, issuer) の組ごとに既存クレデンシャルを1クエリで取得"""
        return {
            key: self._to_entity(model)
            for key, model in self._find_models_by_account_and_issuer(
                pairs, user_id=user_id
            ).items()
        }

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
        items = list(items)
        # 1件ごとの存在確認SELECTを避け、既存モデルを一括で取得する
        models_by_key = self._find_models_by_account_and_issuer(
            ((item["account"], item["issuer"]) for item in items), user_id=user_id
        )
        entities: List[TOTPCredentialEntity] = []
        for item in items:
            account = item["account"]
            issuer = item["issuer"]
            existing = models_by_key.get((account, issuer))
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
                # 同一 (account, issuer) がインポート内で重複した場合に
                # 2件目以降を更新として扱う（従来の逐次SELECTと同じ挙動）
                models_by_key[(account, issuer)] = model
            entities.append(model)
        db.session.commit()
        return [self._to_entity(model) for model in entities]
