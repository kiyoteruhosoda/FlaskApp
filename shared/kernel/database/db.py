"""Flask 非依存の SQLAlchemy セットアップ。

Flask-SQLAlchemy を廃止し、純粋な SQLAlchemy の ``DeclarativeBase`` /
``scoped_session`` を使う。既存コードとの互換性のために ``db`` オブジェクトを
同じインターフェースで提供する（``db.Model``、``db.session``、
``db.init_app()`` 等）。

モデルは ``db.Model`` を継承していた場合も、そのまま動作する。
``db.session`` はスコープセッション（スレッドローカル）を返す。
"""
from __future__ import annotations

import logging
from typing import Any

import sqlalchemy as sa
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    event,
    inspect,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    RelationshipProperty,
    backref,
    relationship,
    scoped_session,
    sessionmaker,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DeclarativeBase（全モデルの基底クラス）
# ---------------------------------------------------------------------------


class _Base(DeclarativeBase):
    """SQLAlchemy の宣言的基底クラス。"""


# ---------------------------------------------------------------------------
# スコープセッション（スレッドローカル、Flask-SQLAlchemy 互換）
# ---------------------------------------------------------------------------

_scoped_session: scoped_session | None = None


def _get_scoped_session() -> scoped_session:
    global _scoped_session
    if _scoped_session is None:
        from shared.kernel.settings.settings import settings

        db_url = settings.sqlalchemy_database_uri or settings.database_uri
        if not db_url:
            raise RuntimeError(
                "DATABASE_URI が設定されていません。環境変数を確認してください。"
            )
        engine = sa.create_engine(
            db_url,
            pool_pre_ping=True,
            pool_recycle=3600,
        )
        factory = sessionmaker(
            bind=engine,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )
        _scoped_session = scoped_session(factory)
    return _scoped_session


# ---------------------------------------------------------------------------
# Flask-SQLAlchemy 互換ラッパー
# ---------------------------------------------------------------------------


class _DB:
    """Flask-SQLAlchemy の ``db`` オブジェクトと同じインターフェースを提供する。

    移行期間中、既存コードが ``db.Model``・``db.session``・``db.Column`` 等を
    参照し続けられるようにする互換レイヤー。
    """

    # モデル基底クラス
    Model = _Base

    # SQLAlchemy 型／関数のエイリアス（db.Column, db.String, ...）
    Column = Column
    String = String
    Integer = Integer
    BigInteger = BigInteger
    Boolean = Boolean
    DateTime = DateTime
    Float = Float
    Text = Text
    LargeBinary = LargeBinary
    ForeignKey = ForeignKey
    UniqueConstraint = UniqueConstraint
    relationship = relationship
    backref = backref
    event = event
    inspect = inspect
    Table = sa.Table

    def __init__(self) -> None:
        self._app: Any = None

    # ------------------------------------------------------------------
    # Flask-SQLAlchemy 互換 init_app（Flask アプリへの登録）
    # ------------------------------------------------------------------

    def init_app(self, app: Any) -> None:
        """Flask アプリへ登録する（Flask-SQLAlchemy 互換）。

        Flask-Migrate が ``app.extensions['migrate'].db`` を参照するため、
        Flask-SQLAlchemy との互換性を維持するためにここでダミー登録する。
        """
        self._app = app
        # Flask-Migrate との互換: engine / metadata を提供
        app.extensions = getattr(app, "extensions", {})
        # Flask-SQLAlchemy がセットしていた構造を模倣
        if not hasattr(app, "_db"):
            app._db = self

    # ------------------------------------------------------------------
    # session プロパティ（スコープセッション）
    # ------------------------------------------------------------------

    @property
    def session(self) -> scoped_session:
        """スレッドローカルなスコープセッションを返す。"""
        return _get_scoped_session()

    # ------------------------------------------------------------------
    # engine / metadata（Alembic 用）
    # ------------------------------------------------------------------

    @property
    def engine(self) -> sa.Engine:
        return _get_scoped_session().bind  # type: ignore[return-value]

    @property
    def metadata(self) -> sa.MetaData:
        return _Base.metadata

    # ------------------------------------------------------------------
    # create_all（SQLite テスト用）
    # ------------------------------------------------------------------

    def create_all(self, bind: Any = None) -> None:
        """全テーブルを作成する（テスト・開発用）。"""
        engine = bind or self.engine
        _Base.metadata.create_all(engine)

    def drop_all(self, bind: Any = None) -> None:
        """全テーブルを削除する（テスト用）。"""
        engine = bind or self.engine
        _Base.metadata.drop_all(engine)


db = _DB()

__all__ = ["db"]

