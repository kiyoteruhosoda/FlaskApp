from __future__ import annotations
import os
from typing import Dict
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine


def get_engine_from_env(env: Dict[str, str] | None = None) -> Engine:
    env = env or os.environ
    url = env.get("FPV_DB_URL") or env.get("DATABASE_URI")
    if not url:
        raise RuntimeError("FPV_DB_URL or DATABASE_URI not set")
    return create_engine(url, future=True)
