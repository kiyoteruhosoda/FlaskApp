"""Wiki機能のSQLAlchemyモデル."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.db import db

BigInt = db.BigInteger().with_variant(db.Integer, "sqlite")


# Wiki ページとカテゴリの中間テーブル
wiki_page_category = db.Table(
    "wiki_page_category",
    db.Column("page_id", BigInt, db.ForeignKey("wiki_page.id"), primary_key=True),
    db.Column("category_id", BigInt, db.ForeignKey("wiki_category.id"), primary_key=True),
)


class WikiPage(db.Model):
    """Wikiページモデル"""

    __tablename__ = "wiki_page"

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(db.String(255), nullable=False)
    content: Mapped[str] = mapped_column(db.Text, nullable=False)
    slug: Mapped[str] = mapped_column(db.String(255), nullable=False, unique=True, index=True)

    # 公開状態
    is_published: Mapped[bool] = mapped_column(db.Boolean, nullable=False, default=True)

    # 階層構造
    parent_id: Mapped[int | None] = mapped_column(BigInt, db.ForeignKey("wiki_page.id"), nullable=True)
    sort_order: Mapped[int] = mapped_column(db.Integer, nullable=False, default=0)

    # タイムスタンプ
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # ユーザー関連
    created_by_id: Mapped[int] = mapped_column(BigInt, db.ForeignKey("user.id"), nullable=False)
    updated_by_id: Mapped[int] = mapped_column(BigInt, db.ForeignKey("user.id"), nullable=False)

    # リレーション
    created_by: Mapped["User"] = relationship(
        "User",
        foreign_keys=[created_by_id],
        backref="created_wiki_pages",
    )
    updated_by: Mapped["User"] = relationship(
        "User",
        foreign_keys=[updated_by_id],
        backref="updated_wiki_pages",
    )

    parent: Mapped["WikiPage | None"] = relationship(
        "WikiPage",
        remote_side=[id],
        back_populates="children",
    )
    children: Mapped[list["WikiPage"]] = relationship(
        "WikiPage",
        back_populates="parent",
    )
    categories: Mapped[list["WikiCategory"]] = relationship(
        "WikiCategory",
        secondary=wiki_page_category,
        back_populates="pages",
    )
    revisions: Mapped[list["WikiRevision"]] = relationship(
        "WikiRevision",
        back_populates="page",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<WikiPage {self.title}>"

    def to_dict(self) -> dict[str, object | None]:
        """辞書形式で返す"""

        return {
            "id": self.id,
            "title": self.title,
            "content": self.content,
            "slug": self.slug,
            "is_published": self.is_published,
            "parent_id": self.parent_id,
            "sort_order": self.sort_order,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "created_by_id": self.created_by_id,
            "updated_by_id": self.updated_by_id,
        }


class WikiCategory(db.Model):
    """Wikiカテゴリモデル"""

    __tablename__ = "wiki_category"

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(db.String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(db.Text, nullable=True)
    slug: Mapped[str] = mapped_column(db.String(100), nullable=False, unique=True, index=True)
    sort_order: Mapped[int] = mapped_column(db.Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    pages: Mapped[list[WikiPage]] = relationship(
        "WikiPage",
        secondary=wiki_page_category,
        back_populates="categories",
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<WikiCategory {self.name}>"

    def to_dict(self) -> dict[str, object | None]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "slug": self.slug,
            "sort_order": self.sort_order,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class WikiRevision(db.Model):
    """Wikiページの履歴管理"""

    __tablename__ = "wiki_revision"

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    page_id: Mapped[int] = mapped_column(BigInt, db.ForeignKey("wiki_page.id"), nullable=False)
    title: Mapped[str] = mapped_column(db.String(255), nullable=False)
    content: Mapped[str] = mapped_column(db.Text, nullable=False)
    revision_number: Mapped[int] = mapped_column(db.Integer, nullable=False)
    change_summary: Mapped[str | None] = mapped_column(db.String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    created_by_id: Mapped[int] = mapped_column(BigInt, db.ForeignKey("user.id"), nullable=False)

    # リレーション
    page: Mapped[WikiPage] = relationship(
        "WikiPage",
        back_populates="revisions",
    )
    created_by: Mapped["User"] = relationship(
        "User",
        backref="wiki_revisions",
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<WikiRevision {self.page_id} v{self.revision_number}>"

    def to_dict(self) -> dict[str, object | None]:
        return {
            "id": self.id,
            "page_id": self.page_id,
            "title": self.title,
            "content": self.content,
            "revision_number": self.revision_number,
            "change_summary": self.change_summary,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "created_by_id": self.created_by_id,
        }
