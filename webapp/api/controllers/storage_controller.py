"""Storage domain controller."""

import base64
import hashlib
imac
import mimetypes
import secrets
import time
from pathlib import Path
from typing import Dict, Any
from urllib.parse import quote

from flask import Blueprint, current_app, request, Response, send_file, abort
from flask_login import login_required
from flask_babel import gettext as _

from .base_controller import BaseController
from core.models.photo_models import Media, MediaPlayback
from core.storage_service import StorageArea, StorageService
from bounded_contexts.storage import StorageDomain, StorageIntent
from core.settings import settings


class StorageController(BaseController):
    """ストレージドメインコントローラー."""
    
    def _register_routes(self) -> None:
        """ストレージ関連のルートを登録."""
        
        @self.bp.get("/dl/<token>")
        def download_file(token: str):
            """署名付きURL経由でファイルダウンロード."""
            return self._handle_signed_download(token)
        
        @self.bp.get("/media/<int:media_id>/stream")
        @login_required
        def stream_media(media_id: int):
            """メディアストリーミング."""
            return self._handle_media_stream(media_id)
        
        @self.bp.post("/storage/upload")
        @login_required
        def upload_file():
            """ファイルアップロード."""
            return self._handle_file_upload()
        
        @self.bp.get("/storage/info")
        @login_required
        def storage_info():
            """ストレージ情報取得."""
            return self._handle_storage_info()
    
    def _handle_signed_download(self, token: str) -> Response:
        """署名付きダウンロード処理."""
        try:
            # トークン検証とペイロード解析
            payload = self._verify_download_token(token)
            
            media_id = payload.get("media_id")
            file_type = payload.get("type")  # "original", "thumbnail", "playback"
            size = payload.get("size")  # サムネイル用
            
            if not media_id or not file_type:
                abort(400, description=_("Invalid download token"))
            
            # メディア取得
            media = Media.query.get(media_id)
            if not media:
                abort(404, description=_("Media not found"))
            
            # ファイルパス取得とダウンロード実行
            return self._serve_media_file(media, file_type, size)
            
        except Exception as e:
            current_app.logger.error(f"署名付きダウンロードエラー: {e}")
            abort(403, description=_("Invalid or expired download token"))
    
    def _handle_media_stream(self, media_id: int) -> Response:
        """メディアストリーミング処理."""
        media = Media.query.get(media_id)
        if not media:
            abort(404, description=_("Media not found"))
        
        # 動画の場合は再生用ファイル、それ以外はオリジナル
        if media.mime_type.startswith("video/"):
            playback = MediaPlayback.query.filter_by(media_id=media_id).first()
            if playback:
                return self._serve_media_file(media, "playback")
        
        return self._serve_media_file(media, "original")
    
    def _handle_file_upload(self) -> Dict[str, Any]:
        """ファイルアップロード処理."""
        self._require_permission("media:upload")
        
        if "file" not in request.files:
            return self._error_response(_("No file provided"))
        
        file = request.files["file"]
        if file.filename == "":
            return self._error_response(_("No file selected"))
        
        try:
            # ファイル保存とメディア作成
            media = self._save_uploaded_file(file)
            
            self._log_action("file_uploaded", {
                "media_id": media.id,
                "filename": file.filename,
                "size": media.file_size
            })
            
            return self._success_response({
                "media_id": media.id,
                "filename": media.display_name,
                "size": media.file_size,
                "mime_type": media.mime_type
            })
            
        except Exception as e:
            current_app.logger.error(f"ファイルアップロードエラー: {e}")
            return self._error_response(_("File upload failed"))
    
    def _handle_storage_info(self) -> Dict[str, Any]:
        """ストレージ情報取得処理."""
        self._require_permission("admin")
        
        storage_service = StorageService()
        
        try:
            info = {
                "storage_areas": [],
                "cdn_enabled": settings.cdn_enabled,
                "blob_enabled": settings.blob_enabled
            }
            
            # 各ストレージエリアの情報を取得
            for area in [StorageArea.ORIGINALS, StorageArea.THUMBNAILS, StorageArea.PLAYBACK]:
                area_info = storage_service.get_area_info(area)
                info["storage_areas"].append({
                    "area": area.value,
                    "total_files": area_info.get("file_count", 0),
                    "total_size": area_info.get("total_size", 0),
                    "path": area_info.get("path", "")
                })
            
            return self._success_response(info)
            
        except Exception as e:
            current_app.logger.error(f"ストレージ情報取得エラー: {e}")
            return self._error_response(_("Failed to get storage info"))
    
    def _verify_download_token(self, token: str) -> Dict[str, Any]:
        """ダウンロードトークン検証."""
        try:
            # Base64デコード
            decoded_data = base64.b64decode(token)
            
            # 署名検証（HMAC-SHA256）
            secret_key = settings.secret_key.encode()
            
            # データと署名を分離
            signature = decoded_data[-32:]  # 最後の32バイトが署名
            data = decoded_data[:-32]
            
            # 署名検証
            expected_signature = hmac.new(secret_key, data, hashlib.sha256).digest()
            if not hmac.compare_digest(signature, expected_signature):
                raise ValueError("Invalid signature")
            
            # JSONデータをデシリアライズ
            import json
            payload = json.loads(data.decode())
            
            # 有効期限チェック
            if payload.get("expires", 0) < time.time():
                raise ValueError("Token expired")
            
            return payload
            
        except Exception as e:
            current_app.logger.warning(f"トークン検証失敗: {e}")
            raise ValueError("Invalid token") from e
    
    def _serve_media_file(self, media: Media, file_type: str, size: str = None) -> Response:
        """メディアファイル配信."""
        storage_service = StorageService()
        
        try:
            if file_type == "original":
                file_path = storage_service.get_file_path(StorageArea.ORIGINALS, media.relative_path)
                mime_type = media.mime_type
                
            elif file_type == "thumbnail":
                file_path = storage_service.get_thumbnail_path(media, size or "256")
                mime_type = "image/jpeg"
                
            elif file_type == "playback":
                playback = MediaPlayback.query.filter_by(media_id=media.id).first()
                if not playback:
                    abort(404, description=_("Playback file not found"))
                
                file_path = storage_service.get_file_path(StorageArea.PLAYBACK, playback.relative_path)
                mime_type = playback.mime_type or "video/mp4"
                
            else:
                abort(400, description=_("Invalid file type"))
            
            if not file_path or not Path(file_path).exists():
                abort(404, description=_("File not found"))
            
            return send_file(
                file_path,
                mimetype=mime_type,
                as_attachment=False,
                download_name=media.display_name
            )
            
        except Exception as e:
            current_app.logger.error(f"ファイル配信エラー: {e}")
            abort(500, description=_("File serving error"))
    
    def _save_uploaded_file(self, file) -> Media:
        """アップロードファイル保存."""
        from werkzeug.utils import secure_filename
        from core.tasks.local_import import SUPPORTED_EXTENSIONS
        from core.tasks.media_post_processing import enqueue_thumbs_generate
        
        # ファイル名とMIMEタイプ検証
        filename = secure_filename(file.filename)
        file_ext = Path(filename).suffix.lower()
        
        if file_ext not in SUPPORTED_EXTENSIONS:
            raise ValueError(_("Unsupported file type"))
        
        mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        
        # ストレージに保存
        storage_service = StorageService()
        relative_path = storage_service.generate_media_path(filename)
        
        # ファイル保存
        full_path = storage_service.get_file_path(StorageArea.ORIGINALS, relative_path)
        Path(full_path).parent.mkdir(parents=True, exist_ok=True)
        file.save(full_path)
        
        # メディアレコード作成
        from core.time import utc_now_isoformat
        from webapp.extensions import db
        
        media = Media(
            display_name=filename,
            original_filename=filename,
            mime_type=mime_type,
            file_size=Path(full_path).stat().st_size,
            relative_path=relative_path,
            created_at=utc_now_isoformat(),
            updated_at=utc_now_isoformat()
        )
        
        db.session.add(media)
        db.session.commit()
        
        # サムネイル生成を非同期でキューに追加
        enqueue_thumbs_generate(media.id)
        
        return media
    
    def _sign_payload(self, payload: Dict[str, Any]) -> str:
        """ペイロードに署名してトークン生成."""
        import json
        
        # JSONシリアライズ
        data = json.dumps(payload, separators=(',', ':')).encode()
        
        # HMAC署名
        secret_key = settings.secret_key.encode()
        signature = hmac.new(secret_key, data, hashlib.sha256).digest()
        
        # データと署名を結合してBase64エンコード
        signed_data = data + signature
        token = base64.b64encode(signed_data).decode()
        
        return token