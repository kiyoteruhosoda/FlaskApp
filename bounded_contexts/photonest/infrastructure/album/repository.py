"""``AlbumRepository`` の SQLAlchemy 実装.

クエリ最適化やセッション操作といった技術的詳細はこの層に閉じ込める。
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import joinedload

from bounded_contexts.photonest.application.album.repository import AlbumRepository
from core.models.photo_models import Album, Media, album_item


class SqlAlchemyAlbumRepository(AlbumRepository):
    """Flask-SQLAlchemy のセッションを用いた Album リポジトリ."""

    def __init__(self, session: Any) -> None:
        self._session = session

    def get(self, album_id: int) -> Album | None:
        return self._session.get(Album, album_id)

    def get_many(self, album_ids: list[int]) -> list[Album]:
        if not album_ids:
            return []
        return Album.query.filter(Album.id.in_(album_ids)).all()

    def add(self, album: Album) -> None:
        self._session.add(album)

    def delete(self, album: Album) -> None:
        self._session.delete(album)

    def load_ordered_media(self, media_ids: list[int]) -> tuple[list[Media], list[int]]:
        if not media_ids:
            return [], []

        medias = Media.query.filter(Media.id.in_(media_ids)).all()
        media_by_id = {media.id: media for media in medias}

        ordered: list[Media] = []
        missing: list[int] = []
        for media_id in media_ids:
            media = media_by_id.get(media_id)
            if media is None:
                missing.append(media_id)
            else:
                ordered.append(media)
        return ordered, missing

    def replace_media(self, album: Album, ordered_media: list[Media]) -> None:
        album.media = ordered_media
        self._session.flush()

    def update_sort_indexes(self, album_id: int, media_ids: list[int]) -> None:
        if not media_ids:
            return
        for position, media_id in enumerate(media_ids):
            self._session.execute(
                album_item.update()
                .where(
                    album_item.c.album_id == album_id,
                    album_item.c.media_id == media_id,
                )
                .values(sort_index=position)
            )

    def media_rows(self, album_id: int) -> list[tuple[Media, int]]:
        return (
            self._session.query(Media, album_item.c.sort_index)
            .join(album_item, album_item.c.media_id == Media.id)
            .filter(album_item.c.album_id == album_id)
            .options(joinedload(Media.tags))
            .order_by(album_item.c.sort_index.asc(), Media.id.asc())
            .all()
        )

    def flush(self) -> None:
        self._session.flush()

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()


__all__ = ["SqlAlchemyAlbumRepository"]
