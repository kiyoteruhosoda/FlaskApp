"""Album ドメイン値オブジェクトの純粋ユニットテスト（外部依存なし）."""
from __future__ import annotations

import pytest

from bounded_contexts.photonest.domain.album import (
    AlbumVisibility,
    DuplicateMediaSelection,
    InvalidAlbumVisibility,
    InvalidMediaSelection,
    parse_album_ids,
    parse_media_ids,
    parse_ordered_media_ids,
    resolve_cover_media_id,
)


class TestAlbumVisibility:
    def test_values_are_the_three_known_modes(self):
        assert AlbumVisibility.values() == frozenset({"public", "private", "unlisted"})

    @pytest.mark.parametrize("raw", ["public", "PRIVATE", "  Unlisted "])
    def test_parse_normalizes_case_and_whitespace(self, raw):
        assert AlbumVisibility.parse(raw).value == raw.strip().lower()

    @pytest.mark.parametrize("raw", ["", "secret", None])
    def test_parse_rejects_unknown_values(self, raw):
        with pytest.raises(InvalidAlbumVisibility):
            AlbumVisibility.parse(raw)


class TestParseMediaIds:
    def test_none_yields_empty_list(self):
        assert parse_media_ids(None) == []

    def test_dedupes_preserving_first_seen_order(self):
        assert parse_media_ids([3, 1, 3, 2, 1]) == [3, 1, 2]

    def test_skips_blank_entries_and_coerces_strings(self):
        assert parse_media_ids(["1", None, "", 2]) == [1, 2]

    def test_rejects_non_sequence(self):
        with pytest.raises(InvalidMediaSelection):
            parse_media_ids("123")

    def test_rejects_non_integer_items(self):
        with pytest.raises(InvalidMediaSelection):
            parse_media_ids([1, "abc"])


class TestParseOrderedMediaIds:
    def test_keeps_order(self):
        assert parse_ordered_media_ids([5, 4, 6]) == [5, 4, 6]

    def test_rejects_duplicates(self):
        with pytest.raises(DuplicateMediaSelection):
            parse_ordered_media_ids([1, 2, 1])

    def test_rejects_non_integer(self):
        with pytest.raises(InvalidMediaSelection):
            parse_ordered_media_ids([1, "x"])


class TestParseAlbumIds:
    def test_dedupes_silently_keeping_order(self):
        assert parse_album_ids([10, 5, 10, 2]) == [10, 5, 2]

    def test_rejects_non_integer(self):
        with pytest.raises(InvalidMediaSelection):
            parse_album_ids([1, None])


class TestResolveCoverMediaId:
    def test_keeps_valid_cover(self):
        assert resolve_cover_media_id(2, [1, 2, 3]) == 2

    def test_falls_back_to_first_when_cover_missing(self):
        assert resolve_cover_media_id(99, [1, 2, 3]) == 1

    def test_falls_back_to_first_when_cover_none(self):
        assert resolve_cover_media_id(None, [7, 8]) == 7

    def test_none_when_no_media(self):
        assert resolve_cover_media_id(None, []) is None
        assert resolve_cover_media_id(5, []) is None
