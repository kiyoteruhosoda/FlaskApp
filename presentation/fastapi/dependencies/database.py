"""FastAPI DBセッション依存コンポーネント。"""
from __future__ import annotations

from typing import Generator

from fastapi import Depends
from sqlalchemy.orm import Session

from shared.kernel.database.session import get_db

__all__ = ["get_db"]
