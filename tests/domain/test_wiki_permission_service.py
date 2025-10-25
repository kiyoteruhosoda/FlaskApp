from dataclasses import dataclass

from features.wiki.domain.entities import WikiPage as DomainWikiPage
from features.wiki.domain.permissions import EditorContext, WikiPagePermissionService


@dataclass
class SimplePage:
    created_by_id: int


def test_owner_can_edit_without_admin() -> None:
    service = WikiPagePermissionService()
    page = SimplePage(created_by_id=10)
    editor = EditorContext(user_id=10, is_admin=False)

    assert service.can_edit(page, editor) is True


def test_non_owner_without_admin_cannot_edit() -> None:
    service = WikiPagePermissionService()
    page = SimplePage(created_by_id=10)
    editor = EditorContext(user_id=5, is_admin=False)

    assert service.can_edit(page, editor) is False


def test_admin_can_edit_any_page() -> None:
    service = WikiPagePermissionService()
    page = SimplePage(created_by_id=10)
    editor = EditorContext(user_id=1, is_admin=True)

    assert service.can_edit(page, editor) is True


def test_owner_can_delete_without_admin() -> None:
    service = WikiPagePermissionService()
    page = SimplePage(created_by_id=10)
    editor = EditorContext(user_id=10, is_admin=False)

    assert service.can_delete(page, editor) is True


def test_non_owner_without_admin_cannot_delete() -> None:
    service = WikiPagePermissionService()
    page = SimplePage(created_by_id=10)
    editor = EditorContext(user_id=5, is_admin=False)

    assert service.can_delete(page, editor) is False


def test_admin_can_delete_any_page() -> None:
    service = WikiPagePermissionService()
    page = SimplePage(created_by_id=10)
    editor = EditorContext(user_id=1, is_admin=True)

    assert service.can_delete(page, editor) is True


def test_domain_entity_delegates_to_entity_logic() -> None:
    service = WikiPagePermissionService()
    entity = DomainWikiPage(
        id=1,
        title="title",
        content="content",
        slug="slug",
        created_at=None,
        updated_at=None,
        created_by_id=10,
        updated_by_id=10,
    )
    editor = EditorContext(user_id=99, is_admin=False)

    assert service.can_edit(entity, editor) is False

