"""Flask 非依存の SQLAlchemy セッションファクトリ。

FastAPI のルートでは ``get_db`` を ``Depends()`` で注入して使用する。
Flask-SQLAlchemy の ``db.session`` と同じデータベースを参照するが、
Flask のアプリコンテキストに依存しない。
"""
from __future__ import annotations

from collections.abc import Generator
from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from shared.kernel.settings.settings import settings

_engine = None
_SessionLocal: Optional[sessionmaker] = None


def _get_engine():
    global _engine
    if _engine is None:
        db_url = settings.sqlalchemy_database_uri or settings.database_uri
        if not db_url:
            raise RuntimeError(
                "データベースURLが設定されていません。"
                "DATABASE_URI 環境変数を設定してください。"
            )
        _engine = create_engine(
            db_url,
            pool_pre_ping=True,
            pool_recycle=3600,
        )
    return _engine


def _get_session_factory() -> sessionmaker:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            bind=_get_engine(),
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )
    return _SessionLocal


def get_db() -> Generator[Session, None, None]:
    """FastAPI の ``Depends()`` 用 DBセッション依存関数。

    使用例::

        @router.get("/items")
        def list_items(db: Session = Depends(get_db)):
            return db.query(Item).all()
    """
    factory = _get_session_factory()
    db = factory()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


__all__ = ["get_db"]
