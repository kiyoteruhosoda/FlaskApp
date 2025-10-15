"""TOTP 用ユースケース"""
from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone
from typing import Iterable, List

import pyotp

from features.totp.application.dto import (
    TOTPCreateInput,
    TOTPImportItem,
    TOTPImportPayload,
    TOTPUpdateInput,
)
from features.totp.domain.entities import TOTPCredentialEntity, TOTPPreview
from features.totp.domain.exceptions import (
    TOTPConflictError,
    TOTPNotFoundError,
    TOTPValidationError,
)
from features.totp.domain.validators import (
    validate_algorithm,
    validate_digits_and_period,
    validate_secret,
)
from features.totp.infrastructure.repositories import TOTPCredentialRepository


def _ensure_non_empty(value: str, field: str) -> str:
    if value is None:
        raise TOTPValidationError("必須項目です", field=field)
    stripped = value.strip()
    if not stripped:
        raise TOTPValidationError("必須項目です", field=field)
    return stripped


def _digest_for_algorithm(algorithm: str):
    algo = algorithm.lower()
    if not hasattr(hashlib, algo):
        raise TOTPValidationError("未知のアルゴリズムです", field="algorithm")
    return getattr(hashlib, algo)


class TOTPListUseCase:
    def __init__(self, repository: TOTPCredentialRepository | None = None):
        self.repository = repository or TOTPCredentialRepository()

    def execute(self) -> List[tuple[TOTPCredentialEntity, TOTPPreview]]:
        entities = self.repository.list_all()
        previews: List[tuple[TOTPCredentialEntity, TOTPPreview]] = []
        now = time.time()
        for entity in entities:
            digest = _digest_for_algorithm(entity.algorithm)
            totp = pyotp.TOTP(
                entity.secret,
                digits=entity.digits,
                interval=entity.period,
                digest=digest,
            )
            otp = totp.now()
            remaining = entity.period - int(now) % entity.period
            if remaining <= 0:
                remaining = entity.period
            previews.append((entity, TOTPPreview(otp=otp, remaining_seconds=remaining)))
        return previews


class TOTPCreateUseCase:
    def __init__(self, repository: TOTPCredentialRepository | None = None):
        self.repository = repository or TOTPCredentialRepository()

    def execute(self, payload: TOTPCreateInput) -> TOTPCredentialEntity:
        account = _ensure_non_empty(payload.account, "account")
        issuer = _ensure_non_empty(payload.issuer, "issuer")
        normalized_secret = validate_secret(payload.secret)
        algorithm = validate_algorithm(payload.algorithm)
        digits, period = validate_digits_and_period(payload.digits, payload.period)

        if self.repository.find_by_account_and_issuer(account, issuer):
            raise TOTPConflictError(account, issuer)

        description = payload.description.strip() if payload.description else None

        return self.repository.create(
            account=account,
            issuer=issuer,
            secret=normalized_secret,
            description=description,
            algorithm=algorithm,
            digits=digits,
            period=period,
        )


class TOTPUpdateUseCase:
    def __init__(self, repository: TOTPCredentialRepository | None = None):
        self.repository = repository or TOTPCredentialRepository()

    def execute(self, payload: TOTPUpdateInput) -> TOTPCredentialEntity:
        model = self.repository.find_model_by_id(payload.id)
        if not model:
            raise TOTPNotFoundError(f"TOTP #{payload.id} not found")

        account = _ensure_non_empty(payload.account, "account")
        issuer = _ensure_non_empty(payload.issuer, "issuer")
        algorithm = validate_algorithm(payload.algorithm)
        digits, period = validate_digits_and_period(payload.digits, payload.period)

        existing = None
        if (account != model.account) or (issuer != model.issuer):
            existing = self.repository.find_by_account_and_issuer(account, issuer)
        if existing:
            raise TOTPConflictError(account, issuer)

        description = payload.description.strip() if payload.description else None
        secret = validate_secret(payload.secret) if payload.secret else None

        return self.repository.update(
            model,
            account=account,
            issuer=issuer,
            description=description,
            algorithm=algorithm,
            digits=digits,
            period=period,
            secret=secret,
        )


class TOTPDeleteUseCase:
    def __init__(self, repository: TOTPCredentialRepository | None = None):
        self.repository = repository or TOTPCredentialRepository()

    def execute(self, credential_id: int) -> None:
        model = self.repository.find_model_by_id(credential_id)
        if not model:
            raise TOTPNotFoundError(f"TOTP #{credential_id} not found")
        self.repository.delete(model)


class TOTPExportUseCase:
    def __init__(self, repository: TOTPCredentialRepository | None = None):
        self.repository = repository or TOTPCredentialRepository()

    def execute(self) -> List[dict]:
        entities = self.repository.list_all()
        exported: List[dict] = []
        for entity in entities:
            exported.append(
                {
                    "account": entity.account,
                    "issuer": entity.issuer,
                    "secret": entity.secret,
                    "description": entity.description,
                    "algorithm": entity.algorithm,
                    "digits": entity.digits,
                    "period": entity.period,
                    "created_at": entity.created_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
                }
            )
        return exported


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    if not value:
        return None
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise TOTPValidationError("created_at の形式が不正です", field="created_at") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class TOTPImportUseCase:
    def __init__(self, repository: TOTPCredentialRepository | None = None):
        self.repository = repository or TOTPCredentialRepository()

    def _normalize_items(self, items: Iterable[TOTPImportItem]) -> List[dict]:
        normalized: List[dict] = []
        for item in items:
            account = _ensure_non_empty(item.account, "account")
            issuer = _ensure_non_empty(item.issuer, "issuer")
            algorithm = validate_algorithm(item.algorithm)
            digits, period = validate_digits_and_period(item.digits, item.period)
            secret = validate_secret(item.secret)
            if isinstance(item.created_at, datetime):
                created_at = item.created_at.astimezone(timezone.utc)
            else:
                created_at = _parse_datetime(item.created_at)
            normalized.append(
                {
                    "account": account,
                    "issuer": issuer,
                    "algorithm": algorithm,
                    "digits": digits,
                    "period": period,
                    "secret": secret,
                    "description": item.description.strip() if item.description else None,
                    "created_at": created_at,
                }
            )
        return normalized

    def execute(self, payload: TOTPImportPayload) -> dict:
        items = list(payload.items)
        if not items:
            raise TOTPValidationError("インポート対象がありません", field="items")

        normalized = self._normalize_items(items)

        conflicts: List[dict] = []
        for item in normalized:
            existing = self.repository.find_by_account_and_issuer(item["account"], item["issuer"])
            if existing:
                conflicts.append(
                    {
                        "account": item["account"],
                        "issuer": item["issuer"],
                        "existing_id": existing.id,
                    }
                )

        if conflicts and not payload.force:
            return {"conflicts": conflicts, "imported": []}

        imported_entities = self.repository.bulk_upsert(normalized)
        return {
            "conflicts": conflicts,
            "imported": [entity.id for entity in imported_entities],
        }
