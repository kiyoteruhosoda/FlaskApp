"""Wikiアプリケーション層で利用するDTOとビューモデル"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from core.models.photo_models import Media
from core.models.wiki.models import WikiCategory, WikiPage, WikiRevision


@dataclass(frozen=True)
class WikiIndexView:
    recent_pages: List[WikiPage]
    page_hierarchy: List[Dict[str, Any]]
    categories: List[WikiCategory]


@dataclass(frozen=True)
class WikiPageDetailView:
    page: WikiPage
    children: List[Dict[str, Any]]
    categories: List[WikiCategory]
    page_hierarchy: List[Dict[str, Any]]


@dataclass(frozen=True)
class WikiPageFormPreparation:
    categories: List[WikiCategory]
    pages: List[WikiPage]


@dataclass(frozen=True)
class WikiPageCreateInput:
    title: str
    content: str
    slug: Optional[str]
    parent_id: Optional[str]
    category_ids: Sequence[str]
    author_id: int


@dataclass(frozen=True)
class WikiPageCreationResult:
    page: WikiPage


@dataclass(frozen=True)
class WikiPageEditContext:
    page: WikiPage
    categories: List[WikiCategory]


@dataclass(frozen=True)
class WikiPageUpdateInput:
    slug: str
    title: str
    content: str
    change_summary: Optional[str]
    category_ids: Sequence[str]
    editor_id: int
    has_admin_rights: bool


@dataclass(frozen=True)
class WikiPageUpdateResult:
    page: WikiPage


@dataclass(frozen=True)
class WikiPageSearchResult:
    query: str
    pages: List[WikiPage]


@dataclass(frozen=True)
class WikiCategoryDetailView:
    category: WikiCategory
    pages: List[WikiPage]


@dataclass(frozen=True)
class WikiCategoryListItem:
    category: WikiCategory
    page_count: int

    def __getattr__(self, item: str):
        return getattr(self.category, item)


@dataclass(frozen=True)
class WikiCategoryListView:
    categories: List[WikiCategoryListItem]


@dataclass(frozen=True)
class WikiAdminDashboardView:
    total_pages: int
    total_categories: int
    recent_pages: List[WikiPage]


@dataclass(frozen=True)
class WikiPageHistoryView:
    page: WikiPage
    revisions: List[WikiRevision]


@dataclass(frozen=True)
class WikiApiPagesView:
    pages: List[WikiPage]
    query: Optional[str] = None


@dataclass(frozen=True)
class WikiMarkdownPreview:
    html: str


@dataclass(frozen=True)
class WikiCategoryCreateInput:
    name: str
    description: Optional[str]
    slug: Optional[str]


@dataclass(frozen=True)
class WikiCategoryCreationResult:
    category: WikiCategory


@dataclass(frozen=True)
class WikiMediaUploadResult:
    results: List[Dict[str, Any]]
    media: List[Media]
