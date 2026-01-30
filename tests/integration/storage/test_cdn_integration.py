"""CDN統合テスト."""

import tempfile
from unittest.mock import MagicMock, patch

import pytest

from bounded_contexts.storage.application import StorageApplicationService
from bounded_contexts.storage.domain import (
    StorageBackendType,
    StorageConfiguration,
    StorageCredentials,
    StorageDomain,
    StorageIntent,
    StoragePath,
)
from bounded_contexts.storage.infrastructure import InMemoryStorageRepository


class TestCDNIntegration:
    """CDN統合テストクラス."""
    
    @pytest.fixture
    def repository(self):
        """インメモリリポジトリ."""
        return InMemoryStorageRepository()
    
    @pytest.fixture
    def storage_service(self, repository):
        """CDN対応Storageサービス."""
        return StorageApplicationService(repository)
    
    @pytest.fixture
    def temp_storage_dir(self):
        """テンポラリストレージディレクトリ."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir
    
    @pytest.fixture
    def sample_image_path(self):
        """サンプル画像パス."""
        return StoragePath(
            domain=StorageDomain.MEDIA,
            intent=StorageIntent.ORIGINAL,
            relative_path="2024/01/30/sample.jpg",
        )
    
    def test_azure_cdn_configuration(self, storage_service):
        """Azure CDN設定テスト."""
        # Azure CDN設定
        cdn_credentials = StorageCredentials(
            backend_type=StorageBackendType.AZURE_CDN,
            account_name="testcdn",
            access_key="testkey",
            cdn_profile="test-profile",
            cdn_endpoint="testcdn",
        )
        
        # オリジンストレージ（Azure Blob）設定
        origin_credentials = StorageCredentials(
            backend_type=StorageBackendType.AZURE_BLOB,
            connection_string="DefaultEndpointsProtocol=https;AccountName=origin;AccountKey=key==",
            container_name="images",
        )
        
        cdn_config = StorageConfiguration(
            backend_type=StorageBackendType.AZURE_CDN,
            credentials=cdn_credentials,
            origin_backend_type=StorageBackendType.AZURE_BLOB,
            origin_credentials=origin_credentials,
            cache_ttl=7200,
            enable_compression=True,
        )
        
        domain = "azure-cdn-images"
        
        with patch.dict('sys.modules', {
            'azure.storage.blob': MagicMock(),
            'azure.core.exceptions': MagicMock(),
        }):
            with patch('bounded_contexts.storage.infrastructure.azure_blob.BlobServiceClient'):
                with patch('bounded_contexts.storage.infrastructure.azure_blob.ResourceExistsError'):
                    storage_service.configure_storage(domain, cdn_config)
        
        # 設定確認
        domains = storage_service.get_storage_domains()
        assert domain in domains
    
    def test_cloudflare_cdn_configuration(self, storage_service, temp_storage_dir):
        """CloudFlare CDN設定テスト."""
        # CloudFlare CDN設定
        cdn_credentials = StorageCredentials(
            backend_type=StorageBackendType.CLOUDFLARE_CDN,
            api_token="test-api-token",
            zone_id="test-zone-id",
            origin_hostname="images.example.com",
        )
        
        # オリジンストレージ（Local）設定
        origin_credentials = StorageCredentials(
            backend_type=StorageBackendType.LOCAL,
        )
        
        cdn_config = StorageConfiguration(
            backend_type=StorageBackendType.CLOUDFLARE_CDN,
            credentials=cdn_credentials,
            origin_backend_type=StorageBackendType.LOCAL,
            origin_credentials=origin_credentials,
            base_path=temp_storage_dir,
            cache_ttl=3600,
        )
        
        domain = "cloudflare-cdn-images"
        storage_service.configure_storage(domain, cdn_config)
        
        # 設定確認
        domains = storage_service.get_storage_domains()
        assert domain in domains
    
    def test_cdn_url_generation(self, storage_service, temp_storage_dir, sample_image_path):
        """CDN URL生成テスト."""
        # CloudFlare CDN設定
        cdn_credentials = StorageCredentials(
            backend_type=StorageBackendType.CLOUDFLARE_CDN,
            api_token="test-token",
            zone_id="test-zone",
            origin_hostname="cdn.example.com",
        )
        
        origin_credentials = StorageCredentials(backend_type=StorageBackendType.LOCAL)
        
        cdn_config = StorageConfiguration(
            backend_type=StorageBackendType.CLOUDFLARE_CDN,
            credentials=cdn_credentials,
            origin_backend_type=StorageBackendType.LOCAL,
            origin_credentials=origin_credentials,
            base_path=temp_storage_dir,
        )
        
        domain = "cdn-test"
        storage_service.configure_storage(domain, cdn_config)
        
        # CDN URLを取得
        cdn_url = storage_service.get_cdn_url(domain, sample_image_path)
        
        assert cdn_url.startswith("https://cdn.example.com/")
        assert "media/original/2024/01/30/sample.jpg" in cdn_url
    
    def test_secure_cdn_url_generation(self, storage_service, temp_storage_dir, sample_image_path):
        """セキュアCDN URL生成テスト."""
        # CDN設定（アクセスキー付き）
        cdn_credentials = StorageCredentials(
            backend_type=StorageBackendType.CLOUDFLARE_CDN,
            api_token="test-token",
            zone_id="test-zone",
            origin_hostname="secure.example.com",
            access_key="secret-signing-key",
        )
        
        origin_credentials = StorageCredentials(backend_type=StorageBackendType.LOCAL)
        
        cdn_config = StorageConfiguration(
            backend_type=StorageBackendType.CLOUDFLARE_CDN,
            credentials=cdn_credentials,
            origin_backend_type=StorageBackendType.LOCAL,
            origin_credentials=origin_credentials,
            base_path=temp_storage_dir,
        )
        
        domain = "secure-cdn"
        storage_service.configure_storage(domain, cdn_config)
        
        # セキュアCDN URLを生成
        secure_url = storage_service.generate_secure_cdn_url(
            domain, 
            sample_image_path,
            expiration_seconds=1800,
            allowed_ip="192.168.1.100"
        )
        
        assert secure_url.startswith("https://secure.example.com/")\n        assert \"token=\" in secure_url\n        assert \"expires=\" in secure_url\n        assert \"ip=192.168.1.100\" in secure_url\n    \n    def test_cdn_upload_and_distribute(self, storage_service, temp_storage_dir, sample_image_path):\n        \"\"\"CDNアップロード＋配信テスト.\"\"\"\n        # CloudFlare CDN設定\n        cdn_credentials = StorageCredentials(\n            backend_type=StorageBackendType.CLOUDFLARE_CDN,\n            api_token=\"test-token\",\n            zone_id=\"test-zone\",\n            origin_hostname=\"upload.example.com\",\n        )\n        \n        origin_credentials = StorageCredentials(backend_type=StorageBackendType.LOCAL)\n        \n        cdn_config = StorageConfiguration(\n            backend_type=StorageBackendType.CLOUDFLARE_CDN,\n            credentials=cdn_credentials,\n            origin_backend_type=StorageBackendType.LOCAL,\n            origin_credentials=origin_credentials,\n            base_path=temp_storage_dir,\n        )\n        \n        domain = \"upload-cdn\"\n        storage_service.configure_storage(domain, cdn_config)\n        \n        # 画像をアップロードしてCDNで配信\n        image_content = b\"fake image content for CDN distribution\"\n        \n        metadata = storage_service.upload_and_distribute(domain, sample_image_path, image_content)\n        \n        assert metadata.size == len(image_content)\n        assert metadata.cdn_url is not None\n        assert \"upload.example.com\" in metadata.cdn_url\n        assert metadata.cache_status == \"PURGED\"\n    \n    def test_cdn_cache_purge(self, storage_service, temp_storage_dir):\n        \"\"\"CDNキャッシュパージテスト.\"\"\"\n        # Azure CDN設定\n        cdn_credentials = StorageCredentials(\n            backend_type=StorageBackendType.AZURE_CDN,\n            account_name=\"testpurge\",\n            access_key=\"testkey\",\n            cdn_profile=\"purge-profile\",\n            cdn_endpoint=\"purgecdn\",\n        )\n        \n        origin_credentials = StorageCredentials(\n            backend_type=StorageBackendType.LOCAL,\n        )\n        \n        cdn_config = StorageConfiguration(\n            backend_type=StorageBackendType.AZURE_CDN,\n            credentials=cdn_credentials,\n            origin_backend_type=StorageBackendType.LOCAL,\n            origin_credentials=origin_credentials,\n            base_path=temp_storage_dir,\n        )\n        \n        domain = \"purge-test\"\n        storage_service.configure_storage(domain, cdn_config)\n        \n        # 複数パスでキャッシュパージ\n        paths = [\n            StoragePath(domain=StorageDomain.MEDIA, intent=StorageIntent.ORIGINAL, relative_path=\"image1.jpg\"),\n            StoragePath(domain=StorageDomain.MEDIA, intent=StorageIntent.ORIGINAL, relative_path=\"image2.jpg\"),\n            StoragePath(domain=StorageDomain.THUMBNAILS, intent=StorageIntent.THUMBNAIL, relative_path=\"thumb1.jpg\"),\n        ]\n        \n        job_id = storage_service.purge_cdn_cache(domain, paths, purge_type=\"url\", priority=1)\n        \n        # パージジョブIDが返される\n        assert job_id is not None\n        assert len(job_id) > 0\n    \n    def test_cdn_prefetch(self, storage_service, temp_storage_dir):\n        \"\"\"CDNプリフェッチテスト.\"\"\"\n        # CloudFlare CDN設定\n        cdn_credentials = StorageCredentials(\n            backend_type=StorageBackendType.CLOUDFLARE_CDN,\n            api_token=\"prefetch-token\",\n            zone_id=\"prefetch-zone\",\n            origin_hostname=\"prefetch.example.com\",\n        )\n        \n        origin_credentials = StorageCredentials(backend_type=StorageBackendType.LOCAL)\n        \n        cdn_config = StorageConfiguration(\n            backend_type=StorageBackendType.CLOUDFLARE_CDN,\n            credentials=cdn_credentials,\n            origin_backend_type=StorageBackendType.LOCAL,\n            origin_credentials=origin_credentials,\n            base_path=temp_storage_dir,\n        )\n        \n        domain = \"prefetch-test\"\n        storage_service.configure_storage(domain, cdn_config)\n        \n        # プリフェッチ対象パス\n        paths = [\n            StoragePath(domain=StorageDomain.MEDIA, intent=StorageIntent.ORIGINAL, relative_path=\"popular1.jpg\"),\n            StoragePath(domain=StorageDomain.MEDIA, intent=StorageIntent.ORIGINAL, relative_path=\"popular2.jpg\"),\n        ]\n        \n        # プリフェッチを実行（エラーなく完了することを確認）\n        storage_service.prefetch_to_cdn(domain, paths)\n    \n    def test_cdn_analytics(self, storage_service, temp_storage_dir):\n        \"\"\"CDNアナリティクステスト.\"\"\"\n        # Azure CDN設定\n        cdn_credentials = StorageCredentials(\n            backend_type=StorageBackendType.AZURE_CDN,\n            account_name=\"analytics\",\n            access_key=\"testkey\",\n            cdn_profile=\"analytics-profile\",\n            cdn_endpoint=\"analyticscdn\",\n        )\n        \n        origin_credentials = StorageCredentials(backend_type=StorageBackendType.LOCAL)\n        \n        cdn_config = StorageConfiguration(\n            backend_type=StorageBackendType.AZURE_CDN,\n            credentials=cdn_credentials,\n            origin_backend_type=StorageBackendType.LOCAL,\n            origin_credentials=origin_credentials,\n            base_path=temp_storage_dir,\n        )\n        \n        domain = \"analytics-test\"\n        storage_service.configure_storage(domain, cdn_config)\n        \n        # アナリティクスデータを取得\n        path_prefix = StoragePath(\n            domain=StorageDomain.MEDIA,\n            intent=StorageIntent.ORIGINAL,\n            relative_path=\"2024/01/\",\n        )\n        \n        analytics = storage_service.get_cdn_analytics(\n            domain,\n            path_prefix,\n            \"2024-01-30T00:00:00Z\",\n            \"2024-01-30T23:59:59Z\",\n        )\n        \n        assert len(analytics) > 0\n        first_record = analytics[0]\n        assert first_record.requests_count > 0\n        assert 0 <= first_record.cache_hit_ratio <= 1\n        assert first_record.bandwidth_bytes > 0\n    \n    def test_non_cdn_backend_fallback(self, storage_service, temp_storage_dir, sample_image_path):\n        \"\"\"非CDNバックエンドでのフォールバック動作テスト.\"\"\"\n        # 通常のローカルストレージ設定\n        local_credentials = StorageCredentials(backend_type=StorageBackendType.LOCAL)\n        local_config = StorageConfiguration(\n            backend_type=StorageBackendType.LOCAL,\n            credentials=local_credentials,\n            base_path=temp_storage_dir,\n        )\n        \n        domain = \"local-fallback\"\n        storage_service.configure_storage(domain, local_config)\n        \n        # CDN URLを要求するが、通常のダウンロードURLが返される\n        url = storage_service.get_cdn_url(domain, sample_image_path)\n        \n        # file:// スキームのURLが返される\n        assert url.startswith(\"file://\")\n        \n        # CDNプリフェッチは警告ログのみでエラーにならない\n        storage_service.prefetch_to_cdn(domain, [sample_image_path])\n    \n    def test_cdn_configuration_validation(self, storage_service):\n        \"\"\"CDN設定バリデーションテスト.\"\"\"\n        # 不正なAzure CDN設定（必須フィールド不足）\n        with pytest.raises(ValueError, match=\"Azure CDN requires\"):\n            StorageCredentials(\n                backend_type=StorageBackendType.AZURE_CDN,\n                account_name=\"test\",\n                # access_key, cdn_profile, cdn_endpoint が不足\n            )\n        \n        # 不正なCloudFlare CDN設定\n        with pytest.raises(ValueError, match=\"CloudFlare CDN requires\"):\n            StorageCredentials(\n                backend_type=StorageBackendType.CLOUDFLARE_CDN,\n                api_token=\"token\",\n                # zone_id, origin_hostname が不足\n            )\n        \n        # CDN設定でオリジンストレージが未指定\n        cdn_credentials = StorageCredentials(\n            backend_type=StorageBackendType.AZURE_CDN,\n            account_name=\"test\",\n            access_key=\"key\",\n            cdn_profile=\"profile\",\n            cdn_endpoint=\"endpoint\",\n        )\n        \n        with pytest.raises(ValueError, match=\"CDN backends require origin_backend_type\"):\n            StorageConfiguration(\n                backend_type=StorageBackendType.AZURE_CDN,\n                credentials=cdn_credentials,\n                # origin_backend_type, origin_credentials が不足\n            )