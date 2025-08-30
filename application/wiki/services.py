"""
Wiki機能のアプリケーションサービス - ユースケースの実装
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
import re
from core.models.wiki.models import WikiPage, WikiCategory, WikiRevision
from infrastructure.wiki.repositories import WikiPageRepository, WikiCategoryRepository, WikiRevisionRepository
from core.models.user import User


class WikiPageService:
    """Wikiページ関連のビジネスロジック"""
    
    def __init__(self):
        self.page_repo = WikiPageRepository()
        self.revision_repo = WikiRevisionRepository()
        self.category_repo = WikiCategoryRepository()
    
    def create_page(self, title: str, content: str, user_id: int, 
                   slug: Optional[str] = None, parent_id: Optional[int] = None, 
                   category_ids: Optional[List[int]] = None) -> WikiPage:
        """新しいWikiページを作成"""
        
        # スラッグの自動生成
        if not slug:
            slug = self._generate_slug(title)
        
        # スラッグの重複チェック
        if self.page_repo.find_by_slug(slug):
            slug = self._generate_unique_slug(slug)
        
        # ページ作成
        page = WikiPage(
            title=title,
            content=content,
            slug=slug,
            parent_id=parent_id,
            created_by_id=user_id,
            updated_by_id=user_id
        )
        
        # カテゴリの設定
        if category_ids:
            categories = [self.category_repo.find_by_id(cid) for cid in category_ids]
            categories = [c for c in categories if c is not None]
            page.categories = categories
        
        # 保存
        page = self.page_repo.save(page)
        
        # 初回リビジョンを作成
        self._create_revision(page, user_id, "初期作成")
        
        return page
    
    def update_page(self, page_id: int, title: str, content: str, user_id: int,
                   change_summary: Optional[str] = None, 
                   category_ids: Optional[List[int]] = None) -> Optional[WikiPage]:
        """Wikiページを更新"""
        
        page = self.page_repo.find_by_id(page_id)
        if not page:
            return None
        
        # 変更の検出
        has_changes = (page.title != title or page.content != content)
        
        if has_changes:
            # リビジョンを作成（更新前の状態を保存）
            self._create_revision(page, user_id, change_summary or "ページ更新")
            
            # ページを更新
            page.title = title
            page.content = content
            page.updated_by_id = user_id
            page.updated_at = datetime.now(timezone.utc)
        
        # カテゴリの更新
        if category_ids is not None:
            categories = [self.category_repo.find_by_id(cid) for cid in category_ids]
            categories = [c for c in categories if c is not None]
            page.categories = categories
        
        return self.page_repo.save(page)
    
    def delete_page(self, page_id: int, user_id: int) -> bool:
        """Wikiページを削除"""
        page = self.page_repo.find_by_id(page_id)
        if not page:
            return False
        
        # 子ページがある場合は削除不可
        children = self.page_repo.find_by_parent_id(page_id)
        if children:
            return False
        
        self.page_repo.delete(page)
        return True
    
    def get_page_by_slug(self, slug: str) -> Optional[WikiPage]:
        """スラッグでページを取得"""
        return self.page_repo.find_by_slug(slug)
    
    def get_page_hierarchy(self, parent_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """ページの階層構造を取得"""
        pages = self.page_repo.find_by_parent_id(parent_id)
        result = []
        
        for page in pages:
            page_data = page.to_dict()
            page_data['children'] = self.get_page_hierarchy(page.id)
            result.append(page_data)
        
        return result
    
    def search_pages(self, query: str, limit: int = 20) -> List[WikiPage]:
        """ページを検索"""
        return self.page_repo.search_by_title(query, limit)
    
    def get_recent_pages(self, limit: int = 10) -> List[WikiPage]:
        """最近更新されたページを取得"""
        return self.page_repo.find_published_pages(limit=limit, offset=0)
    
    def get_page_revisions(self, page_id: int, limit: int = 20) -> List[WikiRevision]:
        """ページの履歴を取得"""
        return self.revision_repo.find_by_page_id(page_id, limit)
    
    def _generate_slug(self, title: str) -> str:
        """タイトルからスラッグを生成"""
        # 日本語対応の簡易スラッグ生成
        slug = re.sub(r'[^\w\s-]', '', title.lower())
        slug = re.sub(r'[-\s]+', '-', slug)
        return slug.strip('-')
    
    def _generate_unique_slug(self, base_slug: str) -> str:
        """重複しないスラッグを生成"""
        counter = 1
        while True:
            new_slug = f"{base_slug}-{counter}"
            if not self.page_repo.find_by_slug(new_slug):
                return new_slug
            counter += 1
    
    def _create_revision(self, page: WikiPage, user_id: int, summary: Optional[str]) -> WikiRevision:
        """リビジョンを作成"""
        revision_number = self.revision_repo.find_latest_revision_number(page.id) + 1
        
        revision = WikiRevision(
            page_id=page.id,
            title=page.title,
            content=page.content,
            revision_number=revision_number,
            change_summary=summary,
            created_by_id=user_id
        )
        
        return self.revision_repo.save(revision)


class WikiCategoryService:
    """Wikiカテゴリ関連のビジネスロジック"""
    
    def __init__(self):
        self.category_repo = WikiCategoryRepository()
    
    def create_category(self, name: str, description: Optional[str] = None, 
                       slug: Optional[str] = None) -> WikiCategory:
        """新しいカテゴリを作成"""
        
        if not slug:
            slug = self._generate_slug(name)
        
        # スラッグの重複チェック
        if self.category_repo.find_by_slug(slug):
            slug = self._generate_unique_slug(slug)
        
        category = WikiCategory(
            name=name,
            description=description,
            slug=slug
        )
        
        return self.category_repo.save(category)
    
    def get_all_categories(self) -> List[WikiCategory]:
        """全カテゴリを取得"""
        return self.category_repo.find_all()
    
    def get_category_by_slug(self, slug: str) -> Optional[WikiCategory]:
        """スラッグでカテゴリを取得"""
        return self.category_repo.find_by_slug(slug)
    
    def _generate_slug(self, name: str) -> str:
        """名前からスラッグを生成"""
        slug = re.sub(r'[^\w\s-]', '', name.lower())
        slug = re.sub(r'[-\s]+', '-', slug)
        return slug.strip('-')
    
    def _generate_unique_slug(self, base_slug: str) -> str:
        """重複しないスラッグを生成"""
        counter = 1
        while True:
            new_slug = f"{base_slug}-{counter}"
            if not self.category_repo.find_by_slug(new_slug):
                return new_slug
            counter += 1
