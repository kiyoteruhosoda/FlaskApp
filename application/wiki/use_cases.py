"""Wikiアプリケーション層のユースケース"""

from __future__ import annotations

from typing import Optional

from application.wiki.dto import (
    WikiAdminDashboardView,
    WikiApiPagesView,
    WikiCategoryDetailView,
    WikiCategoryListItem,
    WikiCategoryListView,
    WikiCategoryCreateInput,
    WikiCategoryCreationResult,
    WikiIndexView,
    WikiMarkdownPreview,
    WikiPageCreateInput,
    WikiPageCreationResult,
    WikiPageDetailView,
    WikiPageEditContext,
    WikiPageFormPreparation,
    WikiPageHistoryView,
    WikiPageSearchResult,
    WikiPageUpdateInput,
    WikiPageUpdateResult,
)
from application.wiki.services import WikiCategoryService, WikiPageService
from domain.wiki.exceptions import (
    WikiAccessDeniedError,
    WikiOperationError,
    WikiPageNotFoundError,
    WikiValidationError,
)


class WikiIndexUseCase:
    """Wikiトップページ表示ユースケース"""

    def __init__(
        self,
        page_service: Optional[WikiPageService] = None,
        category_service: Optional[WikiCategoryService] = None,
    ) -> None:
        self.page_service = page_service or WikiPageService()
        self.category_service = category_service or WikiCategoryService()

    def execute(self) -> WikiIndexView:
        recent_pages = self.page_service.get_recent_pages(limit=10)
        page_hierarchy = self.page_service.get_page_hierarchy()
        categories = self.category_service.get_all_categories()
        return WikiIndexView(
            recent_pages=recent_pages,
            page_hierarchy=page_hierarchy,
            categories=categories,
        )


class WikiPageDetailUseCase:
    """Wikiページ詳細表示ユースケース"""

    def __init__(
        self,
        page_service: Optional[WikiPageService] = None,
        category_service: Optional[WikiCategoryService] = None,
    ) -> None:
        self.page_service = page_service or WikiPageService()
        self.category_service = category_service or WikiCategoryService()

    def execute(self, slug: str) -> WikiPageDetailView:
        page = self.page_service.get_page_by_slug(slug)
        if not page or not page.is_published:
            raise WikiPageNotFoundError(f"slug={slug}")

        children = self.page_service.get_page_hierarchy(page.id)
        categories = self.category_service.get_all_categories()
        page_hierarchy = self.page_service.get_page_hierarchy()

        return WikiPageDetailView(
            page=page,
            children=children,
            categories=categories,
            page_hierarchy=page_hierarchy,
        )


class WikiPageFormPreparationUseCase:
    """ページ作成フォーム表示用ユースケース"""

    def __init__(
        self,
        page_service: Optional[WikiPageService] = None,
        category_service: Optional[WikiCategoryService] = None,
    ) -> None:
        self.page_service = page_service or WikiPageService()
        self.category_service = category_service or WikiCategoryService()

    def execute(self) -> WikiPageFormPreparation:
        categories = self.category_service.get_all_categories()
        pages = self.page_service.get_recent_pages(limit=50)
        return WikiPageFormPreparation(categories=categories, pages=pages)


class WikiPageCreationUseCase:
    """Wikiページ作成ユースケース"""

    def __init__(self, page_service: Optional[WikiPageService] = None) -> None:
        self.page_service = page_service or WikiPageService()

    def execute(self, data: WikiPageCreateInput) -> WikiPageCreationResult:
        title = (data.title or "").strip()
        content = (data.content or "").strip()
        slug = (data.slug or "").strip() or None

        if not title or not content:
            raise WikiValidationError("タイトルと内容は必須です")

        try:
            parent_id = int(data.parent_id) if data.parent_id else None
        except (TypeError, ValueError) as exc:
            raise WikiValidationError("親ページの指定が不正です") from exc

        try:
            category_ids = [int(cid) for cid in data.category_ids if cid]
        except ValueError as exc:
            raise WikiValidationError("カテゴリの指定が不正です") from exc

        page = self.page_service.create_page(
            title=title,
            content=content,
            user_id=data.author_id,
            slug=slug,
            parent_id=parent_id,
            category_ids=category_ids,
        )

        return WikiPageCreationResult(page=page)


