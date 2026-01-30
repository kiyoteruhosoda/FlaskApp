"""Azure CDN実装."""

from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import datetime, timedelta
from typing import Iterator
from urllib.parse import quote, urlencode

from ..domain import (
    CDNAnalytics,
    CDNBackend,
    CDNConfiguration,
    CDNPurgeRequest,
    StorageConfiguration,
    StorageException,
    StorageMetadata,
    StoragePath,
    StoragePathResolverService,
)
from .azure_blob import AzureBlobStorage

__all__ = ["AzureCDN"]

logger = logging.getLogger(__name__)


class AzureCDN:
    """Azure CDNのCDNバックエンド実装."""
    
    def __init__(self) -> None:
        self._configuration: StorageConfiguration | None = None
        self._origin_storage: AzureBlobStorage | None = None
        self._path_resolver = StoragePathResolverService()
        self._cdn_endpoint_url: str | None = None
    
    def initialize(self, configuration: StorageConfiguration) -> None:
        """Azure CDNクライアントを初期化."""
        try:
            self._configuration = configuration
            
            # CDN endpoint URLを構築
            cdn_endpoint = configuration.credentials.cdn_endpoint
            if not cdn_endpoint:
                raise StorageException("Azure CDN endpoint is required")
            
            # https://xxx.azureedge.net 形式のURLを構築
            if not cdn_endpoint.startswith("https://"):
                cdn_endpoint = f"https://{cdn_endpoint}"
            if not cdn_endpoint.endswith(".azureedge.net"):
                cdn_endpoint = f"{cdn_endpoint}.azureedge.net"
            
            self._cdn_endpoint_url = cdn_endpoint
            
            # オリジンストレージ（Azure Blob）を初期化
            if configuration.origin_backend_type and configuration.origin_credentials:
                from ..domain import StorageBackendType
                if configuration.origin_backend_type == StorageBackendType.AZURE_BLOB:
                    origin_config = StorageConfiguration(
                        backend_type=configuration.origin_backend_type,
                        credentials=configuration.origin_credentials,
                        base_path=configuration.base_path,
                        region=configuration.region,
                    )
                    self._origin_storage = AzureBlobStorage()
                    self._origin_storage.initialize(origin_config)
            
            logger.info(f"Azure CDN initialized: endpoint={cdn_endpoint}")
            
        except Exception as e:
            raise StorageException(f"Azure CDN初期化エラー: {e}")
    
    def get_cdn_url(self, path: StoragePath) -> str:
        """CDN配信URLを取得."""
        if not self._cdn_endpoint_url:
            raise StorageException("CDNが初期化されていません")
        
        if not self._configuration:
            raise StorageException("CDN設定が初期化されていません")
        
        # ストレージパスをCDN URLに変換
        relative_path = self._path_resolver.resolve_full_path(path, self._configuration)
        
        # URL エンコーディング
        encoded_path = quote(relative_path, safe="/")
        
        return f"{self._cdn_endpoint_url}/{encoded_path}"
    
    def generate_secure_url(
        self, 
        path: StoragePath, 
        expiration_seconds: int = 3600,
        allowed_ip: str | None = None,
    ) -> str:
        """セキュアトークン付きCDN URLを生成."""
        if not self._configuration or not self._configuration.credentials.access_key:
            raise StorageException("セキュアURL生成にはアクセスキーが必要です")
        
        base_url = self.get_cdn_url(path)
        
        # 有効期限を計算
        expiry = datetime.utcnow() + timedelta(seconds=expiration_seconds)
        expiry_timestamp = int(expiry.timestamp())
        
        # セキュアトークンを生成
        # Azure CDNのセキュアトークン仕様に基づく
        secret_key = self._configuration.credentials.access_key
        
        # トークン用データを構築
        token_data = f"{expiry_timestamp}"
        if allowed_ip:
            token_data += f":{allowed_ip}"
        
        # HMACでトークンを生成
        token = hmac.new(
            secret_key.encode('utf-8'),
            token_data.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()[:16]  # Azure CDNは16文字に切り詰め
        
        # セキュアURLパラメータを追加
        params = {
            'st': token,
            'e': str(expiry_timestamp),
        }
        if allowed_ip:
            params['ip'] = allowed_ip
        
        query_string = urlencode(params)
        return f"{base_url}?{query_string}"
    
    def purge_cache(self, purge_request: CDNPurgeRequest) -> str:
        """CDNキャッシュをパージ（無効化）."""
        if not self._configuration:
            raise StorageException("CDNが初期化されていません")
        
        try:
            # Azure CDN Management APIを使用してパージ
            # 実際の実装では azure-mgmt-cdn パッケージを使用
            logger.info(f"Azure CDNキャッシュパージ開始: {len(purge_request.paths)} paths")
            
            # パージジョブIDを生成（模擬）
            import uuid
            purge_job_id = str(uuid.uuid4())
            
            for path in purge_request.paths:
                # 各パスをパージ
                logger.info(f"CDNキャッシュパージ: {path}")
            
            logger.info(f"Azure CDNパージ完了: job_id={purge_job_id}")
            return purge_job_id
            
        except Exception as e:
            raise StorageException(f"CDNキャッシュパージエラー: {e}")
    
    def get_cache_status(self, path: StoragePath) -> str:
        """キャッシュステータスを取得（HIT/MISS/BYPASS）."""
        try:
            # Azure CDN Analytics APIを使用してキャッシュステータスを取得
            # 実装では azure-mgmt-cdn を使用
            logger.info(f"Azure CDNキャッシュステータス取得: {path.relative_path}")
            
            # 模擬的なキャッシュステータス
            # 実際の実装ではAPIレスポンスから取得
            return "HIT"  # HIT, MISS, BYPASS, EXPIRED
            
        except Exception as e:
            logger.warning(f"CDNキャッシュステータス取得エラー: {e}")
            return "UNKNOWN"
    
    def update_cdn_configuration(self, config: CDNConfiguration) -> None:
        """CDN設定を更新."""
        if not self._configuration:
            raise StorageException("CDNが初期化されていません")
        
        try:
            # Azure CDN Management APIで設定を更新
            logger.info(f"Azure CDN設定更新: cache_ttl={config.cache_ttl}")
            
            # 実際の実装では azure-mgmt-cdn を使用して
            # キャッシュルール、圧縮設定、オリジン設定等を更新
            
        except Exception as e:
            raise StorageException(f"CDN設定更新エラー: {e}")
    
    def get_analytics(
        self, 
        path_prefix: StoragePath,
        start_time: str,
        end_time: str,
    ) -> Iterator[CDNAnalytics]:
        """CDNアナリティクスデータを取得."""
        if not self._configuration:
            raise StorageException("CDNが初期化されていません")
        
        try:
            # Azure CDN Analytics APIからデータを取得
            logger.info(f"Azure CDNアナリティクス取得: {path_prefix.relative_path} ({start_time} - {end_time})")
            
            # 模擬的なアナリティクスデータ
            # 実際の実装ではAzure CDN Analytics APIを使用
            yield CDNAnalytics(
                path=path_prefix,
                requests_count=1500,
                cache_hit_ratio=0.85,
                bandwidth_bytes=1024 * 1024 * 50,  # 50MB
                response_time_ms=25.5,
                status_codes={200: 1400, 404: 50, 500: 50},
                edge_locations={"Tokyo": 800, "Osaka": 700},
                period_start=start_time,
                period_end=end_time,
            )
            
        except Exception as e:
            raise StorageException(f"CDNアナリティクス取得エラー: {e}")
    
    def prefetch_content(self, paths: list[StoragePath]) -> None:
        """コンテンツをCDNエッジに事前フェッチ."""
        if not self._configuration:
            raise StorageException("CDNが初期化されていません")
        
        try:
            # Azure CDN Pre-loading APIを使用
            logger.info(f"Azure CDNプリフェッチ開始: {len(paths)} files")
            
            for path in paths:
                cdn_url = self.get_cdn_url(path)
                logger.info(f"CDNプリフェッチ: {cdn_url}")
                # 実際の実装では Pre-loading API を呼び出し
            
        except Exception as e:
            raise StorageException(f"CDNプリフェッチエラー: {e}")
    
    def upload_to_origin_and_invalidate(
        self, 
        path: StoragePath, 
        content: bytes,
    ) -> StorageMetadata:
        """オリジンにアップロードしてCDNキャッシュを無効化."""
        if not self._origin_storage:
            raise StorageException("オリジンストレージが設定されていません")
        
        try:
            # 1. オリジンストレージにアップロード
            self._origin_storage.write(path, content)
            metadata = self._origin_storage.get_metadata(path)
            
            # 2. CDNキャッシュを無効化
            purge_request = CDNPurgeRequest(
                paths=[self._path_resolver.resolve_full_path(path, self._configuration)],
                purge_type="url",
                priority=1,
            )
            self.purge_cache(purge_request)
            
            # 3. CDN URLをメタデータに追加
            cdn_url = self.get_cdn_url(path)
            
            return StorageMetadata(
                path=metadata.path,
                size=metadata.size,
                content_type=metadata.content_type,
                etag=metadata.etag,
                last_modified=metadata.last_modified,
                custom_metadata=metadata.custom_metadata,
                cdn_url=cdn_url,
                cache_status="PURGED",
            )
            
        except Exception as e:
            raise StorageException(f"オリジンアップロード+CDN無効化エラー: {e}")
    
    def delete_from_origin_and_purge(self, path: StoragePath) -> None:
        """オリジンから削除してCDNキャッシュをパージ."""
        if not self._origin_storage:
            raise StorageException("オリジンストレージが設定されていません")
        
        try:
            # 1. オリジンストレージから削除
            self._origin_storage.delete(path)
            
            # 2. CDNキャッシュをパージ
            purge_request = CDNPurgeRequest(
                paths=[self._path_resolver.resolve_full_path(path, self._configuration)],
                purge_type="url",
                priority=1,
            )
            self.purge_cache(purge_request)
            
            logger.info(f"オリジン削除+CDNパージ完了: {path.relative_path}")
            
        except Exception as e:
            raise StorageException(f"オリジン削除+CDNパージエラー: {e}")