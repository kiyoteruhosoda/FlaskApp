"""Media domain controller."""

import mimetypes
import os
from pathlib import Path
from typing import Dict, Any, Optional
from urllib.parse import quote

from flask import Blueprint, current_app, request, send_file, abort
from flask_login import login_required
from flask_babel import gettext as _
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload
from werkzeug.utils import secure_filename

from .base_controller import BaseController
from webapp.api.pagination import PaginationParams, paginate_and_respond
from core.models.photo_models import Media, MediaSidecar, MediaPlayback, Tag, media_tag
from core.tasks.local_import import SUPPORTED_EXTENSIONS, refresh_media_metadata_from_original
from core.tasks.media_post_processing import enqueue_thumbs_generate
from core.storage_service import StorageArea, StorageSelector, StorageService
from bounded_contexts.storage import StorageDomain, StorageIntent, StorageResolution
from core.time import utc_now_isoformat


class MediaController(BaseController):
    """メディアドメインコントローラー."""
    
    def _register_routes(self) -> None:
        """メディア関連のルートを登録."""
        
        @self.bp.get("/media")
        @login_required
        def list_media():
            """メディア一覧取得."""
            return self._handle_media_list()
        
        @self.bp.get("/media/<int:media_id>")
        @login_required
        def get_media(media_id: int):
            """メディア詳細取得."""
            return self._handle_media_detail(media_id)
        
        @self.bp.patch("/media/<int:media_id>")
        @login_required
        def update_media(media_id: int):
            """メディア更新."""
            return self._handle_media_update(media_id)
        
        @self.bp.delete("/media/<int:media_id>")
        @login_required
        def delete_media(media_id: int):
            """メディア削除."""
            return self._handle_media_delete(media_id)
        
        @self.bp.post("/media/bulk-actions")
        @login_required
        def bulk_actions():
            """メディア一括操作."""
            return self._handle_bulk_actions()
        
        @self.bp.get("/media/<int:media_id>/thumbnail")
        @login_required
        def get_thumbnail(media_id: int):
            """サムネイル取得."""
            return self._handle_thumbnail_get(media_id)
        
        @self.bp.post("/media/<int:media_id>/thumb-url")
        @login_required
        def get_thumbnail_url(media_id: int):
            """サムネイルURL生成."""
            return self._handle_thumbnail_url(media_id)
        
        @self.bp.post("/media/<int:media_id>/original-url")
        @login_required
        def get_original_url(media_id: int):
            """オリジナルファイルURL生成."""
            return self._handle_original_url(media_id)
        
        @self.bp.post("/media/<int:media_id>/playback-url")
        @login_required
        def get_playback_url(media_id: int):
            """再生用URL生成."""
            return self._handle_playback_url(media_id)
        
        @self.bp.post("/media/<int:media_id>/recover")
        @login_required
        def recover_media(media_id: int):
            """メディアリカバリ."""
            return self._handle_media_recover(media_id)
    
    def _handle_media_list(self) -> Dict[str, Any]:
        """メディア一覧処理."""
        self._log_action("media_list_request")
        
        # パラメータ取得
        pagination = PaginationParams.from_request(request)
        album_id = request.args.get("album_id", type=int)
        tag_id = request.args.get("tag_id", type=int)
        search_query = request.args.get("search", "").strip()
        media_type = request.args.get("type")  # "image", "video", etc.
        
        # クエリ構築
        query = self._build_media_query(album_id, tag_id, search_query, media_type)
        
        # ページネーション実行
        result = paginate_and_respond(
            query=query,
            pagination=pagination,
            serializer=self._serialize_media
        )
        
        self._log_action("media_list_success", {
            "count": len(result.get("data", [])),
            "album_id": album_id,
            "tag_id": tag_id
        })
        
        return result
    
    def _handle_media_detail(self, media_id: int) -> Dict[str, Any]:
        """メディア詳細処理."""
        media = self._get_media_or_404(media_id)
        
        self._log_action("media_detail", {"media_id": media_id})
        
        return self._success_response(self._serialize_media_detail(media))
    
    def _handle_media_update(self, media_id: int) -> Dict[str, Any]:
        """メディア更新処理."""
        media = self._get_media_or_404(media_id)
        data = request.get_json() or {}
        
        # 更新可能フィールド
        updatable_fields = ["display_name", "description", "date_taken", "location"]
        updated_fields = []
        
        for field in updatable_fields:
            if field in data:
                setattr(media, field, data[field])
                updated_fields.append(field)
        
        if updated_fields:
            media.updated_at = utc_now_isoformat()
            self._commit_changes()
            
            self._log_action("media_updated", {
                "media_id": media_id,
                "fields": updated_fields
            })
        
        return self._success_response(
            self._serialize_media_detail(media),
            _("Media updated successfully")
        )
    
    def _handle_media_delete(self, media_id: int) -> Dict[str, Any]:
        """メディア削除処理."""
        media = self._get_media_or_404(media_id)
        
        # ストレージからファイル削除
        self._delete_media_files(media)
        
        # DB削除
        from webapp.extensions import db
        db.session.delete(media)
        self._commit_changes()
        
        self._log_action("media_deleted", {"media_id": media_id})
        
        return self._success_response(message=_("Media deleted successfully"))
    
    def _handle_bulk_actions(self) -> Dict[str, Any]:
        """一括操作処理."""
        data = request.get_json() or {}
        action = data.get("action")
        media_ids = data.get("media_ids", [])
        
        if not action or not media_ids:
            return self._error_response(_("Action and media_ids are required"))
        
        processed_count = 0
        
        if action == "delete":
            processed_count = self._bulk_delete_media(media_ids)
        elif action == "add_tags":
            tag_ids = data.get("tag_ids", [])
            processed_count = self._bulk_add_tags(media_ids, tag_ids)
        elif action == "remove_tags":
            tag_ids = data.get("tag_ids", [])
            processed_count = self._bulk_remove_tags(media_ids, tag_ids)
        else:
            return self._error_response(_("Unsupported bulk action"))
        
        self._log_action("bulk_action", {
            "action": action,
            "media_count": len(media_ids),
            "processed": processed_count
        })
        
        return self._success_response({
            "processed_count": processed_count,
            "total_count": len(media_ids)
        })
    
    def _handle_thumbnail_get(self, media_id: int):
        """サムネイル取得処理."""
        media = self._get_media_or_404(media_id)
        
        size = request.args.get("size", "256", type=str)
        if size not in ["256", "1024", "2048"]:
            size = "256"
        
        # Storage Service経由でサムネイル取得
        storage_service = StorageService()
        
        try:
            thumbnail_path = storage_service.get_thumbnail_path(media, size)
            if not thumbnail_path or not os.path.exists(thumbnail_path):
                # サムネイル生成をキューに追加
                enqueue_thumbs_generate(media.id)
                abort(404, description=_("Thumbnail not found"))
            
            return send_file(
                thumbnail_path,
                mimetype=f"image/jpeg",
                as_attachment=False
            )
            
        except Exception as e:
            current_app.logger.error(f"サムネイル取得エラー: {e}")
            abort(500, description=_("Thumbnail generation error"))
    
    def _handle_thumbnail_url(self, media_id: int) -> Dict[str, Any]:
        """サムネイルURL生成."""
        media = self._get_media_or_404(media_id)
        data = request.get_json() or {}
        size = data.get("size", "256")
        
        # CDN/ストレージ経由でURL生成
        storage_domain = StorageDomain()
        
        try:
            url = storage_domain.get_media_url(
                media,
                StorageIntent.THUMBNAIL,
                {"size": size}
            )
            
            return self._success_response({
                "url": url,
                "expires_in": 3600  # 1時間
            })
            
        except Exception as e:
            return self._error_response(_("Failed to generate thumbnail URL"))
    
    def _handle_original_url(self, media_id: int) -> Dict[str, Any]:
        """オリジナルURL生成."""
        media = self._get_media_or_404(media_id)
        
        storage_domain = StorageDomain()
        
        try:
            url = storage_domain.get_media_url(
                media,
                StorageIntent.ORIGINAL
            )
            
            return self._success_response({
                "url": url,
                "expires_in": 3600
            })
            
        except Exception as e:
            return self._error_response(_("Failed to generate original URL"))
    
    def _handle_playback_url(self, media_id: int) -> Dict[str, Any]:
        """再生用URL生成."""
        media = self._get_media_or_404(media_id)
        
        if not media.mime_type.startswith("video/"):
            return self._error_response(_("Playback URL only available for videos"))
        
        storage_domain = StorageDomain()
        
        try:
            url = storage_domain.get_media_url(
                media,
                StorageIntent.PLAYBACK
            )
            
            return self._success_response({
                "url": url,
                "expires_in": 3600
            })
            
        except Exception as e:
            return self._error_response(_("Failed to generate playback URL"))
    
    def _handle_media_recover(self, media_id: int) -> Dict[str, Any]:
        """メディアリカバリ処理."""
        media = self._get_media_or_404(media_id)
        
        try:
            # メタデータリフレッシュ
            refresh_media_metadata_from_original(media.id)
            
            # サムネイル再生成
            enqueue_thumbs_generate(media.id)
            
            self._log_action("media_recover", {"media_id": media_id})
            
            return self._success_response(
                message=_("Media recovery initiated")
            )
            
        except Exception as e:
            return self._error_response(_("Media recovery failed"))
    
    # ヘルパーメソッド
    
    def _get_media_or_404(self, media_id: int) -> Media:
        """メディア取得（404エラー付き）."""
        media = Media.query.filter_by(id=media_id).first()
        if not media:
            abort(404, description=_("Media not found"))
        return media
    
    def _build_media_query(self, album_id: Optional[int], tag_id: Optional[int], 
                          search_query: str, media_type: Optional[str]):
        """メディア検索クエリ構築."""
        query = Media.query.options(
            joinedload(Media.sidecar),
            joinedload(Media.tags)
        )
        
        if album_id:
            from core.models.photo_models import album_item
            query = query.join(album_item).filter(album_item.c.album_id == album_id)
        
        if tag_id:
            query = query.join(media_tag).filter(media_tag.c.tag_id == tag_id)
        
        if search_query:
            query = query.filter(
                Media.display_name.ilike(f"%{search_query}%") |
                Media.description.ilike(f"%{search_query}%")
            )
        
        if media_type:
            if media_type == "image":
                query = query.filter(Media.mime_type.like("image/%"))
            elif media_type == "video":
                query = query.filter(Media.mime_type.like("video/%"))
        
        return query.order_by(Media.date_taken.desc(), Media.id.desc())
    
    def _serialize_media(self, media: Media) -> Dict[str, Any]:
        """メディアシリアライゼーション."""
        return {
            "id": media.id,
            "display_name": media.display_name,
            "mime_type": media.mime_type,
            "file_size": media.file_size,
            "date_taken": media.date_taken.isoformat() if media.date_taken else None,
            "width": media.width,
            "height": media.height,
            "duration": getattr(media, 'duration', None),
            "thumbnail_url": f"/api/media/{media.id}/thumbnail?size=256",
            "tags": [{"id": tag.id, "name": tag.name} for tag in media.tags]
        }
    
    def _serialize_media_detail(self, media: Media) -> Dict[str, Any]:
        """メディア詳細シリアライゼーション."""
        data = self._serialize_media(media)
        data.update({
            "description": media.description,
            "location": media.location,
            "created_at": media.created_at,
            "updated_at": media.updated_at,
            "exif": media.sidecar.exif_data if media.sidecar else None,
            "has_playback": bool(MediaPlayback.query.filter_by(media_id=media.id).first())
        })
        return data
    
    def _commit_changes(self):
        """DB変更をコミット."""
        from webapp.extensions import db
        db.session.commit()
    
    def _bulk_delete_media(self, media_ids: list) -> int:
        """メディア一括削除."""
        deleted_count = 0
        for media_id in media_ids:
            try:
                media = Media.query.get(media_id)
                if media:
                    self._delete_media_files(media)
                    from webapp.extensions import db
                    db.session.delete(media)
                    deleted_count += 1
            except Exception as e:
                current_app.logger.error(f"メディア削除エラー {media_id}: {e}")
        
        self._commit_changes()
        return deleted_count
    
    def _bulk_add_tags(self, media_ids: list, tag_ids: list) -> int:
        """タグ一括追加."""
        processed_count = 0
        for media_id in media_ids:
            try:
                media = Media.query.get(media_id)
                if media:
                    for tag_id in tag_ids:
                        tag = Tag.query.get(tag_id)
                        if tag and tag not in media.tags:
                            media.tags.append(tag)
                    processed_count += 1
            except Exception as e:
                current_app.logger.error(f"タグ追加エラー {media_id}: {e}")
        
        self._commit_changes()
        return processed_count
    
    def _bulk_remove_tags(self, media_ids: list, tag_ids: list) -> int:
        """タグ一括削除."""
        processed_count = 0
        for media_id in media_ids:
            try:
                media = Media.query.get(media_id)
                if media:
                    for tag_id in tag_ids:
                        tag = Tag.query.get(tag_id)
                        if tag and tag in media.tags:
                            media.tags.remove(tag)
                    processed_count += 1
            except Exception as e:
                current_app.logger.error(f"タグ削除エラー {media_id}: {e}")
        
        self._commit_changes()
        return processed_count
    
    def _delete_media_files(self, media: Media):
        """メディアファイル削除."""
        storage_service = StorageService()
        try:
            # オリジナルファイル削除
            storage_service.delete_file(StorageArea.ORIGINALS, media.relative_path)
            
            # サムネイル削除
            for size in ["256", "1024", "2048"]:
                storage_service.delete_thumbnail(media, size)
            
            # 再生用ファイル削除
            playback = MediaPlayback.query.filter_by(media_id=media.id).first()
            if playback:
                storage_service.delete_file(StorageArea.PLAYBACK, playback.relative_path)
                
        except Exception as e:
            current_app.logger.warning(f"ファイル削除エラー: {e}")