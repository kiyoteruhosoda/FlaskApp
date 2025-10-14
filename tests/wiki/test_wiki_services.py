"""
Wiki機能のテスト
"""

import pytest
from datetime import datetime, timezone
from application.wiki.services import WikiPageService, WikiCategoryService
from core.models.wiki.models import WikiPage, WikiCategory
from core.models.user import User
from domain.wiki.slug import SlugService


class TestWikiPageService:
    """WikiPageServiceのテスト"""
    
    def test_create_page(self, app, db_session, test_user):
        """ページ作成のテスト"""
        with app.app_context():
            service = WikiPageService()
            
            page = service.create_page(
                title="テストページ",
                content="これはテストページです。",
                user_id=test_user.id
            )
            
            assert page.id is not None
            assert page.title == "テストページ"
            assert page.content == "これはテストページです。"
            assert page.created_by_id == test_user.id
            assert page.slug is not None
            assert page.is_published is True
    
    def test_create_page_with_custom_slug(self, app, db_session, test_user):
        """カスタムスラッグでのページ作成テスト"""
        with app.app_context():
            service = WikiPageService()
            
            page = service.create_page(
                title="テストページ",
                content="内容",
                user_id=test_user.id,
                slug="custom-slug"
            )
            
            assert page.slug == "custom-slug"
    
    def test_create_page_with_parent(self, app, db_session, test_user):
        """親ページありでのページ作成テスト"""
        with app.app_context():
            service = WikiPageService()

            # 親ページを作成
            parent = service.create_page(
                title="親ページ",
                content="親ページの内容",
                user_id=test_user.id
            )
            
            # 子ページを作成
            child = service.create_page(
                title="子ページ",
                content="子ページの内容",
                user_id=test_user.id,
                parent_id=parent.id
            )
            
            assert child.parent_id == parent.id
            assert child.parent == parent

    def test_create_page_with_invalid_slug_falls_back(self, app, db_session, test_user):
        """不正なスラッグ指定時に自動生成へフォールバックする"""
        with app.app_context():
            service = WikiPageService()

            page = service.create_page(
                title="フォールバックタイトル",
                content="内容",
                user_id=test_user.id,
                slug="***"
            )

            expected_slug = SlugService().generate_from_text("フォールバックタイトル").value
            assert page.slug == expected_slug

    def test_update_page(self, app, db_session, test_user):
        """ページ更新のテスト"""
        with app.app_context():
            service = WikiPageService()
            
            # ページを作成
            page = service.create_page(
                title="元のタイトル",
                content="元の内容",
                user_id=test_user.id
            )
            
            # ページを更新
            updated_page = service.update_page(
                page_id=page.id,
                title="更新されたタイトル",
                content="更新された内容",
                user_id=test_user.id,
                change_summary="テスト更新"
            )
            
            assert updated_page.title == "更新されたタイトル"
            assert updated_page.content == "更新された内容"
            assert updated_page.updated_by_id == test_user.id
    
    def test_search_pages(self, app, db_session, test_user):
        """ページ検索のテスト"""
        with app.app_context():
            service = WikiPageService()
            
            # テストページを作成
            service.create_page(
                title="Python プログラミング",
                content="Python の基礎",
                user_id=test_user.id
            )
            
            service.create_page(
                title="JavaScript ガイド",
                content="JavaScript の基本",
                user_id=test_user.id
            )
            
            # 検索実行
            results = service.search_pages("Python")
            
            assert len(results) == 1
            assert results[0].title == "Python プログラミング"
    
    def test_get_page_hierarchy(self, app, db_session, test_user):
        """ページ階層取得のテスト"""
        with app.app_context():
            service = WikiPageService()
            
            # 親ページを作成
            parent = service.create_page(
                title="親ページ",
                content="親の内容",
                user_id=test_user.id
            )
            
            # 子ページを作成
            child1 = service.create_page(
                title="子ページ1",
                content="子1の内容",
                user_id=test_user.id,
                parent_id=parent.id
            )
            
            child2 = service.create_page(
                title="子ページ2",
                content="子2の内容",
                user_id=test_user.id,
                parent_id=parent.id
            )
            
            # 階層構造を取得
            hierarchy = service.get_page_hierarchy()
            
            assert len(hierarchy) == 1  # 親ページが1つ
            assert hierarchy[0]['title'] == "親ページ"
            assert len(hierarchy[0]['children']) == 2  # 子ページが2つ


class TestWikiCategoryService:
    """WikiCategoryServiceのテスト"""
    
    def test_create_category(self, app, db_session):
        """カテゴリ作成のテスト"""
        with app.app_context():
            service = WikiCategoryService()
            
            category = service.create_category(
                name="プログラミング",
                description="プログラミング関連のページ"
            )
            
            assert category.id is not None
            assert category.name == "プログラミング"
            assert category.description == "プログラミング関連のページ"
            assert category.slug is not None
    
    def test_create_category_with_custom_slug(self, app, db_session):
        """カスタムスラッグでのカテゴリ作成テスト"""
        with app.app_context():
            service = WikiCategoryService()

            category = service.create_category(
                name="プログラミング",
                slug="programming"
            )

            assert category.slug == "programming"

    def test_create_category_with_invalid_slug_falls_back(self, app, db_session):
        """不正なスラッグの場合でも自動生成される"""
        with app.app_context():
            service = WikiCategoryService()

            category = service.create_category(
                name="カテゴリ",
                slug="###"
            )

            expected_slug = SlugService().generate_from_text("カテゴリ").value
            assert category.slug == expected_slug
    
    def test_get_all_categories(self, app, db_session):
        """全カテゴリ取得のテスト"""
        with app.app_context():
            service = WikiCategoryService()
            
            # カテゴリを作成
            service.create_category(name="カテゴリ1")
            service.create_category(name="カテゴリ2")
            
            # 全カテゴリを取得
            categories = service.get_all_categories()
            
            assert len(categories) == 2
            assert any(c.name == "カテゴリ1" for c in categories)
            assert any(c.name == "カテゴリ2" for c in categories)
