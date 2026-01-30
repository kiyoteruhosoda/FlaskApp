import pytest

from bounded_contexts.wiki.domain.commands import (
    WikiPageCommandFactory,
    WikiPageCreationCommand,
    WikiPageDeleteCommand,
    WikiPageUpdateCommand,
)
from bounded_contexts.wiki.domain.exceptions import WikiValidationError


def test_build_creation_command_normalizes_values() -> None:
    factory = WikiPageCommandFactory()

    command = factory.build_creation_command(
        title="  Title  ",
        content="  Content  ",
        slug="  custom ",
        parent_id="42",
        category_ids=["1", "", 2, None],
        author_id=10,
    )

    assert isinstance(command, WikiPageCreationCommand)
    assert command.title == "Title"
    assert command.content == "Content"
    assert command.slug == "custom"
    assert command.parent_id == 42
    assert command.category_ids == (1, 2)
    assert command.author_id == 10


def test_build_creation_command_validates_required_fields() -> None:
    factory = WikiPageCommandFactory()

    try:
        factory.build_creation_command(
            title=" ",
            content="",
            slug=None,
            parent_id=None,
            category_ids=[],
            author_id=1,
        )
    except WikiValidationError as exc:
        assert "タイトルと内容は必須です" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("expected validation error")


def test_build_creation_command_validates_parent_id() -> None:
    factory = WikiPageCommandFactory()

    try:
        factory.build_creation_command(
            title="Title",
            content="Content",
            slug=None,
            parent_id="invalid",
            category_ids=[],
            author_id=1,
        )
    except WikiValidationError as exc:
        assert "親ページの指定が不正です" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("expected validation error")


def test_build_creation_command_validates_category_ids() -> None:
    factory = WikiPageCommandFactory()

    try:
        factory.build_creation_command(
            title="Title",
            content="Content",
            slug=None,
            parent_id=None,
            category_ids=["invalid"],
            author_id=1,
        )
    except WikiValidationError as exc:
        assert "カテゴリの指定が不正です" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("expected validation error")


def test_build_update_command_normalizes_values() -> None:
    factory = WikiPageCommandFactory()

    command = factory.build_update_command(
        slug="  slug  ",
        title="  Title  ",
        content="  Content  ",
        change_summary=" summary ",
        category_ids=["1", 2, ""],
        editor_id=5,
        has_admin_rights=True,
    )

    assert isinstance(command, WikiPageUpdateCommand)
    assert command.slug == "slug"
    assert command.title == "Title"
    assert command.content == "Content"
    assert command.change_summary == "summary"
    assert command.category_ids == (1, 2)
    assert command.editor_id == 5
    assert command.has_admin_rights is True


def test_build_update_command_validates_required_fields() -> None:
    factory = WikiPageCommandFactory()

    try:
        factory.build_update_command(
            slug=" ",
            title="",
            content="",
            change_summary=None,
            category_ids=[],
            editor_id=1,
            has_admin_rights=False,
        )
    except WikiValidationError as exc:
        assert "タイトルと内容は必須です" in str(exc) or "ページ識別子は必須です" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("expected validation error")


def test_build_delete_command_normalizes_values() -> None:
    factory = WikiPageCommandFactory()

    command = factory.build_delete_command(
        slug="  sample-slug  ",
        executor_id=7,
        has_admin_rights=True,
    )

    assert isinstance(command, WikiPageDeleteCommand)
    assert command.slug == "sample-slug"
    assert command.executor_id == 7
    assert command.has_admin_rights is True


def test_build_delete_command_requires_identifier() -> None:
    factory = WikiPageCommandFactory()

    with pytest.raises(WikiValidationError) as exc:
        factory.build_delete_command(slug="  ", executor_id=1, has_admin_rights=False)

    assert "Page identifier is required." in str(exc.value)

