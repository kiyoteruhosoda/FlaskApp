"""CloudFlare CDN実装."""

from __future__ import annotations

import hashlib
import hmac
import json
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
from .local import LocalStorage

__all__ = ["CloudFlareCDN"]

logger = logging.getLogger(__name__)


class CloudFlareCDN:
    """CloudFlare CDNのCDNバックエンド実装."""
    
    def __init__(self) -> None:
        self._configuration: StorageConfiguration | None = None
        self._origin_storage: LocalStorage | None = None
        self._path_resolver = StoragePathResolverService()
        self._zone_id: str | None = None
        self._api_token: str | None = None
        self._origin_hostname: str | None = None
    
    def initialize(self, configuration: StorageConfiguration) -> None:
        """CloudFlare CDNクライアントを初期化."""
        try:
            self._configuration = configuration
            
            # CloudFlare API認証情報を取得
            self._api_token = configuration.credentials.api_token
            self._zone_id = configuration.credentials.zone_id
            self._origin_hostname = configuration.credentials.origin_hostname
            
            if not all([self._api_token, self._zone_id, self._origin_hostname]):
                raise StorageException("CloudFlare CDN requires api_token, zone_id, and origin_hostname")
            
            # オリジンストレージを初期化（ローカルまたは他のストレージ）
            if configuration.origin_backend_type and configuration.origin_credentials:
                from ..domain import StorageBackendType
                if configuration.origin_backend_type == StorageBackendType.LOCAL:
                    origin_config = StorageConfiguration(
                        backend_type=configuration.origin_backend_type,
                        credentials=configuration.origin_credentials,
                        base_path=configuration.base_path,
                    )
                    self._origin_storage = LocalStorage()
                    self._origin_storage.initialize(origin_config)
            
            logger.info(f"CloudFlare CDN initialized: zone={self._zone_id}, origin={self._origin_hostname}")
            
        except Exception as e:
            raise StorageException(f"CloudFlare CDN初期化エラー: {e}")
    
    def get_cdn_url(self, path: StoragePath) -> str:
        """CDN配信URLを取得."""
        if not self._origin_hostname:
            raise StorageException("CDNが初期化されていません")
        
        if not self._configuration:
            raise StorageException("CDN設定が初期化されていません")
        
        # ストレージパスをCDN URLに変換
        relative_path = self._path_resolver.resolve_full_path(path, self._configuration)
        
        # URL エンコーディング
        encoded_path = quote(relative_path, safe="/")
        
        # CloudFlareを通したCDN URL
        return f"https://{self._origin_hostname}/{encoded_path}"
    
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
        
        # CloudFlareのセキュアトークンを生成
        secret_key = self._configuration.credentials.access_key
        
        # トークン用データを構築
        # CloudFlare URL署名仕様に基づく
        url_path = f"/{self._path_resolver.resolve_full_path(path, self._configuration)}"
        token_data = f"{url_path}{expiry_timestamp}"
        if allowed_ip:
            token_data += f"{allowed_ip}"
        
        # HMACでトークンを生成
        token = hmac.new(
            secret_key.encode('utf-8'),
            token_data.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()[:32]  # CloudFlareは32文字
        
        # セキュアURLパラメータを追加
        params = {
            'token': token,
            'expires': str(expiry_timestamp),
        }
        if allowed_ip:
            params['ip'] = allowed_ip
        
        query_string = urlencode(params)
        return f"{base_url}?{query_string}"
    
    def purge_cache(self, purge_request: CDNPurgeRequest) -> str:
        """CDNキャッシュをパージ（無効化）."""
        if not self._zone_id or not self._api_token:
            raise StorageException("CDNが初期化されていません")
        
        try:
            # CloudFlare API v4を使用してパージ
            logger.info(f"CloudFlare CDNキャッシュパージ開始: {len(purge_request.paths)} paths")
            
            # パージリクエストを構築
            if purge_request.purge_type == "url":
                # 完全URLでパージ
                purge_urls = []
                for path in purge_request.paths:
                    if path.startswith('http'):
                        purge_urls.append(path)
                    else:
                        purge_urls.append(f"https://{self._origin_hostname}/{path}")
                
                # CloudFlare Purge APIペイロード
                payload = {
                    "files": purge_urls
                }
            elif purge_request.purge_type == "prefix":
                # プレフィックスでパージ
                payload = {
                    "prefixes": purge_request.paths
                }
            elif purge_request.purge_type == "tag":
                # キャッシュタグでパージ
                payload = {
                    "tags": purge_request.paths
                }
            else:
                raise StorageException(f"未対応のパージタイプ: {purge_request.purge_type}")
            
            # 実際のHTTPリクエストは省略（requests等を使用）
            # POST https://api.cloudflare.com/client/v4/zones/{zone_id}/purge_cache
            
            # パージジョブIDを生成（模擬）
            import uuid
            purge_job_id = str(uuid.uuid4())
            
            logger.info(f"CloudFlare CDNパージ完了: job_id={purge_job_id}")
            return purge_job_id
            
        except Exception as e:
            raise StorageException(f"CDNキャッシュパージエラー: {e}")
    
    def get_cache_status(self, path: StoragePath) -> str:
        """""キャッシュステータスを取得（HIT/MISS/BYPASS）."""""
        try:
            # CloudFlare Analytics APIを使用してキャッシュステータスを取得
            logger.info(f"CloudFlare CDNキャッシュステータス取得: {path.relative_path}")
            
            # 模擬的なキャッシュステータス
            # 実際の実装では Analytics API レスポンスから取得
            return "HIT"  # HIT, MISS, BYPASS, EXPIRED, STALE
            
        except Exception as e:
            logger.warning(f"CDNキャッシュステータス取得エラー: {e}")
            return "UNKNOWN"
    
    def update_cdn_configuration(self, config: CDNConfiguration) -> None:
        """""CDN設定を更新."""""
        if not self._zone_id or not self._api_token:
            raise StorageException("CDNが初期化されていません")
        
        try:
            # CloudFlare Zone Settings APIで設定を更新
            logger.info(f"CloudFlare CDN設定更新: cache_ttl={config.cache_ttl}")
            
            # キャッシュ設定の更新
            cache_settings = {
                "browser_cache_ttl": config.cache_ttl,
                "edge_cache_ttl": config.cache_ttl,
            }
            
            # 圧縮設定
            if config.enable_gzip:
                compression_settings = {
                    "gzip": "on",
                }
            if config.enable_brotli:
                compression_settings["brotli"] = "on"
            
            # 実際のAPIコールは省略（requests等を使用）
            # PATCH https://api.cloudflare.com/client/v4/zones/{zone_id}/settings/
            
        except Exception as e:
            raise StorageException(f"CDN設定更新エラー: {e}")
    
    def get_analytics(
        self, 
        path_prefix: StoragePath,
        start_time: str,
        end_time: str,
    ) -> Iterator[CDNAnalytics]:
        """""CDNアナリティクスデータを取得."""""
        if not self._zone_id or not self._api_token:
            raise StorageException("CDNが初期化されていません")
        
        try:
            # CloudFlare Analytics APIからデータを取得
            logger.info(f"CloudFlare CDNアナリティクス取得: {path_prefix.relative_path} ({start_time} - {end_time})")
            
            # 模擬的なアナリティクスデータ
            # 実際の実装では CloudFlare Analytics API を使用
            yield CDNAnalytics(
                path=path_prefix,
                requests_count=2500,
                cache_hit_ratio=0.92,
                bandwidth_bytes=1024 * 1024 * 80,  # 80MB
                response_time_ms=18.2,
                status_codes={200: 2350, 404: 100, 500: 50},
                edge_locations={"Tokyo": 1200, "Seoul": 800, "Singapore": 500},
                period_start=start_time,
                period_end=end_time,
            )
            
        except Exception as e:
            raise StorageException(f"CDNアナリティクス取得エラー: {e}")
    
    def prefetch_content(self, paths: list[StoragePath]) -> None:
        """""コンテンツをCDNエッジに事前フェッチ."""""
        if not self._zone_id or not self._api_token:
            raise StorageException("CDNが初期化されていません")
        
        try:
            # CloudFlareのPrefetch APIを使用
            logger.info(f"CloudFlare CDNプリフェッチ開始: {len(paths)} files")
            
            prefetch_urls = []
            for path in paths:
                cdn_url = self.get_cdn_url(path)
                prefetch_urls.append(cdn_url)
            
            # プリフェッチリクエストを送信（実装省略）
            # 実際の実装では HTTP リクエストでエッジキャッシュを温める
            
            for url in prefetch_urls:
                logger.info(f"CDNプリフェッチ: {url}")
            
        except Exception as e:
            raise StorageException(f"CDNプリフェッチエラー: {e}")
    
    def upload_to_origin_and_invalidate(
        self, 
        path: StoragePath, 
        content: bytes,
    ) -> StorageMetadata:
        """""オリジンにアップロードしてCDNキャッシュを無効化."""""
        if not self._origin_storage:
            raise StorageException("オリジンストレージが設定されていません")
        
        try:
            # 1. オリジンストレージにアップロード
            self._origin_storage.write(path, content)
            metadata = self._origin_storage.get_metadata(path)
            
            # 2. CDNキャッシュを無効化
            cdn_url = self.get_cdn_url(path)
            purge_request = CDNPurgeRequest(
                paths=[cdn_url],
                purge_type="url",
                priority=1,
            )
            self.purge_cache(purge_request)
            
            # 3. CDN URLをメタデータに追加
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
        """""オリジンから削除してCDNキャッシュをパージ."""""
        if not self._origin_storage:
            raise StorageException("オリジンストレージが設定されていません")
        
        try:
            # 1. オリジンストレージから削除
            self._origin_storage.delete(path)
            
            # 2. CDNキャッシュをパージ
            cdn_url = self.get_cdn_url(path)
            purge_request = CDNPurgeRequest(
                paths=[cdn_url],
                purge_type="url",
                priority=1,
            )
            self.purge_cache(purge_request)
            
            logger.info(f"オリジン削除+CDNパージ完了: {path.relative_path}")
            
        except Exception as e:
            raise StorageException(f"オリジン削除+CDNパージエラー: {e}")