class WikiPageEditPreparationUseCase:
    """ページ編集画面用のデータを取得するユースケース"""

    def __init__(
        self,
        page_service: Optional[WikiPageService] = None,
        category_service: Optional[WikiCategoryService] = None,
    ) -> None:
        self.page_service = page_service or WikiPageService()
        self.category_service = category_service or WikiCategoryService()

    def execute(
        self,
        slug: str,
        user_id: int,
        has_admin_rights: bool,
    ) -> WikiPageEditContext:
        page = self.page_service.get_page_by_slug(slug)
        if not page:
            raise WikiPageNotFoundError(f"slug={slug}")

        if not self._can_edit(page.created_by_id, user_id, has_admin_rights):
            raise WikiAccessDeniedError("編集権限がありません")

        categories = self.category_service.get_all_categories()
        return WikiPageEditContext(page=page, categories=categories)

    @staticmethod
    def _can_edit(page_owner_id: int, user_id: int, has_admin_rights: bool) -> bool:
        return page_owner_id == user_id or has_admin_rights


class WikiPageUpdateUseCase:
    """ページ更新ユースケース"""

    def __init__(self, page_service: Optional[WikiPageService] = None) -> None:
        self.page_service = page_service or WikiPageService()

    def execute(self, data: WikiPageUpdateInput) -> WikiPageUpdateResult:
        page = self.page_service.get_page_by_slug(data.slug)
        if not page:
            raise WikiPageNotFoundError(f"slug={data.slug}")

        if not self._can_edit(page.created_by_id, data.editor_id, data.has_admin_rights):
            raise WikiAccessDeniedError("編集権限がありません")

        title = (data.title or "").strip()
        content = (data.content or "").strip()
        if not title or not content:
            raise WikiValidationError("タイトルと内容は必須です")

        change_summary = (data.change_summary or "").strip() or None

        try:
            category_ids = [int(cid) for cid in data.category_ids if cid]
        except ValueError as exc:
            raise WikiValidationError("カテゴリの指定が不正です") from exc

        updated_page = self.page_service.update_page(
            page_id=page.id,
            title=title,
            content=content,
            user_id=data.editor_id,
            change_summary=change_summary,
            category_ids=category_ids,
        )

        if not updated_page:
            raise WikiOperationError("ページの更新に失敗しました")

        return WikiPageUpdateResult(page=updated_page)

    @staticmethod
    def _can_edit(page_owner_id: int, user_id: int, has_admin_rights: bool) -> bool:
        return page_owner_id == user_id or has_admin_rights


class WikiPageSearchUseCase:
    """Wikiページ検索ユースケース"""

    def __init__(self, page_service: Optional[WikiPageService] = None) -> None:
        self.page_service = page_service or WikiPageService()

    def execute(self, query: str, limit: int = 50) -> WikiPageSearchResult:
        normalized_query = (query or "").strip()
        if not normalized_query:
            return WikiPageSearchResult(query="", pages=[])

        pages = self.page_service.search_pages(normalized_query, limit=limit)
        return WikiPageSearchResult(query=normalized_query, pages=pages)


class WikiCategoryDetailUseCase:
    """カテゴリ詳細表示ユースケース"""

    def __init__(
        self,
        page_service: Optional[WikiPageService] = None,
        category_service: Optional[WikiCategoryService] = None,
    ) -> None:
        self.page_service = page_service or WikiPageService()
        self.category_service = category_service or WikiCategoryService()

    def execute(self, slug: str) -> WikiCategoryDetailView:
        category = self.category_service.get_category_by_slug(slug)
        if not category:
            raise WikiPageNotFoundError(f"category={slug}")

        pages = self.page_service.get_pages_by_category(category.id)
        return WikiCategoryDetailView(category=category, pages=pages)


class WikiCategoryListUseCase:
    """カテゴリ一覧ユースケース"""

    def __init__(
        self,
        page_service: Optional[WikiPageService] = None,
        category_service: Optional[WikiCategoryService] = None,
    ) -> None:
        self.page_service = page_service or WikiPageService()
        self.category_service = category_service or WikiCategoryService()

    def execute(self) -> WikiCategoryListView:
        categories = self.category_service.get_all_categories()
        items: list[WikiCategoryListItem] = []
        for category in categories:
            pages = self.page_service.get_pages_by_category(category.id)
            items.append(WikiCategoryListItem(category=category, page_count=len(pages)))
        return WikiCategoryListView(categories=items)


