"""Tag domain controller."""

from typing import Dict, Any

from flask import Blueprint, current_app, request, abort
from flask_login import login_required, current_user
from flask_babel import gettext as _
from sqlalchemy.orm import joinedload

from .base_controller import BaseController
from webapp.api.pagination import PaginationParams, paginate_and_respond
from core.models.photo_models import Tag, media_tag
from core.time import utc_now_isoformat


class TagController(BaseController):
    """タグドメインコントローラー."""
    
    def _register_routes(self) -> None:
        """タグ関連のルートを登録."""
        
        @self.bp.get("/tags")
        @login_required
        def list_tags():
            """タグ一覧取得."""
            return self._handle_tag_list()
        
        @self.bp.post("/tags")
        @login_required
        def create_tag():
            """タグ作成."""
            return self._handle_tag_create()
        
        @self.bp.put("/tags/<int:tag_id>")
        @login_required
        def update_tag(tag_id: int):
            """タグ更新."""
            return self._handle_tag_update(tag_id)
        
        @self.bp.delete("/tags/<int:tag_id>")
        @login_required
        def delete_tag(tag_id: int):
            """タグ削除."""
            return self._handle_tag_delete(tag_id)
        
        @self.bp.put("/media/<int:media_id>/tags")
        @login_required
        def update_media_tags(media_id: int):
            """メディアタグ更新."""
            return self._handle_media_tags_update(media_id)
    
    def _handle_tag_list(self) -> Dict[str, Any]:
        """タグ一覧処理."""
        self._log_action("tag_list_request")
        
        pagination = PaginationParams.from_request(request)
        search_query = request.args.get("search", "").strip()
        
        query = Tag.query
        if search_query:
            query = query.filter(Tag.name.ilike(f"%{search_query}%"))
        
        query = query.order_by(Tag.name.asc())
        
        result = paginate_and_respond(
            query=query,
            pagination=pagination,
            serializer=self._serialize_tag
        )
        
        return result
    
    def _handle_tag_create(self) -> Dict[str, Any]:
        """タグ作成処理."""
        data = request.get_json() or {}
        name = data.get("name", "").strip()
        
        if not name:
            return self._error_response(_("Tag name is required"))
        
        # 重複チェック
        existing = Tag.query.filter_by(name=name).first()
        if existing:
            return self._error_response(_("Tag with this name already exists"))
        
        # タグ作成
        tag = Tag(
            name=name,
            description=data.get("description", ""),
            color=data.get("color", "#3B82F6"),
            created_by=current_user.id,
            created_at=utc_now_isoformat()
        )
        
        from webapp.extensions import db
        db.session.add(tag)
        db.session.commit()
        
        self._log_action("tag_created", {"tag_id": tag.id, "name": tag.name})
        
        return self._success_response(
            self._serialize_tag(tag),
            _("Tag created successfully")
        )
    
    def _handle_tag_update(self, tag_id: int) -> Dict[str, Any]:
        """タグ更新処理."""
        tag = self._get_tag_or_404(tag_id)
        data = request.get_json() or {}
        
        updatable_fields = ["name", "description", "color"]
        updated_fields = []
        
        for field in updatable_fields:
            if field in data:
                if field == "name" and data[field] != tag.name:
                    # 重複チェック
                    existing = Tag.query.filter_by(name=data[field]).first()
                    if existing:
                        return self._error_response(_("Tag with this name already exists"))
                
                setattr(tag, field, data[field])
                updated_fields.append(field)
        
        if updated_fields:
            from webapp.extensions import db
            db.session.commit()
            
            self._log_action("tag_updated", {
                "tag_id": tag_id,
                "fields": updated_fields
            })
        
        return self._success_response(
            self._serialize_tag(tag),
            _("Tag updated successfully")
        )
    
    def _handle_tag_delete(self, tag_id: int) -> Dict[str, Any]:
        """タグ削除処理."""
        tag = self._get_tag_or_404(tag_id)
        
        from webapp.extensions import db
        # メディアとの関連を削除
        db.session.execute(
            media_tag.delete().where(media_tag.c.tag_id == tag_id)
        )
        
        # タグ削除
        db.session.delete(tag)
        db.session.commit()
        
        self._log_action("tag_deleted", {"tag_id": tag_id, "name": tag.name})
        
        return self._success_response(message=_("Tag deleted successfully"))
    
    def _handle_media_tags_update(self, media_id: int) -> Dict[str, Any]:
        """メディアタグ更新処理."""
        from core.models.photo_models import Media
        
        media = Media.query.get(media_id)
        if not media:
            return self._error_response(_("Media not found"), 404)
        
        data = request.get_json() or {}
        tag_ids = data.get("tag_ids", [])
        
        # 既存タグを削除
        from webapp.extensions import db
        db.session.execute(
            media_tag.delete().where(media_tag.c.media_id == media_id)
        )
        
        # 新しいタグを追加
        for tag_id in tag_ids:
            tag = Tag.query.get(tag_id)
            if tag:
                db.session.execute(
                    media_tag.insert().values(
                        media_id=media_id,
                        tag_id=tag_id
                    )
                )
        
        db.session.commit()
        
        self._log_action("media_tags_updated", {
            "media_id": media_id,
            "tag_count": len(tag_ids)
        })
        
        return self._success_response(message=_("Media tags updated successfully"))
    
    def _get_tag_or_404(self, tag_id: int) -> Tag:
        """タグ取得（404エラー付き）."""
        tag = Tag.query.get(tag_id)
        if not tag:
            abort(404, description=_("Tag not found"))
        return tag
    
    def _serialize_tag(self, tag: Tag) -> Dict[str, Any]:
        """タグシリアライゼーション."""
        return {
            "id": tag.id,
            "name": tag.name,
            "description": tag.description,
            "color": tag.color,
            "created_at": tag.created_at,
            "media_count": self._get_tag_media_count(tag.id)
        }
    
    def _get_tag_media_count(self, tag_id: int) -> int:
        """タグに関連するメディア数を取得."""
        from sqlalchemy import func, select
        from webapp.extensions import db
        
        return db.session.execute(
            select(func.count(media_tag.c.media_id))
            .where(media_tag.c.tag_id == tag_id)
        ).scalar() or 0