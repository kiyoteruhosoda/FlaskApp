"""Wikiアプリケーション層のユースケース"""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Optional, Sequence

from core.db import db
from core.models.photo_models import Media
from core.settings import settings

from bounded_contexts.wiki.application.dto import (
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
    WikiPageDeleteInput,
    WikiPageDeleteResult,
    WikiPageUpdateInput,
    WikiPageUpdateResult,
    WikiMediaUploadResult,
)
from bounded_contexts.wiki.application.services import WikiCategoryService, WikiPageService
from bounded_contexts.wiki.domain.commands import (
    WikiPageCommandFactory,
)
from bounded_contexts.wiki.domain.permissions import EditorContext, WikiPagePermissionService
from bounded_contexts.wiki.domain.exceptions import (
    WikiAccessDeniedError,
    WikiOperationError,
    WikiPageNotFoundError,
    WikiValidationError,
)
from webapp.config import BaseApplicationSettings
from webapp.services.upload_service import commit_uploads_to_directory


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

    def __init__(
        self,
        page_service: Optional[WikiPageService] = None,
        command_factory: Optional[WikiPageCommandFactory] = None,
    ) -> None:
        self.page_service = page_service or WikiPageService()
        self.command_factory = command_factory or WikiPageCommandFactory()

    def execute(self, data: WikiPageCreateInput) -> WikiPageCreationResult:
        command = self.command_factory.build_creation_command(
            title=data.title,
            content=data.content,
            slug=data.slug,
            parent_id=data.parent_id,
            category_ids=data.category_ids,
            author_id=data.author_id,
        )

        page = self.page_service.create_page(
            title=command.title,
            content=command.content,
            user_id=command.author_id,
            slug=command.slug,
            parent_id=command.parent_id,
            category_ids=list(command.category_ids),
        )

        return WikiPageCreationResult(page=page)


class WikiPageEditPreparationUseCase:
    """ページ編集画面用のデータを取得するユースケース"""

    def __init__(
        self,
        page_service: Optional[WikiPageService] = None,
        category_service: Optional[WikiCategoryService] = None,
        permission_service: Optional[WikiPagePermissionService] = None,
    ) -> None:
        self.page_service = page_service or WikiPageService()
        self.category_service = category_service or WikiCategoryService()
        self.permission_service = permission_service or WikiPagePermissionService()

    def execute(
        self,
        slug: str,
        user_id: int,
        has_admin_rights: bool,
    ) -> WikiPageEditContext:
        page = self.page_service.get_page_by_slug(slug)
        if not page:
            raise WikiPageNotFoundError(f"slug={slug}")

        editor = EditorContext(user_id=user_id, is_admin=has_admin_rights)
        if not self.permission_service.can_edit(page, editor):
            raise WikiAccessDeniedError("編集権限がありません")

        categories = self.category_service.get_all_categories()
        return WikiPageEditContext(page=page, categories=categories)


class WikiPageUpdateUseCase:
    """ページ更新ユースケース"""

    def __init__(
        self,
        page_service: Optional[WikiPageService] = None,
        command_factory: Optional[WikiPageCommandFactory] = None,
        permission_service: Optional[WikiPagePermissionService] = None,
    ) -> None:
        self.page_service = page_service or WikiPageService()
        self.command_factory = command_factory or WikiPageCommandFactory()
        self.permission_service = permission_service or WikiPagePermissionService()

    def execute(self, data: WikiPageUpdateInput) -> WikiPageUpdateResult:
        command = self.command_factory.build_update_command(
            slug=data.slug,
            title=data.title,
            content=data.content,
            change_summary=data.change_summary,
            category_ids=data.category_ids,
            editor_id=data.editor_id,
            has_admin_rights=data.has_admin_rights,
        )

        page = self.page_service.get_page_by_slug(command.slug)
        if not page:
            raise WikiPageNotFoundError(f"slug={command.slug}")

        editor = EditorContext(user_id=command.editor_id, is_admin=command.has_admin_rights)
        if not self.permission_service.can_edit(page, editor):
            raise WikiAccessDeniedError("編集権限がありません")

        updated_page = self.page_service.update_page(
            page_id=page.id,
            title=command.title,
            content=command.content,
            user_id=command.editor_id,
            change_summary=command.change_summary,
            category_ids=list(command.category_ids),
        )

        if not updated_page:
            raise WikiOperationError("ページの更新に失敗しました")

        return WikiPageUpdateResult(page=updated_page)


