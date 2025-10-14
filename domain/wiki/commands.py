"""Wikiページ操作に利用するドメインコマンドとファクトリ。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Tuple

from domain.wiki.exceptions import WikiValidationError


@dataclass(frozen=True)
class WikiPageCreationCommand:
    """ページ作成に必要な値を正規化したコマンド。"""

    title: str
    content: str
    slug: str | None
    parent_id: int | None
    category_ids: Tuple[int, ...]
    author_id: int


@dataclass(frozen=True)
class WikiPageUpdateCommand:
    """ページ更新に必要な値を正規化したコマンド。"""

    slug: str
    title: str
    content: str
    change_summary: str | None
    category_ids: Tuple[int, ...]
    editor_id: int
    has_admin_rights: bool


class WikiPageCommandFactory:
    """入力値を正規化しドメインコマンドへ変換するファクトリ。"""

    def build_creation_command(
        self,
        *,
        title: str,
        content: str,
        slug: str | None,
        parent_id: str | int | None,
        category_ids: Iterable[str | int | None],
        author_id: int,
    ) -> WikiPageCreationCommand:
        normalized_title = self._normalize_required(title, "タイトルと内容は必須です")
        normalized_content = self._normalize_required(content, "タイトルと内容は必須です")
        normalized_slug = self._normalize_slug(slug)
        normalized_parent = self._parse_optional_int(parent_id, "親ページの指定が不正です")
        normalized_categories = self._parse_category_ids(category_ids)

        return WikiPageCreationCommand(
            title=normalized_title,
            content=normalized_content,
            slug=normalized_slug,
            parent_id=normalized_parent,
            category_ids=normalized_categories,
            author_id=author_id,
        )

    def build_update_command(
        self,
        *,
        slug: str,
        title: str,
        content: str,
        change_summary: str | None,
        category_ids: Iterable[str | int | None],
        editor_id: int,
        has_admin_rights: bool,
    ) -> WikiPageUpdateCommand:
        normalized_slug = self._normalize_slug_for_lookup(slug)
        normalized_title = self._normalize_required(title, "タイトルと内容は必須です")
        normalized_content = self._normalize_required(content, "タイトルと内容は必須です")
        normalized_summary = self._normalize_optional(change_summary)
        normalized_categories = self._parse_category_ids(category_ids)

        return WikiPageUpdateCommand(
            slug=normalized_slug,
            title=normalized_title,
            content=normalized_content,
            change_summary=normalized_summary,
            category_ids=normalized_categories,
            editor_id=editor_id,
            has_admin_rights=has_admin_rights,
        )

    @staticmethod
    def _normalize_required(value: str | None, error_message: str) -> str:
        normalized = (value or "").strip()
        if not normalized:
            raise WikiValidationError(error_message)
        return normalized

    @staticmethod
    def _normalize_optional(value: str | None) -> str | None:
        normalized = (value or "").strip()
        return normalized or None

    @staticmethod
    def _normalize_slug(value: str | None) -> str | None:
        normalized = (value or "").strip()
        return normalized or None

    @staticmethod
    def _normalize_slug_for_lookup(value: str | None) -> str:
        return (value or "").strip()

    @staticmethod
    def _parse_optional_int(value: str | int | None, error_message: str) -> int | None:
        if value in (None, ""):
            return None
        try:
            return int(value)  # type: ignore[arg-type]
        except (TypeError, ValueError) as exc:  # pragma: no cover - 型安全のため
            raise WikiValidationError(error_message) from exc

    def _parse_category_ids(
        self,
        values: Iterable[str | int | None],
        error_message: str = "カテゴリの指定が不正です",
    ) -> Tuple[int, ...]:
        result: list[int] = []
        for value in values or []:
            if value in (None, ""):
                continue
            try:
                result.append(int(value))  # type: ignore[arg-type]
            except (TypeError, ValueError) as exc:
                raise WikiValidationError(error_message) from exc
        return tuple(result)


__all__ = [
    "WikiPageCommandFactory",
    "WikiPageCreationCommand",
    "WikiPageUpdateCommand",
]

