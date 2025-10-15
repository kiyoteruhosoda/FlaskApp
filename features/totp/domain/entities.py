"""TOTP 機能のエンティティ定義"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(slots=True)
class TOTPCredentialEntity:
    """TOTP シークレットを表すドメインエンティティ"""

    id: int
    account: str
    issuer: str
    secret: str
    description: Optional[str]
    algorithm: str
    digits: int
    period: int
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class TOTPPreview:
    """UI プレビュー用の OTP 情報"""

    otp: str
    remaining_seconds: int
