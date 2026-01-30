"""Storage境界文脈のアプリケーションサービス."""

from __future__ import annotations

import logging
from typing import IO, Iterator

from core.settings import settings

from ..domain import (
    CDNBackend,
    StorageBackend,
    StorageBackendType,
    StorageConfiguration,
    StorageCredentials,
    StorageException,
    StorageMetadata,
    StoragePath,
    StorageRepository,
)
from ..infrastructure import AzureBlobStorage, AzureCDN, CloudFlareCDN, LocalStorage

__all__ = ["StorageApplicationService", "StorageBackendFactory"]

logger = logging.getLogger(__name__)


class StorageBackendFactory:
    """ストレージバックエンドファクトリ - ポリモーフィズムの実現."""
    
    @staticmethod
    def create_backend(configuration: StorageConfiguration) -> StorageBackend | CDNBackend:
        """設定に基づいてストレージバックエンドを作成."""
        backend_type = configuration.backend_type
        
        # Storage backends
        if backend_type.value == "local":
            backend = LocalStorage()
        elif backend_type.value == "azure_blob":
            backend = AzureBlobStorage()
        
        # CDN backends
        elif backend_type.value == "azure_cdn":
            backend = AzureCDN()
        elif backend_type.value == "cloudflare_cdn":
            backend = CloudFlareCDN()
        
        else:
            raise StorageException(f"未対応のバックエンドタイプ: {backend_type}")
        
        # バックエンドを初期化
        backend.initialize(configuration)
        return backend


