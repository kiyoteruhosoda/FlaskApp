"""Infrastructure layer base classes.

リポジトリ共通操作の基底クラスを提供します。
DIP（依存性逆転の原則）に従い、具象クラスはこの基底を継承します。
"""

from __future__ import annotations

from abc import abstractmethod
from typing import Generic, Protocol, TypeVar, runtime_checkable

from core.db import db


T = TypeVar("T")
TModel = TypeVar("TModel")
TDomain = TypeVar("TDomain")


@runtime_checkable
class Mapper(Protocol[TModel, TDomain]):
    """モデルとドメインオブジェクト間のマッピング契約."""

    def to_domain(self, model: TModel) -> TDomain:
        """SQLAlchemyモデルからドメインオブジェクトへ変換."""
        ...


class UnitOfWork:
    """Unit of Work パターンの実装.

    トランザクション境界を管理し、複数リポジトリ操作を
    単一のコミットで完了させます。
    """

    def commit(self) -> None:
        """現在のセッションをコミット."""
        db.session.commit()

    def rollback(self) -> None:
        """現在のセッションをロールバック."""
        db.session.rollback()

    def flush(self) -> None:
        """変更をフラッシュ（DBへ書き込み、コミットはしない）."""
        db.session.flush()


class BaseRepository(Generic[TModel]):
    """リポジトリ基底クラス.

    SQLAlchemyモデルの永続化操作を共通化します。

    Attributes:
        uow: Unit of Work インスタンス（共有トランザクション管理）
    """

    def __init__(self, uow: UnitOfWork | None = None) -> None:
        self._uow = uow or UnitOfWork()

    @property
    def uow(self) -> UnitOfWork:
        """Unit of Work を取得."""
        return self._uow

    def add(self, entity: TModel) -> None:
        """エンティティをセッションに追加."""
        db.session.add(entity)

    def save(self, entity: TModel) -> None:
        """エンティティを保存（addのエイリアス）."""
        self.add(entity)

    def commit(self) -> None:
        """変更をコミット."""
        self._uow.commit()

    def rollback(self) -> None:
        """変更をロールバック."""
        self._uow.rollback()


__all__ = ["BaseRepository", "Mapper", "UnitOfWork"]