class WikiPageDeletionUseCase:
    """ページ削除ユースケース"""

    def __init__(
        self,
        page_service: Optional[WikiPageService] = None,
        command_factory: Optional[WikiPageCommandFactory] = None,
        permission_service: Optional[WikiPagePermissionService] = None,
    ) -> None:
        self.page_service = page_service or WikiPageService()
        self.command_factory = command_factory or WikiPageCommandFactory()
        self.permission_service = permission_service or WikiPagePermissionService()

    def execute(self, data: WikiPageDeleteInput) -> WikiPageDeleteResult:
        command = self.command_factory.build_delete_command(
            slug=data.slug,
            executor_id=data.executor_id,
            has_admin_rights=data.has_admin_rights,
        )

        page = self.page_service.get_page_by_slug(command.slug)
        if not page:
            raise WikiPageNotFoundError(f"slug={command.slug}")

        editor = EditorContext(user_id=command.executor_id, is_admin=command.has_admin_rights)
        if not self.permission_service.can_delete(page, editor):
            raise WikiAccessDeniedError("You do not have permission to delete this page.")

        success = self.page_service.delete_page(page.id, user_id=command.executor_id)
        if not success:
            raise WikiOperationError("page_has_children")

        return WikiPageDeleteResult(slug=page.slug)


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
        from bounded_contexts.wiki.presentation.wiki.utils import markdown_to_html

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


class WikiMediaUploadUseCase:
    """Wiki用メディアアップロードユースケース"""

    def __init__(self, destination_dir: Optional[Path | str] = None) -> None:
        self._destination_dir = Path(destination_dir) if destination_dir else None

    def execute(
        self,
        session_id: str,
        temp_file_ids: Sequence[str],
    ) -> WikiMediaUploadResult:
        file_ids = [str(item) for item in temp_file_ids]
        if not file_ids:
            return WikiMediaUploadResult(results=[], media=[])

        if self._destination_dir is not None:
            base_dir = self._destination_dir
        else:
            configured = settings.wiki_upload_directory or BaseApplicationSettings.WIKI_UPLOAD_DIRECTORY
            base_dir = Path(configured)

        try:
            base_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise WikiOperationError("Wiki media directory is not available") from exc

        try:
            resolved_base = base_dir.resolve()
        except OSError:
            resolved_base = base_dir

        results = commit_uploads_to_directory(session_id, file_ids, base_dir)

        media_entries: list[Media] = []
        for entry in results:
            if entry.get("status") != "success":
                continue

            stored_path_str = entry.get("storedPath")
            if not stored_path_str:
                continue

            stored_path = Path(stored_path_str)
            try:
                resolved_path = stored_path.resolve()
            except OSError:
                resolved_path = stored_path

            relative_path_str = entry.get("relativePath")
            if relative_path_str:
                relative_path = Path(relative_path_str)
            else:
                try:
                    relative_path = resolved_path.relative_to(resolved_base)
                except ValueError as exc:
                    raise WikiOperationError("Uploaded file stored outside wiki directory") from exc

            analysis = entry.get("analysis") or {}
            format_label = str(analysis.get("format") or "").upper()
            is_video = format_label == "VIDEO"
            guessed_mime, _ = mimetypes.guess_type(entry.get("fileName") or "")

            media = Media(
                source_type="wiki-media",
                filename=entry.get("fileName"),
                local_rel_path=relative_path.as_posix(),
                bytes=entry.get("fileSize"),
                hash_sha256=entry.get("hashSha256"),
                mime_type=guessed_mime,
                is_video=is_video,
            )

            db.session.add(media)
            media_entries.append(media)

        if not media_entries:
            return WikiMediaUploadResult(results=results, media=[])

        try:
            db.session.commit()
        except Exception as exc:  # noqa: BLE001 - 予期しないDBエラーのため
            db.session.rollback()
            raise WikiOperationError("Failed to record wiki media") from exc

        return WikiMediaUploadResult(results=results, media=media_entries)


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
    "WikiPageDeletionUseCase",
    "WikiPageSearchUseCase",
    "WikiPageUpdateUseCase",
    "WikiMediaUploadUseCase",
]
