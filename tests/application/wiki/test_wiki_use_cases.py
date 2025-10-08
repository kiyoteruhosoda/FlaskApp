"""Wikiユースケースの単体テスト"""

from __future__ import annotations

import pytest

from application.wiki.dto import WikiCategoryCreateInput, WikiPageCreateInput, WikiPageUpdateInput
from application.wiki.services import WikiCategoryService, WikiPageService
from application.wiki.use_cases import (
    WikiCategoryCreationUseCase,
    WikiCategoryListUseCase,
    WikiIndexUseCase,
    WikiPageCreationUseCase,
    WikiPageSearchUseCase,
    WikiPageUpdateUseCase,
)
from core.models.user import User
from domain.wiki.exceptions import WikiAccessDeniedError, WikiValidationError


@pytest.fixture
def app(app_context):
    return app_context


@pytest.fixture
def db_session(app):
    from webapp.extensions import db

    return db.session


@pytest.fixture
def test_user(app, db_session):
    with app.app_context():
        user = User(email="user@example.com")
        user.set_password("password")
        db_session.add(user)
        db_session.commit()
        return user.id


@pytest.fixture
def other_user(app, db_session):
    with app.app_context():
        user = User(email="other@example.com")
        user.set_password("password")
        db_session.add(user)
        db_session.commit()
        return user.id


def test_index_use_case_returns_expected_data(app, db_session, test_user):
    with app.app_context():
        page_service = WikiPageService()
        category_service = WikiCategoryService()

        category = category_service.create_category(name="カテゴリA")
        page_service.create_page(
            title="トップページ",
            content="コンテンツ",
            user_id=test_user,
            category_ids=[category.id],
        )

        view_model = WikiIndexUseCase(page_service, category_service).execute()

        assert any(p.title == "トップページ" for p in view_model.recent_pages)
        assert any(c.id == category.id for c in view_model.categories)
        assert view_model.page_hierarchy  # 親ページが無くても空リストではなく構造を返す


def test_page_creation_use_case_validates_input(app, test_user):
    with app.app_context():
        use_case = WikiPageCreationUseCase()
        payload = WikiPageCreateInput(
            title="",
            content="",
            slug=None,
            parent_id=None,
            category_ids=[],
            author_id=test_user,
        )

        with pytest.raises(WikiValidationError):
            use_case.execute(payload)


def test_page_update_use_case_requires_permission(app, db_session, test_user, other_user):
    with app.app_context():
        page_service = WikiPageService()
        page = page_service.create_page(
            title="編集ページ",
            content="元の内容",
            user_id=test_user,
        )

        payload = WikiPageUpdateInput(
            slug=page.slug,
            title="更新後",
            content="更新内容",
            change_summary="",
            category_ids=[],
            editor_id=other_user,
            has_admin_rights=False,
        )

        with pytest.raises(WikiAccessDeniedError):
            WikiPageUpdateUseCase(page_service).execute(payload)


def test_category_list_use_case_counts_pages(app, db_session, test_user):
    with app.app_context():
        page_service = WikiPageService()
        category_service = WikiCategoryService()

        category = category_service.create_category(name="カテゴリB")
        page_service.create_page(
            title="カテゴリページ",
            content="内容",
            user_id=test_user,
            category_ids=[category.id],
        )

        view_model = WikiCategoryListUseCase(page_service, category_service).execute()

        assert len(view_model.categories) == 1
        assert view_model.categories[0].page_count == 1
        assert view_model.categories[0].slug == category.slug


def test_category_creation_use_case_trims_input(app):
    with app.app_context():
        use_case = WikiCategoryCreationUseCase()
        payload = WikiCategoryCreateInput(
            name="  新カテゴリ  ",
            description="  説明  ",
            slug="  new-category  ",
        )

        result = use_case.execute(payload)

        assert result.category.name == "新カテゴリ"
        assert result.category.description == "説明"
        assert result.category.slug == "new-category"


def test_search_use_case_returns_empty_when_no_query(app):
    with app.app_context():
        result = WikiPageSearchUseCase().execute("   ")
        assert result.pages == []
        assert result.query == ""
