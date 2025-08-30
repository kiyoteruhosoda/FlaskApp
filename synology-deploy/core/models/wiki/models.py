"""
Wiki機能のSQLAlchemyモデル
"""

from datetime import datetime, timezone
from core.db import db
from sqlalchemy import text

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
    
    id = db.Column(BigInt, primary_key=True, autoincrement=True)
    title = db.Column(db.String(255), nullable=False)
    content = db.Column(db.Text, nullable=False)
    slug = db.Column(db.String(255), nullable=False, unique=True, index=True)
    
    # 公開状態
    is_published = db.Column(db.Boolean, nullable=False, default=True)
    
    # 階層構造
    parent_id = db.Column(BigInt, db.ForeignKey("wiki_page.id"), nullable=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    
    # タイムスタンプ
    created_at = db.Column(
        db.DateTime(timezone=True), 
        nullable=False, 
        default=lambda: datetime.now(timezone.utc)
    )
    updated_at = db.Column(
        db.DateTime(timezone=True), 
        nullable=False, 
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )
    
    # ユーザー関連
    created_by_id = db.Column(BigInt, db.ForeignKey("user.id"), nullable=False)
    updated_by_id = db.Column(BigInt, db.ForeignKey("user.id"), nullable=False)
    
    # リレーション
    created_by = db.relationship("User", foreign_keys=[created_by_id], backref="created_wiki_pages")
    updated_by = db.relationship("User", foreign_keys=[updated_by_id], backref="updated_wiki_pages")
    
    parent = db.relationship("WikiPage", remote_side=[id], backref="children")
    categories = db.relationship(
        "WikiCategory", 
        secondary=wiki_page_category, 
        backref="pages"
    )
    revisions = db.relationship("WikiRevision", backref="page", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<WikiPage {self.title}>"
    
    def to_dict(self):
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
    
    id = db.Column(BigInt, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    slug = db.Column(db.String(100), nullable=False, unique=True, index=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    
    created_at = db.Column(
        db.DateTime(timezone=True), 
        nullable=False, 
        default=lambda: datetime.now(timezone.utc)
    )
    
    def __repr__(self):
        return f"<WikiCategory {self.name}>"
    
    def to_dict(self):
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
    
    id = db.Column(BigInt, primary_key=True, autoincrement=True)
    page_id = db.Column(BigInt, db.ForeignKey("wiki_page.id"), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    content = db.Column(db.Text, nullable=False)
    revision_number = db.Column(db.Integer, nullable=False)
    change_summary = db.Column(db.String(500), nullable=True)
    
    created_at = db.Column(
        db.DateTime(timezone=True), 
        nullable=False, 
        default=lambda: datetime.now(timezone.utc)
    )
    created_by_id = db.Column(BigInt, db.ForeignKey("user.id"), nullable=False)
    
    # リレーション
    created_by = db.relationship("User", backref="wiki_revisions")
    
    def __repr__(self):
        return f"<WikiRevision {self.page_id} v{self.revision_number}>"
    
    def to_dict(self):
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
