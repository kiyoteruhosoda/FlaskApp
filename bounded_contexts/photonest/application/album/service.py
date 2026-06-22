"""Album ユースケースの実行（アプリケーションサービス）.

入力検証・ドメイン不変条件の適用・トランザクション境界をここで完結させる。
Presentation 層は本サービスを呼び出し、結果を HTTP/JSON へ整形するだけにする。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from bounded_contexts.photonest.domain.album import (
    AlbumVisibility,
    InvalidAlbumVisibility,
    InvalidMediaSelection,
    parse_album_ids,
    parse_media_ids,
    parse_ordered_media_ids,
)

from .commands import (
    CreateAlbumCommand,
    ReorderAlbumMediaCommand,
    ReorderAlbumsCommand,
    UpdateAlbumCommand,
    is_set,
)
from .errors import AlbumApplicationError
from .repository import AlbumRepository


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AlbumApplicationService:
    """アルバムの作成・更新・並べ替え・削除ユースケース."""

    def __init__(
        self,
        repository: AlbumRepository,
        *,
        clock: Callable[[], datetime] = _utcnow,
        album_factory: Callable[..., Any] | None = None,
    ) -> None:
        self._repository = repository
        self._now = clock
        self._album_factory = album_factory

    def _new_album(self, **fields: Any) -> Any:
        if self._album_factory is not None:
            return self._album_factory(**fields)
        from bounded_contexts.photonest.infrastructure.photo_models import Album

        return Album(**fields)

    # ------------------------------------------------------------------ create
    def create(self, command: CreateAlbumCommand) -> Any:
        """新しいアルバムを作成し、永続化済みエンティティを返す."""
        name = (command.name or "").strip()
        if not name:
            raise AlbumApplicationError.name_required()

        description = (command.description or "").strip() or None
        visibility = self._parse_visibility(command.visibility or "private")
        media_ids = self._parse_media_ids(command.media_ids)
        cover_media_id = self._parse_optional_cover(command.cover_media_id)

        ordered_media = self._load_media_or_fail(media_ids)
        self._ensure_cover_within_selection(cover_media_id, media_ids)

        now = self._now()
        album = self._new_album(
            name=name,
            description=description,
            visibility=visibility.value,
            cover_media_id=cover_media_id,
            created_at=now,
            updated_at=now,
        )
        self._repository.add(album)
        self._repository.flush()

        self._repository.replace_media(album, ordered_media)
        self._repository.update_sort_indexes(album.id, media_ids)

        if not album.cover_media_id and media_ids:
            album.cover_media_id = media_ids[0]
        album.updated_at = now

        self._repository.commit()
        return album

    # ------------------------------------------------------------------ update
    def update(self, command: UpdateAlbumCommand) -> tuple[Any, bool]:
        """アルバムを部分更新し、(エンティティ, 変更有無) を返す."""
        album = self._get_or_fail(command.album_id)
        has_changes = False

        if isinstance(command.name, str):
            stripped = command.name.strip()
            if not stripped:
                raise AlbumApplicationError.name_required()
            if stripped != album.name:
                album.name = stripped
                has_changes = True

        if isinstance(command.description, str):
            normalized = command.description.strip() or None
            if normalized != album.description:
                album.description = normalized
                has_changes = True

        if isinstance(command.visibility, str):
            visibility = self._parse_visibility(command.visibility)
            if visibility.value != album.visibility:
                album.visibility = visibility.value
                has_changes = True

        if self._provides_media(command.media_ids):
            media_ids = self._parse_media_ids(command.media_ids)
            ordered_media = self._load_media_or_fail(media_ids)
            self._repository.replace_media(album, ordered_media)
            self._repository.update_sort_indexes(album.id, media_ids)
            has_changes = True
            current_media_ids = media_ids
        else:
            current_media_ids = [media.id for media in album.media]

        if album.cover_media_id and album.cover_media_id not in current_media_ids:
            album.cover_media_id = current_media_ids[0] if current_media_ids else None
            has_changes = True

        if is_set(command.cover_media_id):
            cover_media_id = self._parse_optional_cover(command.cover_media_id)
            self._ensure_cover_within_selection(cover_media_id, current_media_ids)
            if cover_media_id != album.cover_media_id:
                album.cover_media_id = cover_media_id
                has_changes = True

        if not album.cover_media_id and current_media_ids:
            album.cover_media_id = current_media_ids[0]

        if has_changes:
            album.updated_at = self._now()

        self._repository.commit()
        return album, has_changes

    # ----------------------------------------------------------- reorder media
    def reorder_media(self, command: ReorderAlbumMediaCommand) -> tuple[Any, bool]:
        """アルバム内メディアの並び順を更新し、(エンティティ, 変更有無) を返す."""
        album = self._get_or_fail(command.album_id)

        raw = command.media_ids
        if not isinstance(raw, list):
            raise AlbumApplicationError.media_order_not_list()

        try:
            normalized_ids = parse_ordered_media_ids(raw)
        except InvalidMediaSelection as exc:
            raise AlbumApplicationError.media_order_not_unique() from exc

        current_media_ids = [media.id for media, _ in self._repository.media_rows(command.album_id)]

        if not normalized_ids:
            if current_media_ids:
                raise AlbumApplicationError.media_order_mismatch()
            return album, False

        if (
            len(normalized_ids) != len(current_media_ids)
            or set(normalized_ids) != set(current_media_ids)
        ):
            raise AlbumApplicationError.media_order_mismatch()

        if normalized_ids == current_media_ids:
            return album, False

        self._repository.update_sort_indexes(album.id, normalized_ids)
        album.updated_at = self._now()
        self._repository.commit()
        return album, True

    # ---------------------------------------------------------- reorder albums
    def reorder_albums(self, command: ReorderAlbumsCommand) -> tuple[list[int], bool]:
        """アルバムの表示順を更新し、(正規化済みID列, 変更有無) を返す."""
        raw = command.album_ids
        if not isinstance(raw, list) or not raw:
            raise AlbumApplicationError.album_order_empty()

        try:
            normalized_ids = parse_album_ids(raw)
        except InvalidMediaSelection as exc:
            raise AlbumApplicationError.album_order_not_integer() from exc

        if not normalized_ids:
            raise AlbumApplicationError.album_order_empty()

        album_by_id = {album.id: album for album in self._repository.get_many(normalized_ids)}
        missing = [album_id for album_id in normalized_ids if album_id not in album_by_id]
        if missing:
            raise AlbumApplicationError.albums_not_found(missing)

        now = self._now()
        updated_count = 0
        for index, album_id in enumerate(normalized_ids):
            album = album_by_id[album_id]
            if album.display_order != index:
                album.display_order = index
                album.updated_at = now
                updated_count += 1

        if updated_count:
            self._repository.commit()
        else:
            self._repository.rollback()

        return normalized_ids, bool(updated_count)

    # ------------------------------------------------------------------ delete
    def delete(self, album_id: int) -> None:
        """アルバムを削除する."""
        album = self._get_or_fail(album_id)
        self._repository.delete(album)
        self._repository.commit()

    # --------------------------------------------------------------- internals
    def _get_or_fail(self, album_id: int) -> Any:
        album = self._repository.get(album_id)
        if not album:
            raise AlbumApplicationError.album_not_found()
        return album

    @staticmethod
    def _parse_visibility(raw: str) -> AlbumVisibility:
        try:
            return AlbumVisibility.parse(raw)
        except InvalidAlbumVisibility as exc:
            raise AlbumApplicationError.invalid_visibility() from exc

    @staticmethod
    def _parse_media_ids(raw: object) -> list[int]:
        try:
            return parse_media_ids(raw)
        except InvalidMediaSelection as exc:
            raise AlbumApplicationError.invalid_media_ids() from exc

    @staticmethod
    def _provides_media(raw: object) -> bool:
        # 更新では「キー不在(UNSET)」または「明示的 null」は変更対象外。
        return is_set(raw) and raw is not None

    @staticmethod
    def _parse_optional_cover(raw: object) -> int | None:
        if not is_set(raw) or raw in (None, ""):
            return None
        try:
            return int(raw)
        except (TypeError, ValueError) as exc:
            raise AlbumApplicationError.cover_not_integer() from exc

    def _load_media_or_fail(self, media_ids: list[int]) -> list[Any]:
        ordered_media, missing_ids = self._repository.load_ordered_media(media_ids)
        if missing_ids:
            raise AlbumApplicationError.media_not_found(missing_ids)
        return ordered_media

    @staticmethod
    def _ensure_cover_within_selection(cover_media_id: int | None, media_ids: list[int]) -> None:
        if cover_media_id and cover_media_id not in media_ids:
            raise AlbumApplicationError.cover_not_in_selection()


__all__ = ["AlbumApplicationService"]
