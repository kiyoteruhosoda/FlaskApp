"""
Wiki機能のリポジトリ実装 - データアクセス層
"""

from typing import List, Optional
from sqlalchemy import desc, asc
from core.db import db
from core.models.wiki.models import WikiPage, WikiCategory, WikiRevision
from domain.wiki.entities import WikiPage as WikiPageEntity, WikiCategory as WikiCategoryEntity


class WikiPageRepository:
    """Wikiページのデータアクセス"""
    
    def find_by_id(self, page_id: int) -> Optional[WikiPage]:
        """IDでページを検索"""
        return WikiPage.query.filter_by(id=page_id).first()
    
    def find_by_slug(self, slug: str) -> Optional[WikiPage]:
        """スラッグでページを検索"""
        return WikiPage.query.filter_by(slug=slug).first()
    
    def find_published_pages(self, limit: int = 50, offset: int = 0) -> List[WikiPage]:
        """公開中のページ一覧を取得"""
        return (WikiPage.query
                .filter_by(is_published=True)
                .order_by(asc(WikiPage.sort_order), desc(WikiPage.updated_at))
                .limit(limit)
                .offset(offset)
                .all())
    
    def find_by_parent_id(self, parent_id: Optional[int]) -> List[WikiPage]:
        """親ページIDで子ページを検索"""
        return (WikiPage.query
                .filter_by(parent_id=parent_id, is_published=True)
                .order_by(asc(WikiPage.sort_order))
                .all())
    
    def find_by_category_id(self, category_id: int) -> List[WikiPage]:
        """カテゴリIDでページを検索"""
        return (WikiPage.query
                .join(WikiPage.categories)
                .filter(WikiCategory.id == category_id, WikiPage.is_published == True)
                .order_by(asc(WikiPage.sort_order), desc(WikiPage.updated_at))
                .all())
    
    def search_by_title(self, query: str, limit: int = 20) -> List[WikiPage]:
        """タイトルで検索"""
        return (WikiPage.query
                .filter(WikiPage.title.ilike(f"%{query}%"), WikiPage.is_published == True)
                .order_by(desc(WikiPage.updated_at))
                .limit(limit)
                .all())
    
    def count_published_pages(self) -> int:
        """公開中のページ数をカウント"""
        return WikiPage.query.filter_by(is_published=True).count()
    
    def save(self, page: WikiPage) -> WikiPage:
        """ページを保存"""
        db.session.add(page)
        db.session.commit()
        return page
    
    def delete(self, page: WikiPage) -> None:
        """ページを削除"""
        db.session.delete(page)
        db.session.commit()


class WikiCategoryRepository:
    """Wikiカテゴリのデータアクセス"""
    
    def find_all(self) -> List[WikiCategory]:
        """全カテゴリを取得"""
        return WikiCategory.query.order_by(asc(WikiCategory.sort_order)).all()
    
    def find_by_id(self, category_id: int) -> Optional[WikiCategory]:
        """IDでカテゴリを検索"""
        return WikiCategory.query.filter_by(id=category_id).first()
    
    def find_by_slug(self, slug: str) -> Optional[WikiCategory]:
        """スラッグでカテゴリを検索"""
        return WikiCategory.query.filter_by(slug=slug).first()
    
    def save(self, category: WikiCategory) -> WikiCategory:
        """カテゴリを保存"""
        db.session.add(category)
        db.session.commit()
        return category
    
    def delete(self, category: WikiCategory) -> None:
        """カテゴリを削除"""
        db.session.delete(category)
        db.session.commit()


class WikiRevisionRepository:
    """Wiki履歴のデータアクセス"""
    
    def find_by_page_id(self, page_id: int, limit: int = 20) -> List[WikiRevision]:
        """ページIDで履歴を取得"""
        return (WikiRevision.query
                .filter_by(page_id=page_id)
                .order_by(desc(WikiRevision.revision_number))
                .limit(limit)
                .all())
    
    def find_latest_revision_number(self, page_id: int) -> int:
        """最新のリビジョン番号を取得"""
        result = (WikiRevision.query
                 .filter_by(page_id=page_id)
                 .order_by(desc(WikiRevision.revision_number))
                 .first())
        return result.revision_number if result else 0
    
    def save(self, revision: WikiRevision) -> WikiRevision:
        """履歴を保存"""
        db.session.add(revision)
        db.session.commit()
        return revision