class StorageApplicationService:
    """Storage境界文脈のアプリケーションサービス - ユースケース実行層."""
    
    def __init__(
        self,
        repository: StorageRepository,
        backend_factory: StorageBackendFactory | None = None,
    ) -> None:
        self._repository = repository
        self._factory = backend_factory or StorageBackendFactory()
        self._backends: dict[str, StorageBackend | CDNBackend] = {}
    
    # =============================================================
    # 設定管理ユースケース
    # =============================================================
    
    def configure_storage(
        self,
        domain: str,
        configuration: StorageConfiguration,
    ) -> None:
        """ストレージドメイン設定を保存."""
        try:
            # 設定の妥当性を検証（バックエンド作成試行）
            self._factory.create_backend(configuration)
            
            # 設定を永続化
            self._repository.save_configuration(domain, configuration)
            
            # 既存のバックエンドキャッシュをクリア
            if domain in self._backends:
                del self._backends[domain]
            
            logger.info(f"Storage設定を保存: domain={domain}, backend={configuration.backend_type.value}")
        except Exception as e:
            logger.error(f"Storage設定保存エラー: domain={domain}, error={e}")
            raise StorageException(f"Storage設定保存エラー: {e}")
    
    def get_storage_domains(self) -> list[str]:
        """設定済みストレージドメイン一覧を取得."""
        return self._repository.list_domains()
    
    def remove_storage_configuration(self, domain: str) -> None:
        """ストレージドメイン設定を削除."""
        try:
            self._repository.delete_configuration(domain)
            
            if domain in self._backends:
                del self._backends[domain]
            
            logger.info(f"Storage設定を削除: domain={domain}")
        except Exception as e:
            logger.error(f"Storage設定削除エラー: domain={domain}, error={e}")
            raise StorageException(f"Storage設定削除エラー: {e}")
    
    # =============================================================
    # ストレージ操作ユースケース
    # =============================================================
    
    def upload_file(
        self,
        domain: str,
        storage_path: StoragePath,
        content: bytes,
    ) -> StorageMetadata:
        """ファイルをアップロード."""
        try:
            backend = self._get_backend(domain)
            backend.write(storage_path, content)
            
            metadata = backend.get_metadata(storage_path)
            logger.info(f"ファイルアップロード: domain={domain}, path={storage_path.relative_path}, size={metadata.size}")
            return metadata
        except Exception as e:
            logger.error(f"ファイルアップロードエラー: domain={domain}, path={storage_path.relative_path}, error={e}")
            raise
    
    def upload_file_stream(
        self,
        domain: str,
        storage_path: StoragePath,
        stream: IO[bytes],
    ) -> StorageMetadata:
        """ストリーミングでファイルをアップロード."""
        try:
            backend = self._get_backend(domain)
            backend.write_stream(storage_path, stream)
            
            metadata = backend.get_metadata(storage_path)
            logger.info(f"ストリームアップロード: domain={domain}, path={storage_path.relative_path}, size={metadata.size}")
            return metadata
        except Exception as e:
            logger.error(f"ストリームアップロードエラー: domain={domain}, path={storage_path.relative_path}, error={e}")
            raise
    
    def download_file(
        self,
        domain: str,
        storage_path: StoragePath,
    ) -> bytes:
        """ファイルをダウンロード."""
        try:
            backend = self._get_backend(domain)
            content = backend.read(storage_path)
            
            logger.info(f"ファイルダウンロード: domain={domain}, path={storage_path.relative_path}, size={len(content)}")
            return content
        except Exception as e:
            logger.error(f"ファイルダウンロードエラー: domain={domain}, path={storage_path.relative_path}, error={e}")
            raise
    
    def download_file_stream(
        self,
        domain: str,
        storage_path: StoragePath,
    ) -> IO[bytes]:
        """ストリーミングでファイルをダウンロード."""
        try:
            backend = self._get_backend(domain)
            stream = backend.read_stream(storage_path)
            
            logger.info(f"ストリームダウンロード: domain={domain}, path={storage_path.relative_path}")
            return stream
        except Exception as e:
            logger.error(f"ストリームダウンロードエラー: domain={domain}, path={storage_path.relative_path}, error={e}")
            raise
    
    def get_file_metadata(
        self,
        domain: str,
        storage_path: StoragePath,
    ) -> StorageMetadata:
        """ファイルメタデータを取得."""
        try:
            backend = self._get_backend(domain)
            return backend.get_metadata(storage_path)
        except Exception as e:
            logger.error(f"メタデータ取得エラー: domain={domain}, path={storage_path.relative_path}, error={e}")
            raise
    
    def file_exists(
        self,
        domain: str,
        storage_path: StoragePath,
    ) -> bool:
        """ファイル存在チェック."""
        try:
            backend = self._get_backend(domain)
            return backend.exists(storage_path)
        except Exception as e:
            logger.error(f"存在チェックエラー: domain={domain}, path={storage_path.relative_path}, error={e}")
            return False
    
    def copy_file(
        self,
        source_domain: str,
        source_path: StoragePath,
        destination_domain: str,
        destination_path: StoragePath,
    ) -> StorageMetadata:
        """ファイルをコピー（ドメイン間対応）."""
        try:
            if source_domain == destination_domain:
                # 同一ドメイン内コピー
                backend = self._get_backend(source_domain)
                backend.copy(source_path, destination_path)
            else:
                # 異なるドメイン間のコピー（ダウンロード→アップロード）
                content = self.download_file(source_domain, source_path)
                return self.upload_file(destination_domain, destination_path, content)
            
            # メタデータを返す
            return self.get_file_metadata(destination_domain, destination_path)
        except Exception as e:
            logger.error(f"ファイルコピーエラー: {source_domain}:{source_path.relative_path} -> {destination_domain}:{destination_path.relative_path}, error={e}")
            raise
    
    def delete_file(
        self,
        domain: str,
        storage_path: StoragePath,
    ) -> None:
        """ファイルを削除."""
        try:
            backend = self._get_backend(domain)
            backend.delete(storage_path)
            
            logger.info(f"ファイル削除: domain={domain}, path={storage_path.relative_path}")
        except Exception as e:
            logger.error(f"ファイル削除エラー: domain={domain}, path={storage_path.relative_path}, error={e}")
            raise
    
    def list_files(
        self,
        domain: str,
        path_prefix: StoragePath,
    ) -> Iterator[StorageMetadata]:
        """ファイル一覧を取得."""
        try:
            backend = self._get_backend(domain)
            return backend.list_objects(path_prefix)
        except Exception as e:
            logger.error(f"ファイル一覧取得エラー: domain={domain}, prefix={path_prefix.relative_path}, error={e}")
            raise
    
    def generate_download_url(
        self,
        domain: str,
        storage_path: StoragePath,
        expiration_seconds: int = 3600,
    ) -> str:
        """ダウンロード用署名付きURLを生成."""
        try:
            backend = self._get_backend(domain)
            url = backend.generate_presigned_url(storage_path, expiration_seconds, "GET")
            
            logger.info(f"署名付きURL生成: domain={domain}, path={storage_path.relative_path}")
            return url
        except Exception as e:
            logger.error(f"署名付きURL生成エラー: domain={domain}, path={storage_path.relative_path}, error={e}")
            raise
    
    def generate_upload_url(
        self,
        domain: str,
        storage_path: StoragePath,
        expiration_seconds: int = 3600,
    ) -> str:
        """アップロード用署名付きURLを生成."""
        try:
            backend = self._get_backend(domain)
            url = backend.generate_presigned_url(storage_path, expiration_seconds, "PUT")
            
            logger.info(f"アップロード署名付きURL生成: domain={domain}, path={storage_path.relative_path}")
            return url
        except Exception as e:
            logger.error(f"アップロード署名付きURL生成エラー: domain={domain}, path={storage_path.relative_path}, error={e}")
            raise
    
    # =============================================================
    # CDN専用ユースケース
    # =============================================================
    
    def get_cdn_url(
        self,
        domain: str,
        storage_path: StoragePath,
    ) -> str:
        """CDN配信URLを取得（システム設定を考慮）."""
        try:
            # システム設定でCDNが無効になっている場合
            if not settings.cdn_enabled or settings.cdn_provider == "none":
                logger.info(f"CDNが無効のため通常URLを返却: domain={domain}")
                return self.generate_download_url(domain, storage_path)
            
            # CDN設定に基づいて自動的にCDNバックエンドを作成
            cdn_backend = self._get_cdn_backend_from_settings(domain)
            if cdn_backend:
                try:
                    url = cdn_backend.get_cdn_url(storage_path)
                    logger.info(f"CDN URL取得: domain={domain}, path={storage_path.relative_path}")
                    return url
                except Exception as cdn_error:
                    logger.warning(f"CDN URL取得失敗、通常URLにフォールバック: domain={domain}, error={cdn_error}")
                    # CDN失敗時は通常URLにフォールバック
                    return self.generate_download_url(domain, storage_path)
            
            # 明示的にCDNが設定されたドメインの場合
            backend = self._get_backend(domain)
            
            # CDNバックエンドでなければ通常のURLを返す
            if not hasattr(backend, 'get_cdn_url'):
                return self.generate_download_url(domain, storage_path)
            
            url = backend.get_cdn_url(storage_path)
            logger.info(f"CDN URL取得: domain={domain}, path={storage_path.relative_path}")
            return url
        except Exception as e:
            logger.error(f"CDN URL取得エラー: domain={domain}, path={storage_path.relative_path}, error={e}")
            # 最終的なフォールバック
            return self.generate_download_url(domain, storage_path)
    
    def generate_secure_cdn_url(
        self,
        domain: str,
        storage_path: StoragePath,
        expiration_seconds: int = 3600,
        allowed_ip: str | None = None,
    ) -> str:
        """セキュアトークン付きCDN URLを生成."""
        try:
            backend = self._get_backend(domain)
            
            # CDNバックエンドでなければ通常の署名付きURLを返す
            if not hasattr(backend, 'generate_secure_url'):
                return self.generate_download_url(domain, storage_path, expiration_seconds)
            
            url = backend.generate_secure_url(storage_path, expiration_seconds, allowed_ip)
            logger.info(f"セキュアCDN URL生成: domain={domain}, path={storage_path.relative_path}")
            return url
        except Exception as e:
            logger.error(f"セキュアCDN URL生成エラー: domain={domain}, path={storage_path.relative_path}, error={e}")
            raise
    
    def purge_cdn_cache(
        self,
        domain: str,
        paths: list[StoragePath],
        purge_type: str = "url",
        priority: int = 1,
    ) -> str:
        """CDNキャッシュをパージ."""
        try:
            backend = self._get_backend(domain)
            
            if not hasattr(backend, 'purge_cache'):
                raise StorageException(f"ドメイン '{domain}' はCDNバックエンドではありません")
            
            from ..domain import CDNPurgeRequest
            purge_request = CDNPurgeRequest(
                paths=[path.relative_path for path in paths],
                purge_type=purge_type,
                priority=priority,
            )
            
            job_id = backend.purge_cache(purge_request)
            logger.info(f"CDNキャッシュパージ: domain={domain}, paths={len(paths)}, job_id={job_id}")
            return job_id
        except Exception as e:
            logger.error(f"CDNキャッシュパージエラー: domain={domain}, error={e}")
            raise
    
    def upload_and_distribute(
        self,
        domain: str,
        storage_path: StoragePath,
        content: bytes,
    ) -> StorageMetadata:
        """オリジンにアップロードしてCDNで配信開始."""
        try:
            backend = self._get_backend(domain)
            
            # CDNバックエンドの場合はオリジン連携機能を使用
            if hasattr(backend, 'upload_to_origin_and_invalidate'):
                metadata = backend.upload_to_origin_and_invalidate(storage_path, content)
                logger.info(f"CDNアップロード＋配信: domain={domain}, path={storage_path.relative_path}")
                return metadata
            else:
                # 通常のストレージバックエンドの場合
                return self.upload_file(domain, storage_path, content)
                
        except Exception as e:
            logger.error(f"CDNアップロード＋配信エラー: domain={domain}, path={storage_path.relative_path}, error={e}")
            raise
    
    def get_cdn_analytics(
        self,
        domain: str,
        path_prefix: StoragePath,
        start_time: str,
        end_time: str,
    ) -> list:
        """CDNアナリティクスデータを取得."""
        try:
            backend = self._get_backend(domain)
            
            if not hasattr(backend, 'get_analytics'):
                raise StorageException(f"ドメイン '{domain}' はCDNバックエンドではありません")
            
            analytics = list(backend.get_analytics(path_prefix, start_time, end_time))
            logger.info(f"CDNアナリティクス取得: domain={domain}, records={len(analytics)}")
            return analytics
        except Exception as e:
            logger.error(f"CDNアナリティクス取得エラー: domain={domain}, error={e}")
            raise
    
    def prefetch_to_cdn(
        self,
        domain: str,
        paths: list[StoragePath],
    ) -> None:
        """コンテンツをCDNエッジに事前フェッチ."""
        try:
            backend = self._get_backend(domain)
            
            if not hasattr(backend, 'prefetch_content'):
                logger.warning(f"ドメイン '{domain}' はCDNプリフェッチをサポートしていません")
                return
            
            backend.prefetch_content(paths)
            logger.info(f"CDNプリフェッチ: domain={domain}, files={len(paths)}")
        except Exception as e:
            logger.error(f"CDNプリフェッチエラー: domain={domain}, error={e}")
            raise
    
    # =============================================================
    # 内部ヘルパーメソッド
    # =============================================================
    
    def _get_backend(self, domain: str) -> StorageBackend | CDNBackend:
        """ドメインに対応するバックエンドを取得（キャッシュ付き）."""
        if domain in self._backends:
            return self._backends[domain]
        
        # システム設定から自動設定を試行
        backend = self._get_backend_from_settings(domain)
        if backend:
            self._backends[domain] = backend
            return backend
        
        # 設定を取得
        configuration = self._repository.get_configuration(domain)
        if not configuration:
            raise StorageException(f"ドメイン '{domain}' のStorage設定が見つかりません")
        
        # バックエンドを作成してキャッシュ
        backend = self._factory.create_backend(configuration)
        self._backends[domain] = backend
        
        return backend
    
    def _get_cdn_backend_from_settings(self, domain: str) -> CDNBackend | None:
        """システム設定からCDNバックエンドを動的作成."""
        if not settings.cdn_enabled or settings.cdn_provider == "none":
            return None
        
        try:
            # CDN認証情報を作成
            if settings.cdn_provider == "azure":
                if not all([
                    settings.cdn_azure_account_name,
                    settings.cdn_azure_access_key,
                    settings.cdn_azure_profile,
                    settings.cdn_azure_endpoint,
                ]):
                    logger.warning("Azure CDN設定が不完全です")
                    return None
                
                cdn_credentials = StorageCredentials(
                    backend_type=StorageBackendType.AZURE_CDN,
                    account_name=settings.cdn_azure_account_name,
                    access_key=settings.cdn_azure_access_key,
                    cdn_profile=settings.cdn_azure_profile,
                    cdn_endpoint=settings.cdn_azure_endpoint,
                )
                
            elif settings.cdn_provider == "cloudflare":
                if not all([
                    settings.cdn_cloudflare_api_token,
                    settings.cdn_cloudflare_zone_id,
                    settings.cdn_cloudflare_origin_hostname,
                ]):
                    logger.warning("CloudFlare CDN設定が不完全です")
                    return None
                
                cdn_credentials = StorageCredentials(
                    backend_type=StorageBackendType.CLOUDFLARE_CDN,
                    api_token=settings.cdn_cloudflare_api_token,
                    zone_id=settings.cdn_cloudflare_zone_id,
                    origin_hostname=settings.cdn_cloudflare_origin_hostname,
                    access_key=settings.cdn_access_key,  # セキュアURLs用
                )
                
            elif settings.cdn_provider == "generic":
                if not all([
                    settings.cdn_generic_endpoint,
                    settings.cdn_generic_api_token,
                ]):
                    logger.warning("Generic CDN設定が不完全です")
                    return None
                
                cdn_credentials = StorageCredentials(
                    backend_type=StorageBackendType.GENERIC_CDN,
                    api_endpoint=settings.cdn_generic_endpoint,
                    api_token=settings.cdn_generic_api_token,
                    access_key=settings.cdn_access_key,
                )
            else:
                logger.error(f"未対応のCDNプロバイダー: {settings.cdn_provider}")
                return None
            
            # オリジンストレージ設定を取得
            origin_configuration = self._repository.get_configuration(domain)
            if not origin_configuration:
                logger.warning(f"ドメイン '{domain}' のオリジンストレージ設定が見つかりません")
                return None
            
            # CDN設定を作成
            cdn_configuration = StorageConfiguration(
                backend_type=getattr(StorageBackendType, settings.cdn_provider.upper() + "_CDN"),
                credentials=cdn_credentials,
                origin_backend_type=origin_configuration.backend_type,
                origin_credentials=origin_configuration.credentials,
                base_path=getattr(origin_configuration, 'base_path', None),
                cache_ttl=settings.cdn_cache_ttl,
                enable_compression=settings.cdn_enable_compression,
            )
            
            # CDNバックエンドを作成
            cdn_backend = self._factory.create_backend(cdn_configuration)
            return cdn_backend
            
        except Exception as e:
            logger.error(f"CDNバックエンド作成エラー: {e}")
            return None
    
    def _get_cdn_backend_from_settings(self, domain: str) -> CDNBackend | None:
        """システム設定からCDNバックエンドを動的に作成."""
        try:
            provider = settings.cdn_provider
            
            if provider == "none" or not settings.cdn_enabled:
                return None
            
            # 元のストレージバックエンド設定を取得
            original_backend = self._get_backend(domain)
            
            # CDN認証情報を作成
            if provider == "azure":
                if not all([
                    settings.cdn_azure_account_name,
                    settings.cdn_azure_access_key,
                    settings.cdn_azure_profile,
                    settings.cdn_azure_endpoint,
                ]):
                    logger.warning("Azure CDN設定が不完全です")
                    return None
                
                cdn_credentials = StorageCredentials(
                    backend_type=StorageBackendType.AZURE_CDN,
                    account_name=settings.cdn_azure_account_name,
                    access_key=settings.cdn_azure_access_key,
                    cdn_profile=settings.cdn_azure_profile,
                    cdn_endpoint=settings.cdn_azure_endpoint,
                )
            
            elif provider == "cloudflare":
                if not all([
                    settings.cdn_cloudflare_api_token,
                    settings.cdn_cloudflare_zone_id,
                    settings.cdn_cloudflare_origin_hostname,
                ]):
                    logger.warning("CloudFlare CDN設定が不完全です")
                    return None
                
                cdn_credentials = StorageCredentials(
                    backend_type=StorageBackendType.CLOUDFLARE_CDN,
                    api_token=settings.cdn_cloudflare_api_token,
                    zone_id=settings.cdn_cloudflare_zone_id,
                    origin_hostname=settings.cdn_cloudflare_origin_hostname,
                    access_key=settings.cdn_access_key,
                )
            
            elif provider == "generic":
                if not all([
                    settings.cdn_generic_endpoint,
                    settings.cdn_generic_api_token,
                ]):
                    logger.warning("Generic CDN設定が不完全です")
                    return None
                
                cdn_credentials = StorageCredentials(
                    backend_type=StorageBackendType.GENERIC_CDN,
                    api_endpoint=settings.cdn_generic_endpoint,
                    api_token=settings.cdn_generic_api_token,
                )
            
            else:
                logger.warning(f"未対応のCDNプロバイダー: {provider}")
                return None
            
            # 元のストレージ設定を取得
            original_config = self._repository.get_configuration(domain)
            if not original_config:
                logger.warning(f"ドメイン '{domain}' の元設定が見つかりません")
                return None
            
            # CDN設定を作成
            cdn_config = StorageConfiguration(
                backend_type=cdn_credentials.backend_type,
                credentials=cdn_credentials,
                origin_backend_type=original_config.backend_type,
                origin_credentials=original_config.credentials,
                base_path=original_config.base_path,
                cache_ttl=settings.cdn_cache_ttl,
                enable_compression=settings.cdn_enable_compression,
            )
            
            # CDNバックエンドを作成
            cdn_backend = self._factory.create_backend(cdn_config)
            logger.info(f"システム設定からCDNバックエンドを作成: domain={domain}, provider={provider}")
            return cdn_backend
        
        except Exception as e:
            logger.error(f"システム設定からのCDNバックエンド作成エラー: domain={domain}, error={e}")
            return None
    
    def _get_backend_from_settings(self, domain: str) -> StorageBackend | CDNBackend | None:
        """システム設定からストレージバックエンドを自動作成."""
        try:
            # Blob Storage設定を優先チェック
            if settings.blob_enabled and settings.blob_provider and settings.blob_provider != "none":
                blob_backend = self._create_blob_backend_from_settings()
                if blob_backend:
                    logger.info(f"システム設定からBlobバックエンドを作成: domain={domain}, provider={settings.blob_provider}")
                    return blob_backend
            
            # CDN設定をチェック
            if settings.cdn_enabled and settings.cdn_provider and settings.cdn_provider != "none":
                cdn_backend = self._get_cdn_backend_from_settings(domain)
                if cdn_backend:
                    return cdn_backend
            
            return None
            
        except Exception as e:
            logger.error(f"システム設定からのバックエンド作成エラー: domain={domain}, error={e}")
            return None
    
    def _create_blob_backend_from_settings(self) -> StorageBackend | None:
        """システム設定からBlobバックエンドを作成."""
        try:
            if not settings.blob_enabled or not settings.blob_provider:
                return None
            
            provider = settings.blob_provider
            
            if provider == "azure":
                # 認証方法を決定（接続文字列 > アカウント認証 > SASトークン）
                if settings.blob_connection_string:
                    credentials = StorageCredentials(
                        backend_type=StorageBackendType.AZURE_BLOB,
                        connection_string=settings.blob_connection_string,
                    )
                elif settings.blob_account_name and settings.blob_access_key:
                    credentials = StorageCredentials(
                        backend_type=StorageBackendType.AZURE_BLOB,
                        account_name=settings.blob_account_name,
                        access_key=settings.blob_access_key,
                        endpoint_suffix=settings.blob_endpoint_suffix or "core.windows.net",
                    )
                elif settings.blob_sas_token:
                    credentials = StorageCredentials(
                        backend_type=StorageBackendType.AZURE_BLOB,
                        sas_token=settings.blob_sas_token,
                        account_name=settings.blob_account_name,
                        endpoint_suffix=settings.blob_endpoint_suffix or "core.windows.net",
                    )
                else:
                    logger.warning("Azure Blob認証情報が不完全です")
                    return None
                
                # Blob設定を作成
                blob_config = StorageConfiguration(
                    backend_type=StorageBackendType.AZURE_BLOB,
                    credentials=credentials,
                    container_name=settings.blob_container_name,
                    base_path="",
                    secure_transfer=settings.blob_secure_transfer,
                    public_access_level=settings.blob_public_access_level,
                )
                
                # Blobバックエンドを作成
                blob_backend = self._factory.create_backend(blob_config)
                return blob_backend
            
            else:
                logger.warning(f"未対応のBlobプロバイダー: {provider}")
                return None
                
        except Exception as e:
            logger.error(f"Blobバックエンド作成エラー: {e}")
            return None