class WikiAdminDashboardUseCase:
    """Wiki管理ダッシュボード用ユースケース"""

    def __init__(
        self,
        page_service: Optional[WikiPageService] = None,
        category_service: Optional[WikiCategoryService] = None,
    ) -> None:
        self.page_service = page_service or WikiPageService()
        self.category_service = category_service or WikiCategoryService()

    def execute(self) -> WikiAdminDashboardView:
        total_pages = self.page_service.count_published_pages()
        total_categories = len(self.category_service.get_all_categories())
        recent_pages = self.page_service.get_recent_pages(limit=5)
        return WikiAdminDashboardView(
            total_pages=total_pages,
            total_categories=total_categories,
            recent_pages=recent_pages,
        )


class WikiPageHistoryUseCase:
    """Wikiページ履歴表示ユースケース"""

    def __init__(self, page_service: Optional[WikiPageService] = None) -> None:
        self.page_service = page_service or WikiPageService()

    def execute(self, slug: str, limit: int = 50) -> WikiPageHistoryView:
        page = self.page_service.get_page_by_slug(slug)
        if not page:
            raise WikiPageNotFoundError(f"slug={slug}")

        revisions = self.page_service.get_page_revisions(page.id, limit=limit)
        return WikiPageHistoryView(page=page, revisions=revisions)


class WikiApiPagesUseCase:
    """API用のページ一覧取得ユースケース"""

    def __init__(self, page_service: Optional[WikiPageService] = None) -> None:
        self.page_service = page_service or WikiPageService()

    def execute(self, limit: int = 100) -> WikiApiPagesView:
        pages = self.page_service.get_recent_pages(limit=limit)
        return WikiApiPagesView(pages=pages)


class WikiApiSearchUseCase:
    """API検索ユースケース"""

    def __init__(self, page_service: Optional[WikiPageService] = None) -> None:
        self.page_service = page_service or WikiPageService()

    def execute(self, query: str, limit: int = 20) -> WikiApiPagesView:
        normalized_query = (query or "").strip()
        if not normalized_query:
            return WikiApiPagesView(pages=[], query="")

        pages = self.page_service.search_pages(normalized_query, limit=limit)
        return WikiApiPagesView(pages=pages, query=normalized_query)


class WikiMarkdownPreviewUseCase:
    """Markdownプレビュー生成ユースケース"""

    def execute(self, content: str) -> WikiMarkdownPreview:
        from webapp.wiki.utils import markdown_to_html

        html = markdown_to_html(content)
        return WikiMarkdownPreview(html=str(html))


class WikiCategoryCreationUseCase:
    """カテゴリ作成ユースケース"""

    def __init__(self, category_service: Optional[WikiCategoryService] = None) -> None:
        self.category_service = category_service or WikiCategoryService()

    def execute(self, data: WikiCategoryCreateInput) -> WikiCategoryCreationResult:
        name = (data.name or "").strip()
        if not name:
            raise WikiValidationError("カテゴリ名は必須です")

        description = (data.description or "").strip() or None
        slug = (data.slug or "").strip() or None

        category = self.category_service.create_category(
            name=name,
            description=description,
            slug=slug,
        )

        return WikiCategoryCreationResult(category=category)


__all__ = [
    "WikiAdminDashboardUseCase",
    "WikiApiPagesUseCase",
    "WikiApiSearchUseCase",
    "WikiCategoryDetailUseCase",
    "WikiCategoryCreationUseCase",
    "WikiCategoryListUseCase",
    "WikiIndexUseCase",
    "WikiMarkdownPreviewUseCase",
    "WikiPageCreationUseCase",
    "WikiPageDetailUseCase",
    "WikiPageEditPreparationUseCase",
    "WikiPageFormPreparationUseCase",
    "WikiPageHistoryUseCase",
    "WikiPageSearchUseCase",
    "WikiPageUpdateUseCase",
]
