import pytest

from bounded_contexts.wiki.domain.slug import Slug, SlugService


class TestSlugService:
    def setup_method(self) -> None:
        self.service = SlugService()

    def test_generate_from_text_normalizes_unicode(self) -> None:
        slug = self.service.generate_from_text("Python 入門! ガイド")
        assert slug.value == "python-入門-ガイド"

    def test_generate_from_text_rejects_empty(self) -> None:
        with pytest.raises(ValueError):
            self.service.generate_from_text("!!!")

    def test_from_user_input_validates_pattern(self) -> None:
        slug = self.service.from_user_input("CustomSlug")
        assert slug.value == "CustomSlug"

        with pytest.raises(ValueError):
            self.service.from_user_input("bad slug")

    def test_ensure_unique_appends_counter(self) -> None:
        existing = {"hello-world", "hello-world-1"}

        def exists(value: str) -> bool:
            return value in existing

        unique = self.service.ensure_unique(Slug("hello-world"), exists)
        assert unique.value == "hello-world-2"

    def test_generate_unique_from_text_handles_collision(self) -> None:
        existing = {"python-guide"}

        def exists(value: str) -> bool:
            return value in existing

        unique = self.service.generate_unique_from_text("Python Guide", exists)
        assert unique.value == "python-guide-1"

    @pytest.mark.parametrize(
        "candidate, expected",
        [
            ("valid-slug", True),
            ("UPPER_and_lower", True),
            ("with space", False),
            ("", False),
            (None, False),
        ],
    )
    def test_is_valid(self, candidate, expected) -> None:
        assert self.service.is_valid(candidate) is expected
