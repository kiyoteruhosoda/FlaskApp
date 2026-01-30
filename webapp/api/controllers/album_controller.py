"""Album domain controller."""

from typing import Dict, Any, List
from datetime import datetime

from flask import Blueprint, current_app, request, abort
from flask_login import login_required, current_user
from flask_babel import gettext as _
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from .base_controller import BaseController
from webapp.api.pagination import PaginationParams, paginate_and_respond
from core.models.photo_models import Album, Media, album_item
from core.time import utc_now_isoformat


class AlbumController(BaseController):
    """アルバムドメインコントローラー."""
    
    def _register_routes(self) -> None:
        """アルバム関連のルートを登録."""
        
        @self.bp.get("/albums")
        @login_required
        def list_albums():
            """アルバム一覧取得."""
            return self._handle_album_list()
        
        @self.bp.get("/albums/<int:album_id>")
        @login_required
        def get_album(album_id: int):
            """アルバム詳細取得."""
            return self._handle_album_detail(album_id)
        
        @self.bp.post("/albums")
        @login_required
        def create_album():
            """アルバム作成."""
            return self._handle_album_create()
        
        @self.bp.put("/albums/<int:album_id>")
        @login_required
        def update_album(album_id: int):
            """アルバム更新."""
            return self._handle_album_update(album_id)
        
        @self.bp.delete("/albums/<int:album_id>")
        @login_required
        def delete_album(album_id: int):
            """アルバム削除."""
            return self._handle_album_delete(album_id)
        
        @self.bp.put("/albums/<int:album_id>/media/order")
        @login_required
        def update_media_order(album_id: int):
            """アルバム内メディア順序更新."""
            return self._handle_media_order_update(album_id)
        
        @self.bp.put("/albums/order")
        @login_required
        def update_album_order():
            """アルバム順序更新."""
            return self._handle_album_order_update()
        
        @self.bp.post("/albums/<int:album_id>/media")
        @login_required
        def add_media_to_album(album_id: int):
            """アルバムにメディア追加."""
            return self._handle_add_media(album_id)
        
        @self.bp.delete("/albums/<int:album_id>/media/<int:media_id>")
        @login_required
        def remove_media_from_album(album_id: int, media_id: int):
            """アルバムからメディア削除."""
            return self._handle_remove_media(album_id, media_id)
    
    def _handle_album_list(self) -> Dict[str, Any]:
        """アルバム一覧処理."""
        self._log_action("album_list_request")
        
        # パラメータ取得
        pagination = PaginationParams.from_request(request)
        search_query = request.args.get("search", "").strip()
        sort_by = request.args.get("sort", "updated_at")  # name, created_at, updated_at
        
        # クエリ構築
        query = self._build_album_query(search_query, sort_by)
        
        # ページネーション実行
        result = paginate_and_respond(
            query=query,
            pagination=pagination,
            serializer=self._serialize_album
        )
        
        self._log_action("album_list_success", {
            "count": len(result.get("data", []))
        })
        
        return result
    
    def _handle_album_detail(self, album_id: int) -> Dict[str, Any]:
        """アルバム詳細処理."""
        album = self._get_album_or_404(album_id)
        
        # メディア数を取得
        media_count = (
            select(func.count(album_item.c.media_id))
            .where(album_item.c.album_id == album_id)
            .scalar()
        )
        
        self._log_action("album_detail", {"album_id": album_id})
        
        return self._success_response(self._serialize_album_detail(album, media_count))
    
    def _handle_album_create(self) -> Dict[str, Any]:
        """アルバム作成処理."""
        data = request.get_json() or {}
        
        required_fields = ["name"]
        for field in required_fields:
            if not data.get(field):
                return self._error_response(_(f"Field '{field}' is required"))
        
        # 重複チェック
        existing = Album.query.filter_by(name=data["name"]).first()
        if existing:
            return self._error_response(_("Album with this name already exists"))
        
        # アルバム作成
        album = Album(
            name=data["name"],
            description=data.get("description", ""),
            created_by=current_user.id,
            created_at=utc_now_isoformat(),
            updated_at=utc_now_isoformat(),
            sort_order=self._get_next_album_sort_order()
        )
        
        from webapp.extensions import db
        db.session.add(album)
        db.session.commit()
        
        self._log_action("album_created", {
            "album_id": album.id,
            "name": album.name
        })
        
        return self._success_response(
            self._serialize_album_detail(album, 0),
            _("Album created successfully")
        )
    
    def _handle_album_update(self, album_id: int) -> Dict[str, Any]:
        """アルバム更新処理."""
        album = self._get_album_or_404(album_id)
        data = request.get_json() or {}
        
        # 更新可能フィールド
        updatable_fields = ["name", "description"]
        updated_fields = []
        
        for field in updatable_fields:
            if field in data:
                # 重複チェック（名前の場合）
                if field == "name" and data[field] != album.name:
                    existing = Album.query.filter_by(name=data[field]).first()
                    if existing:
                        return self._error_response(_("Album with this name already exists"))
                
                setattr(album, field, data[field])
                updated_fields.append(field)
        
        if updated_fields:
            album.updated_at = utc_now_isoformat()
            from webapp.extensions import db
            db.session.commit()
            
            self._log_action("album_updated", {
                "album_id": album_id,
                "fields": updated_fields
            })
        
        media_count = self._get_album_media_count(album_id)
        
        return self._success_response(
            self._serialize_album_detail(album, media_count),
            _("Album updated successfully")
        )
    
    def _handle_album_delete(self, album_id: int) -> Dict[str, Any]:
        """アルバム削除処理."""
        album = self._get_album_or_404(album_id)
        
        # メディアとの関連を削除（メディア自体は削除しない）
        from webapp.extensions import db
        db.session.execute(
            album_item.delete().where(album_item.c.album_id == album_id)
        )
        
        # アルバム削除
        db.session.delete(album)
        db.session.commit()
        
        self._log_action("album_deleted", {
            "album_id": album_id,
            "name": album.name
        })
        
        return self._success_response(message=_("Album deleted successfully"))
    
    def _handle_media_order_update(self, album_id: int) -> Dict[str, Any]:
        """アルバム内メディア順序更新."""
        album = self._get_album_or_404(album_id)
        data = request.get_json() or {}
        media_orders = data.get("media_orders", [])
        
        if not media_orders:
            return self._error_response(_("Media orders are required"))
        
        # 順序更新
        from webapp.extensions import db
        for order_info in media_orders:
            media_id = order_info.get("media_id")
            sort_order = order_info.get("sort_order")
            
            if media_id and sort_order is not None:
                db.session.execute(
                    album_item.update()
                    .where(album_item.c.album_id == album_id)
                    .where(album_item.c.media_id == media_id)
                    .values(sort_order=sort_order)
                )
        
        # アルバム更新日時更新
        album.updated_at = utc_now_isoformat()
        db.session.commit()
        
        self._log_action("album_media_order_updated", {
            "album_id": album_id,
            "media_count": len(media_orders)
        })
        
        return self._success_response(message=_("Media order updated successfully"))
    
    def _handle_album_order_update(self) -> Dict[str, Any]:
        """アルバム順序更新."""
        data = request.get_json() or {}
        album_orders = data.get("album_orders", [])
        
        if not album_orders:
            return self._error_response(_("Album orders are required"))
        
        # 順序更新
        from webapp.extensions import db
        for order_info in album_orders:
            album_id = order_info.get("album_id")
            sort_order = order_info.get("sort_order")
            
            if album_id and sort_order is not None:
                album = Album.query.get(album_id)
                if album:
                    album.sort_order = sort_order
                    album.updated_at = utc_now_isoformat()
        
        db.session.commit()
        
        self._log_action("album_order_updated", {
            "album_count": len(album_orders)
        })
        
        return self._success_response(message=_("Album order updated successfully"))
    
    def _handle_add_media(self, album_id: int) -> Dict[str, Any]:
        """アルバムへのメディア追加."""
        album = self._get_album_or_404(album_id)
        data = request.get_json() or {}
        media_ids = data.get("media_ids", [])
        
        if not media_ids:
            return self._error_response(_("Media IDs are required"))
        
        added_count = 0
        from webapp.extensions import db
        
        for media_id in media_ids:
            # メディア存在チェック
            media = Media.query.get(media_id)
            if not media:
                continue
            
            # 既存チェック
            existing = db.session.execute(
                select(album_item)
                .where(album_item.c.album_id == album_id)
                .where(album_item.c.media_id == media_id)
            ).first()
            
            if not existing:
                # 追加
                db.session.execute(
                    album_item.insert().values(
                        album_id=album_id,
                        media_id=media_id,
                        sort_order=self._get_next_media_sort_order(album_id)
                    )
                )
                added_count += 1
        
        # アルバム更新日時更新
        album.updated_at = utc_now_isoformat()
        db.session.commit()
        
        self._log_action("album_media_added", {
            "album_id": album_id,
            "added_count": added_count,
            "requested_count": len(media_ids)
        })
        
        return self._success_response({
            "added_count": added_count,
            "total_requested": len(media_ids)
        })
    
    def _handle_remove_media(self, album_id: int, media_id: int) -> Dict[str, Any]:
        """アルバムからのメディア削除."""
        album = self._get_album_or_404(album_id)
        
        from webapp.extensions import db
        result = db.session.execute(
            album_item.delete()
            .where(album_item.c.album_id == album_id)
            .where(album_item.c.media_id == media_id)
        )
        
        if result.rowcount == 0:
            return self._error_response(_("Media not found in album"))
        
        # アルバム更新日時更新
        album.updated_at = utc_now_isoformat()
        db.session.commit()
        
        self._log_action("album_media_removed", {
            "album_id": album_id,
            "media_id": media_id
        })
        
        return self._success_response(message=_("Media removed from album"))
    
    # ヘルパーメソッド
    
    def _get_album_or_404(self, album_id: int) -> Album:
        """アルバム取得（404エラー付き）."""
        album = Album.query.filter_by(id=album_id).first()
        if not album:
            abort(404, description=_("Album not found"))
        return album
    
    def _build_album_query(self, search_query: str, sort_by: str):
        """アルバム検索クエリ構築."""
        query = Album.query
        
        if search_query:
            query = query.filter(
                Album.name.ilike(f"%{search_query}%") |
                Album.description.ilike(f"%{search_query}%")
            )
        
        # ソート条件
        if sort_by == "name":
            query = query.order_by(Album.name.asc())
        elif sort_by == "created_at":
            query = query.order_by(Album.created_at.desc())
        else:  # updated_at (default)
            query = query.order_by(Album.updated_at.desc())
        
        return query
    
    def _serialize_album(self, album: Album) -> Dict[str, Any]:
        """アルバムシリアライゼーション."""
        # メディア数を取得
        media_count = self._get_album_media_count(album.id)
        
        # サムネイル用の最初のメディアを取得
        cover_media = self._get_album_cover_media(album.id)
        
        return {
            "id": album.id,
            "name": album.name,
            "description": album.description,
            "media_count": media_count,
            "created_at": album.created_at,
            "updated_at": album.updated_at,
            "sort_order": getattr(album, 'sort_order', 0),
            "cover_thumbnail": f"/api/media/{cover_media.id}/thumbnail?size=256" if cover_media else None
        }
    
    def _serialize_album_detail(self, album: Album, media_count: int) -> Dict[str, Any]:
        """アルバム詳細シリアライゼーション."""
        data = self._serialize_album(album)
        data.update({
            "media_count": media_count,
            "created_by": album.created_by
        })
        return data
    
    def _get_album_media_count(self, album_id: int) -> int:
        """アルバム内メディア数取得."""
        from webapp.extensions import db
        return db.session.execute(
            select(func.count(album_item.c.media_id))
            .where(album_item.c.album_id == album_id)
        ).scalar() or 0
    
    def _get_album_cover_media(self, album_id: int) -> Media:
        """アルバムカバー用メディア取得."""
        from webapp.extensions import db
        return db.session.execute(
            select(Media)
            .join(album_item)
            .where(album_item.c.album_id == album_id)
            .order_by(album_item.c.sort_order.asc())
            .limit(1)
        ).scalar()
    
    def _get_next_album_sort_order(self) -> int:
        """次のアルバムソート順序取得."""
        from webapp.extensions import db
        max_order = db.session.execute(
            select(func.max(Album.sort_order))
        ).scalar() or 0
        return max_order + 1
    
    def _get_next_media_sort_order(self, album_id: int) -> int:
        """アルバム内の次のメディアソート順序取得."""
        from webapp.extensions import db
        max_order = db.session.execute(
            select(func.max(album_item.c.sort_order))
            .where(album_item.c.album_id == album_id)
        ).scalar() or 0
        return max_order + 1