# -*- coding: utf-8 -*-
"""
ページング機能のテスト
"""

import os
import base64
import pytest
import json
from datetime import datetime, timezone

from webapp.api.pagination import (
    PaginationParams, 
    CursorInfo, 
    PaginatedResult, 
    Paginator,
    paginate_and_respond
)


@pytest.fixture
def app(tmp_path):
    """テスト用のFlaskアプリケーション"""
    db_path = tmp_path / "test.db"
    os.environ["SECRET_KEY"] = "test"
    os.environ["DATABASE_URI"] = f"sqlite:///{db_path}"
    os.environ["GOOGLE_CLIENT_ID"] = "cid"
    os.environ["GOOGLE_CLIENT_SECRET"] = "sec"
    key = base64.urlsafe_b64encode(b"0" * 32).decode()
    os.environ["ENCRYPTION_KEY"] = key
    
    import importlib
    import webapp.config as config_module
    importlib.reload(config_module)
    import webapp as webapp_module
    importlib.reload(webapp_module)
    from webapp.config import BaseApplicationSettings
    BaseApplicationSettings.SQLALCHEMY_ENGINE_OPTIONS = {}
    from webapp import create_app

    app = create_app()
    app.config.update(TESTING=True)

    from webapp.extensions import db
    from core.models.user import User

    with app.app_context():
        db.create_all()
        u = User(email="test@example.com")
        u.set_password("pass")
        db.session.add(u)
        db.session.commit()

    return app


class TestPaginationParams:
    """PaginationParamsクラスのテスト"""
    
    def test_default_values(self):
        """デフォルト値のテスト"""
        params = PaginationParams()
        assert params.page == 1
        assert params.page_size == 200
        assert params.cursor is None
        assert params.order == "desc"
        assert params.use_cursor is False
    
    def test_custom_values(self):
        """カスタム値のテスト"""
        params = PaginationParams(
            page=2, 
            page_size=100, 
            cursor="test_cursor", 
            order="asc"
        )
        assert params.page == 2
        assert params.page_size == 100
        assert params.cursor == "test_cursor"
        assert params.order == "asc"
        assert params.use_cursor is True
    
    def test_page_size_limits(self):
        """ページサイズの制限テスト"""
        # 最小値
        params = PaginationParams(page_size=0)
        assert params.page_size == 1
        
        # 最大値
        params = PaginationParams(page_size=1000)
        assert params.page_size == 500
        
        # 正常値
        params = PaginationParams(page_size=150)
        assert params.page_size == 150


