"""TOTP アプリケーション層 DTO"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Optional


@dataclass(slots=True)
class TOTPCreateInput:
    account: str
    issuer: str
    secret: str
    description: Optional[str] = None
    algorithm: str = "SHA1"
    digits: int = 6
    period: int = 30


@dataclass(slots=True)
class TOTPUpdateInput:
    id: int
    account: str
    issuer: str
    description: Optional[str]
    algorithm: str
    digits: int
    period: int
    secret: Optional[str] = None


@dataclass(slots=True)
class TOTPImportItem:
    account: str
    issuer: str
    secret: str
    description: Optional[str]
    created_at: Optional[datetime]
    algorithm: str = "SHA1"
    digits: int = 6
    period: int = 30


@dataclass(slots=True)
class TOTPImportPayload:
    items: Iterable[TOTPImportItem]
    force: bool = False
