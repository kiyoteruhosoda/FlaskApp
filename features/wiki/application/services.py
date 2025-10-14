"""Wiki機能のアプリケーションサービス - ユースケースの実装"""

from typing import List, Optional, Dict, Any, Callable
from datetime import datetime, timezone
from core.models.wiki.models import WikiPage, WikiCategory, WikiRevision
from features.wiki.infrastructure.repositories import (
    WikiPageRepository,
    WikiCategoryRepository,
    WikiRevisionRepository,
)
from features.wiki.domain.slug import SlugService


class WikiPageService:
    """Wikiページ関連のビジネスロジック"""
    
    def __init__(
        self,
        page_repo: WikiPageRepository | None = None,
        revision_repo: WikiRevisionRepository | None = None,
        category_repo: WikiCategoryRepository | None = None,
        slug_service: SlugService | None = None,
    ) -> None:
        self.page_repo = page_repo or WikiPageRepository()
        self.revision_repo = revision_repo or WikiRevisionRepository()
        self.category_repo = category_repo or WikiCategoryRepository()
        self.slug_service = slug_service or SlugService()
    
    def create_page(self, title: str, content: str, user_id: int, 
                   slug: Optional[str] = None, parent_id: Optional[int] = None, 
                   category_ids: Optional[List[int]] = None) -> WikiPage:
        """新しいWikiページを作成"""
        
        exists: Callable[[str], bool] = lambda candidate: self.page_repo.find_by_slug(candidate) is not None

        if slug:
            try:
                slug_candidate = self.slug_service.from_user_input(slug)
            except ValueError:
                try:
                    slug_candidate = self.slug_service.generate_from_text(slug)
                except ValueError:
                    slug_candidate = self.slug_service.generate_from_text(title)
            slug_value = self.slug_service.ensure_unique(
                slug_candidate,
                exists,
            ).value
        else:
            try:
                slug_value = self.slug_service.generate_unique_from_text(title, exists).value
            except ValueError:
                slug_value = self.slug_service.ensure_unique(
                    self.slug_service.from_user_input("page"),
                    exists,
                ).value

        # ページ作成
        page = WikiPage(
            title=title,
            content=content,
            slug=slug_value,
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

    def get_pages_by_category(self, category_id: int) -> List[WikiPage]:
        """カテゴリに紐づく公開済みページを取得"""
        return self.page_repo.find_by_category_id(category_id)

    def count_published_pages(self) -> int:
        """公開中のページ数を取得"""
        return self.page_repo.count_published_pages()

    def get_page_revisions(self, page_id: int, limit: int = 20) -> List[WikiRevision]:
        """ページの履歴を取得"""
        return self.revision_repo.find_by_page_id(page_id, limit)
    
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
    
    def __init__(
        self,
        category_repo: WikiCategoryRepository | None = None,
        slug_service: SlugService | None = None,
    ) -> None:
        self.category_repo = category_repo or WikiCategoryRepository()
        self.slug_service = slug_service or SlugService()
    
    def create_category(self, name: str, description: Optional[str] = None, 
                       slug: Optional[str] = None) -> WikiCategory:
        """新しいカテゴリを作成"""
        
        exists: Callable[[str], bool] = lambda candidate: self.category_repo.find_by_slug(candidate) is not None

        if slug:
            try:
                slug_candidate = self.slug_service.from_user_input(slug)
            except ValueError:
                try:
                    slug_candidate = self.slug_service.generate_from_text(slug)
                except ValueError:
                    slug_candidate = self.slug_service.generate_from_text(name)
            slug_value = self.slug_service.ensure_unique(
                slug_candidate,
                exists,
            ).value
        else:
            try:
                slug_value = self.slug_service.generate_unique_from_text(name, exists).value
            except ValueError:
                slug_value = self.slug_service.ensure_unique(
                    self.slug_service.from_user_input("category"),
                    exists,
                ).value

        category = WikiCategory(
            name=name,
            description=description,
            slug=slug_value
        )

        return self.category_repo.save(category)
    
    def get_all_categories(self) -> List[WikiCategory]:
        """全カテゴリを取得"""
        return self.category_repo.find_all()
    
    def get_category_by_slug(self, slug: str) -> Optional[WikiCategory]:
        """スラッグでカテゴリを取得"""
        return self.category_repo.find_by_slug(slug)
    
