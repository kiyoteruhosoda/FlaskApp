"""AlbumApplicationService のユースケース結合テスト（テスト用リポジトリ使用）.

時刻は固定し、DB・Flask には一切依存しない。
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from bounded_contexts.photonest.application.album import (
    AlbumApplicationError,
    AlbumApplicationService,
    CreateAlbumCommand,
    ReorderAlbumMediaCommand,
    ReorderAlbumsCommand,
    UpdateAlbumCommand,
)
from bounded_contexts.photonest.application.album.commands import UNSET
from bounded_contexts.photonest.application.album.repository import AlbumRepository

FIXED_NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def _media(media_id: int) -> SimpleNamespace:
    return SimpleNamespace(id=media_id)


def _album(album_id: int, **attrs) -> SimpleNamespace:
    defaults = dict(
        id=album_id,
        name="Album",
        description=None,
        visibility="private",
        cover_media_id=None,
        display_order=None,
        media=[],
        created_at=FIXED_NOW,
        updated_at=FIXED_NOW,
    )
    defaults.update(attrs)
    return SimpleNamespace(**defaults)


class FakeAlbumRepository(AlbumRepository):
    """挙動を観測できるメモリ実装."""

    def __init__(self, *, albums=None, existing_media_ids=None):
        self._albums = {album.id: album for album in (albums or [])}
        self._existing_media_ids = set(existing_media_ids or [])
        self.committed = False
        self.rolled_back = False
        self.sort_index_calls: list[tuple[int, list[int]]] = []
        self.deleted: list[object] = []
        self._next_id = 1000

    # 読み取り
    def get(self, album_id):
        return self._albums.get(album_id)

    def get_many(self, album_ids):
        return [self._albums[a] for a in album_ids if a in self._albums]

    def load_ordered_media(self, media_ids):
        ordered, missing = [], []
        for media_id in media_ids:
            if media_id in self._existing_media_ids:
                ordered.append(_media(media_id))
            else:
                missing.append(media_id)
        return ordered, missing

    def media_rows(self, album_id):
        album = self._albums[album_id]
        return [(media, index) for index, media in enumerate(album.media)]

    # 書き込み
    def add(self, album):
        self._albums[album.id if album.id is not None else self._next_id] = album

    def delete(self, album):
        self.deleted.append(album)
        self._albums.pop(album.id, None)

    def replace_media(self, album, ordered_media):
        album.media = list(ordered_media)

    def update_sort_indexes(self, album_id, media_ids):
        self.sort_index_calls.append((album_id, list(media_ids)))

    def flush(self):
        pass

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


def _service(repo: FakeAlbumRepository) -> AlbumApplicationService:
    return AlbumApplicationService(
        repo,
        clock=lambda: FIXED_NOW,
        album_factory=lambda **fields: SimpleNamespace(id=1, media=[], **fields),
    )


# --------------------------------------------------------------------- create
class TestCreate:
    def test_creates_album_and_sets_first_media_as_cover(self):
        repo = FakeAlbumRepository(existing_media_ids={10, 20})
        album = _service(repo).create(
            CreateAlbumCommand(name="Trip", media_ids=[20, 10])
        )

        assert album.name == "Trip"
        assert album.visibility == "private"
        assert album.cover_media_id == 20
        assert [m.id for m in album.media] == [20, 10]
        assert repo.sort_index_calls == [(1, [20, 10])]
        assert repo.committed is True

    def test_blank_name_is_rejected(self):
        repo = FakeAlbumRepository()
        with pytest.raises(AlbumApplicationError) as exc:
            _service(repo).create(CreateAlbumCommand(name="   "))
        assert exc.value.code == "name_required"
        assert repo.committed is False

    def test_unknown_visibility_is_rejected(self):
        repo = FakeAlbumRepository()
        with pytest.raises(AlbumApplicationError) as exc:
            _service(repo).create(CreateAlbumCommand(name="A", visibility="secret"))
        assert exc.value.code == "invalid_visibility"

    def test_missing_media_reports_missing_ids(self):
        repo = FakeAlbumRepository(existing_media_ids={1})
        with pytest.raises(AlbumApplicationError) as exc:
            _service(repo).create(CreateAlbumCommand(name="A", media_ids=[1, 2, 3]))
        assert exc.value.code == "invalid_media"
        assert exc.value.details == {"missingMediaIds": [2, 3]}

    def test_cover_must_be_within_selection(self):
        repo = FakeAlbumRepository(existing_media_ids={1, 2})
        with pytest.raises(AlbumApplicationError) as exc:
            _service(repo).create(
                CreateAlbumCommand(name="A", media_ids=[1, 2], cover_media_id=99)
            )
        assert exc.value.code == "invalid_cover"


# --------------------------------------------------------------------- update
class TestUpdate:
    def test_partial_rename_marks_changed(self):
        repo = FakeAlbumRepository(albums=[_album(1, name="Old")])
        album, changed = _service(repo).update(UpdateAlbumCommand(album_id=1, name="New"))
        assert changed is True
        assert album.name == "New"
        assert album.updated_at == FIXED_NOW

    def test_no_op_update_keeps_changed_false(self):
        repo = FakeAlbumRepository(albums=[_album(1, name="Same")])
        _, changed = _service(repo).update(UpdateAlbumCommand(album_id=1, name="Same"))
        assert changed is False

    def test_missing_album_raises_not_found(self):
        repo = FakeAlbumRepository()
        with pytest.raises(AlbumApplicationError) as exc:
            _service(repo).update(UpdateAlbumCommand(album_id=404, name="x"))
        assert exc.value.code == "not_found"
        assert exc.value.status == 404

    def test_clearing_media_clears_cover(self):
        # mediaIds=[] は「空配列が来た」= 全削除（route の `is not None` と同じ挙動）。
        album = _album(1, cover_media_id=5, media=[_media(5)])
        repo = FakeAlbumRepository(albums=[album], existing_media_ids=set())
        updated, changed = _service(repo).update(
            UpdateAlbumCommand(album_id=1, media_ids=[])
        )
        assert changed is True
        assert updated.media == []
        assert updated.cover_media_id is None

    def test_absent_media_key_leaves_album_untouched(self):
        # mediaIds キー自体が無い（UNSET）場合は収録メディアを変更しない。
        album = _album(1, cover_media_id=5, media=[_media(5)])
        repo = FakeAlbumRepository(albums=[album])
        updated, changed = _service(repo).update(UpdateAlbumCommand(album_id=1))
        assert changed is False
        assert [m.id for m in updated.media] == [5]
        assert updated.cover_media_id == 5

    def test_replacing_media_reassigns_cover_when_invalid(self):
        album = _album(1, cover_media_id=99, media=[_media(99)])
        repo = FakeAlbumRepository(albums=[album], existing_media_ids={7, 8})
        updated, changed = _service(repo).update(
            UpdateAlbumCommand(album_id=1, media_ids=[7, 8])
        )
        assert changed is True
        assert [m.id for m in updated.media] == [7, 8]
        assert updated.cover_media_id == 7


# -------------------------------------------------------------- reorder media
class TestReorderMedia:
    def test_reorders_and_commits(self):
        album = _album(1, media=[_media(1), _media(2), _media(3)])
        repo = FakeAlbumRepository(albums=[album])
        _, updated = _service(repo).reorder_media(
            ReorderAlbumMediaCommand(album_id=1, media_ids=[3, 1, 2])
        )
        assert updated is True
        assert repo.sort_index_calls == [(1, [3, 1, 2])]
        assert repo.committed is True

    def test_same_order_is_noop(self):
        album = _album(1, media=[_media(1), _media(2)])
        repo = FakeAlbumRepository(albums=[album])
        _, updated = _service(repo).reorder_media(
            ReorderAlbumMediaCommand(album_id=1, media_ids=[1, 2])
        )
        assert updated is False
        assert repo.committed is False

    def test_payload_must_match_album_membership(self):
        album = _album(1, media=[_media(1), _media(2)])
        repo = FakeAlbumRepository(albums=[album])
        with pytest.raises(AlbumApplicationError) as exc:
            _service(repo).reorder_media(
                ReorderAlbumMediaCommand(album_id=1, media_ids=[1, 99])
            )
        assert exc.value.code == "invalid_media_order"

    def test_non_list_payload_rejected(self):
        repo = FakeAlbumRepository(albums=[_album(1)])
        with pytest.raises(AlbumApplicationError) as exc:
            _service(repo).reorder_media(
                ReorderAlbumMediaCommand(album_id=1, media_ids="nope")
            )
        assert exc.value.code == "invalid_media_order"


# ------------------------------------------------------------- reorder albums
class TestReorderAlbums:
    def test_updates_display_order(self):
        repo = FakeAlbumRepository(
            albums=[_album(1, display_order=0), _album(2, display_order=1)]
        )
        ids, updated = _service(repo).reorder_albums(
            ReorderAlbumsCommand(album_ids=[2, 1])
        )
        assert ids == [2, 1]
        assert updated is True
        assert repo.get(2).display_order == 0
        assert repo.get(1).display_order == 1
        assert repo.committed is True

    def test_no_change_rolls_back(self):
        repo = FakeAlbumRepository(
            albums=[_album(1, display_order=0), _album(2, display_order=1)]
        )
        _, updated = _service(repo).reorder_albums(ReorderAlbumsCommand(album_ids=[1, 2]))
        assert updated is False
        assert repo.rolled_back is True
        assert repo.committed is False

    def test_empty_payload_rejected(self):
        repo = FakeAlbumRepository()
        with pytest.raises(AlbumApplicationError) as exc:
            _service(repo).reorder_albums(ReorderAlbumsCommand(album_ids=[]))
        assert exc.value.code == "invalid_payload"

    def test_missing_albums_reported(self):
        repo = FakeAlbumRepository(albums=[_album(1)])
        with pytest.raises(AlbumApplicationError) as exc:
            _service(repo).reorder_albums(ReorderAlbumsCommand(album_ids=[1, 2]))
        assert exc.value.code == "invalid_album"
        assert exc.value.details == {"missingAlbumIds": [2]}


# --------------------------------------------------------------------- delete
class TestDelete:
    def test_deletes_existing_album(self):
        album = _album(1)
        repo = FakeAlbumRepository(albums=[album])
        _service(repo).delete(1)
        assert album in repo.deleted
        assert repo.committed is True

    def test_delete_missing_raises_not_found(self):
        repo = FakeAlbumRepository()
        with pytest.raises(AlbumApplicationError) as exc:
            _service(repo).delete(404)
        assert exc.value.code == "not_found"
