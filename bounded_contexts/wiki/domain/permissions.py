"""Wikiページに関する権限判定のドメインサービス。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from bounded_contexts.wiki.domain.entities import WikiPage as WikiPageEntity


@runtime_checkable
class SupportsWikiPage(Protocol):
    """権限判定に必要な最低限のインターフェース。"""

    created_by_id: int

    def can_be_edited_by(self, user_id: int) -> bool:  # pragma: no cover - プロトコル定義
        ...


@dataclass(frozen=True)
class EditorContext:
    """ページ編集時の利用者情報を表す値オブジェクト。"""

    user_id: int
    is_admin: bool = False

    def __post_init__(self) -> None:
        if self.user_id <= 0:
            raise ValueError("user_id must be positive")


class WikiPagePermissionService:
    """Wikiページに対する操作権限を判定するドメインサービス。"""

    def can_edit(self, page: SupportsWikiPage | WikiPageEntity, editor: EditorContext) -> bool:
        """指定したユーザーがページを編集できるか判定する。"""

        if editor.is_admin:
            return True

        if isinstance(page, WikiPageEntity):
            return page.can_be_edited_by(editor.user_id)

        if isinstance(page, SupportsWikiPage):
            can_edit = getattr(page, "can_be_edited_by", None)
            if callable(can_edit):
                return bool(can_edit(editor.user_id))

        return getattr(page, "created_by_id", None) == editor.user_id

    def can_delete(self, page: SupportsWikiPage | WikiPageEntity, editor: EditorContext) -> bool:
        """指定したユーザーがページを削除できるか判定する。"""

        return self.can_edit(page, editor)


__all__ = ["EditorContext", "WikiPagePermissionService", "SupportsWikiPage"]