class TestCursorInfo:
    """CursorInfoクラスのテスト"""
    
    def test_cursor_encoding_decoding(self):
        """カーソルのエンコード・デコードテスト"""
        # 作成
        original = CursorInfo(
            id_value=123,
            shot_at=datetime(2025, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            extra_field="test_value"
        )
        
        # エンコード
        cursor_str = original.to_cursor_string()
        assert isinstance(cursor_str, str)
        assert len(cursor_str) > 0
        
        # デコード
        decoded = CursorInfo.from_cursor_string(cursor_str)
        assert decoded is not None
        assert decoded.id_value == 123
        assert decoded.shot_at == datetime(2025, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        assert decoded.extra.get("extra_field") == "test_value"
    
    def test_invalid_cursor_string(self):
        """無効なカーソル文字列のテスト"""
        assert CursorInfo.from_cursor_string("") is None
        assert CursorInfo.from_cursor_string("invalid_base64") is None
        assert CursorInfo.from_cursor_string("aW52YWxpZF9qc29u") is None  # "invalid_json"
    
    def test_cursor_with_none_values(self):
        """None値を含むカーソルのテスト"""
        original = CursorInfo(id_value=456, shot_at=None, created_at=None)
        cursor_str = original.to_cursor_string()
        decoded = CursorInfo.from_cursor_string(cursor_str)
        
        assert decoded is not None
        assert decoded.id_value == 456
        assert decoded.shot_at is None
        assert decoded.created_at is None


class TestPaginatedResult:
    """PaginatedResultクラスのテスト"""
    
    def test_to_dict_basic(self):
        """基本的な辞書変換テスト"""
        result = PaginatedResult(
            items=[{"id": 1}, {"id": 2}],
            has_next=True,
            has_prev=False
        )
        
        data = result.to_dict()
        
        assert data["items"] == [{"id": 1}, {"id": 2}]
        assert data["hasNext"] is True
        assert data["hasPrev"] is False
        assert "server_time" in data
    
    def test_to_dict_with_cursors(self):
        """カーソー情報を含む辞書変換テスト"""
        result = PaginatedResult(
            items=[{"id": 1}],
            next_cursor="next_test",
            prev_cursor="prev_test",
            has_next=True,
            has_prev=True
        )
        
        data = result.to_dict()
        
        assert data["nextCursor"] == "next_test"
        assert data["prevCursor"] == "prev_test"
    
    def test_to_dict_with_pagination(self):
        """ページネーション情報を含む辞書変換テスト"""
        result = PaginatedResult(
            items=[{"id": 1}],
            total_count=100,
            current_page=2,
            total_pages=10,
            has_next=True,
            has_prev=True
        )
        
        data = result.to_dict()
        
        assert data["totalCount"] == 100
        assert data["currentPage"] == 2
        assert data["totalPages"] == 10
    
    def test_to_dict_without_server_time(self):
        """サーバー時刻なしの辞書変換テスト"""
        result = PaginatedResult(items=[], has_next=False, has_prev=False)
        data = result.to_dict(include_server_time=False)
        
        assert "server_time" not in data


def test_pagination_integration(app):
    """ページング機能の統合テスト"""
    from core.models.photo_models import Media
    from core.models.google_account import GoogleAccount
    from core.models.user import User
    from webapp.extensions import db

    with app.app_context():
        # テスト用のユーザーを作成
        user = User(
            email="test_integration@example.com",
            password_hash="test_hash"
        )
        db.session.add(user)
        db.session.flush()  # IDを取得するためにflush
        
        # テスト用のGoogleアカウントを作成
        account = GoogleAccount(
            user_id=user.id,
            email="test_integration@example.com",
            status="active",
            scopes="https://www.googleapis.com/auth/photoslibrary.readonly"
        )
        db.session.add(account)
        db.session.flush()  # IDを取得するためにflush        # テストデータの作成
        test_media = []
        for i in range(5):
            media = Media(
                source_type='google_photos',
                google_media_id=f"test_media_id_{i}",
                account_id=account.id,
                local_rel_path=f"test/path_{i}.jpg",
                hash_sha256=f"{'0' * 63}{i}",
                bytes=1000 + i,
                mime_type="image/jpeg",
                width=1920,
                height=1080,
                shot_at=datetime(2025, 1, i+1, 12, 0, 0, tzinfo=timezone.utc),
                is_video=False,
                is_deleted=False,
                has_playback=False,
                imported_at=datetime.now(timezone.utc)
            )
            test_media.append(media)
            db.session.add(media)
        
        db.session.commit()
        
        try:
            # ページングパラメータ
            params = PaginationParams(page_size=2, order="desc")
            
            # クエリ実行
            query = Media.query.filter(Media.id.in_([m.id for m in test_media]))
            result = Paginator.paginate_query(
                query=query,
                params=params,
                id_column=Media.id,
                shot_at_column=Media.shot_at,
                count_total=True
            )
            
            # 結果検証
            assert len(result.items) == 2
            assert result.total_count == 5
            assert result.has_next is True
            assert result.has_prev is False
            assert result.current_page == 1
            assert result.total_pages == 3
            
            # ソート順の確認（降順）
            assert result.items[0].shot_at > result.items[1].shot_at
            
        finally:
            # クリーンアップ
            for media in test_media:
                db.session.delete(media)
            db.session.delete(account)
            db.session.commit()


def test_cursor_based_pagination(app):
    """カーソーベースページングのテスト"""
    from core.models.photo_models import Media
    from core.models.google_account import GoogleAccount
    from core.models.user import User
    from webapp.extensions import db

    with app.app_context():
        # テスト用のユーザーを作成
        user = User(
            email="test_cursor@example.com",
            password_hash="test_hash"
        )
        db.session.add(user)
        db.session.flush()  # IDを取得するためにflush
        
        # テスト用のGoogleアカウントを作成
        account = GoogleAccount(
            user_id=user.id,
            email="test_cursor@example.com",
            status="active",
            scopes="https://www.googleapis.com/auth/photoslibrary.readonly"
        )
        db.session.add(account)
        db.session.flush()  # IDを取得するためにflush        # テストデータの作成
        test_media = []
        for i in range(5):  # 5件に増やす
            media = Media(
                source_type='google_photos',
                google_media_id=f"test_cursor_id_{i}",
                account_id=account.id,
                local_rel_path=f"test/cursor_{i}.jpg",
                hash_sha256=f"{'1' * 63}{i}",
                bytes=2000 + i,
                mime_type="image/jpeg",
                width=1920,
                height=1080,
                shot_at=datetime(2025, 1, i+10, 12, 0, 0, tzinfo=timezone.utc),
                is_video=False,
                is_deleted=False,
                has_playback=False,
                imported_at=datetime.now(timezone.utc)
            )
            test_media.append(media)
            db.session.add(media)

        db.session.commit()

        try:
            # カーソーベースページングを明示的に使用するために、
            # PaginationParamsを直接作成してuse_cursorを設定
            params = PaginationParams(page_size=2, cursor=None, order="desc")
            params.use_cursor = True  # カーソーベースページングを強制的に有効化
            query = Media.query.filter(Media.id.in_([m.id for m in test_media]))

            result1 = Paginator.paginate_query(
                query=query,
                params=params,
                id_column=Media.id,
                shot_at_column=Media.shot_at
            )

            assert len(result1.items) == 2
            assert result1.has_next is True
            assert result1.next_cursor is not None
            
            # 2ページ目（カーソー使用）
            params2 = PaginationParams(
                page_size=2, 
                cursor=result1.next_cursor, 
                order="desc"
            )
            
            result2 = Paginator.paginate_query(
                query=query,
                params=params2,
                id_column=Media.id,
                shot_at_column=Media.shot_at
            )
            
            assert len(result2.items) == 2
            assert result2.has_next is True  # まだ次のページがある
            assert result2.has_prev is True

            # 3ページ目（最後のページ）
            params3 = PaginationParams(
                page_size=2,
                cursor=result2.next_cursor,
                order="desc"
            )
            
            result3 = Paginator.paginate_query(
                query=query,
                params=params3,
                id_column=Media.id,
                shot_at_column=Media.shot_at
            )
            
            assert len(result3.items) == 1  # 最後の1件
            assert result3.has_next is False
            assert result3.has_prev is True
            
            # ページ間でアイテムが重複していないことを確認
            ids1 = {item.id for item in result1.items}
            ids2 = {item.id for item in result2.items}
            ids3 = {item.id for item in result3.items}
            assert len(ids1.intersection(ids2)) == 0
            assert len(ids1.intersection(ids3)) == 0
            assert len(ids2.intersection(ids3)) == 0
            
        finally:
            # クリーンアップ
            for media in test_media:
                db.session.delete(media)
            db.session.delete(account)
            db.session.commit()


@pytest.mark.parametrize("order", ["asc", "desc"])
def test_pagination_order(app, order):
    """ソート順のテスト"""
    from core.models.photo_models import Media
    from core.models.google_account import GoogleAccount
    from core.models.user import User
    from webapp.extensions import db

    with app.app_context():
        # テスト用のユーザーを作成
        user = User(
            email=f"test_order_{order}@example.com",
            password_hash="test_hash"
        )
        db.session.add(user)
        db.session.flush()  # IDを取得するためにflush
        
        # テスト用のGoogleアカウントを作成
        account = GoogleAccount(
            user_id=user.id,
            email=f"test_order_{order}@example.com",
            status="active",
            scopes="https://www.googleapis.com/auth/photoslibrary.readonly"
        )
        db.session.add(account)
        db.session.flush()  # IDを取得するためにflush        # テストデータの作成
        test_media = []
        for i in range(3):
            media = Media(
                source_type='google_photos',
                google_media_id=f"test_order_id_{i}",
                account_id=account.id,
                local_rel_path=f"test/order_{i}.jpg",
                hash_sha256=f"{'2' * 63}{i}",
                bytes=3000 + i,
                mime_type="image/jpeg",
                width=1920,
                height=1080,
                shot_at=datetime(2025, 1, i+20, 12, 0, 0, tzinfo=timezone.utc),
                is_video=False,
                is_deleted=False,
                has_playback=False,
                imported_at=datetime.now(timezone.utc)
            )
            test_media.append(media)
            db.session.add(media)
        
        db.session.commit()
        
        try:
            params = PaginationParams(page_size=10, order=order)
            query = Media.query.filter(Media.id.in_([m.id for m in test_media]))
            
            result = Paginator.paginate_query(
                query=query,
                params=params,
                id_column=Media.id,
                shot_at_column=Media.shot_at
            )
            
            assert len(result.items) == 3
            
            # ソート順の確認
            shot_ats = [item.shot_at for item in result.items]
            if order == "asc":
                assert shot_ats == sorted(shot_ats)
            else:
                assert shot_ats == sorted(shot_ats, reverse=True)
                
        finally:
            # クリーンアップ
            for media in test_media:
                db.session.delete(media)
            db.session.delete(account)
            db.session.commit()
