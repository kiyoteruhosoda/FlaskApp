"""Azure CDN実装のユニットテスト."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from bounded_contexts.storage.domain import (
    CDNAnalytics,
    CDNConfiguration,
    CDNPurgeRequest,
    StorageBackendType,
    StorageCredentials,
    StoragePath,
)
from bounded_contexts.storage.infrastructure.azure_cdn import AzureCDN


class TestAzureCDN:
    """Azure CDN実装のユニットテストクラス."""

    @pytest.fixture
    def azure_cdn_credentials(self):
        """Azure CDN認証情報."""
        return StorageCredentials(
            backend_type=StorageBackendType.AZURE_CDN,
            account_name="testcdn",
            access_key="testkey123",
            cdn_profile="test-profile",
            cdn_endpoint="testcdn",
        )

    @pytest.fixture
    def origin_credentials(self):
        """オリジンストレージ認証情報."""
        return StorageCredentials(
            backend_type=StorageBackendType.AZURE_BLOB,
            connection_string="DefaultEndpointsProtocol=https;AccountName=origin;AccountKey=key==",
            container_name="images",
        )

    @pytest.fixture
    def cdn_configuration(self, azure_cdn_credentials, origin_credentials):
        """CDN設定."""
        return CDNConfiguration(
            credentials=azure_cdn_credentials,
            origin_backend_type=StorageBackendType.AZURE_BLOB,
            origin_credentials=origin_credentials,
            cache_ttl=7200,
            enable_compression=True,
        )

    @pytest.fixture
    def sample_path(self):
        """サンプルパス."""
        return StoragePath(
            domain="media",
            intent="original",
            relative_path="2024/01/30/sample.jpg",
        )

    @pytest.fixture
    def mock_origin_backend(self):
        """モックオリジンバックエンド."""
        mock = MagicMock()
        mock.upload.return_value = MagicMock(
            size=1024,
            etag="mock-etag",
            content_type="image/jpeg",
            last_modified=datetime.now(timezone.utc),
        )
        return mock

    def test_get_cdn_url(self, cdn_configuration, sample_path):
        """CDN URL生成テスト."""
        with patch("bounded_contexts.storage.infrastructure.azure_blob.BlobServiceClient"):
            cdn = AzureCDN(cdn_configuration)

        url = cdn.get_cdn_url(sample_path)

        assert url == "https://testcdn.azureedge.net/media/original/2024/01/30/sample.jpg"

    def test_generate_secure_url(self, cdn_configuration, sample_path):
        """セキュアURL生成テスト."""
        with patch("bounded_contexts.storage.infrastructure.azure_blob.BlobServiceClient"):
            cdn = AzureCDN(cdn_configuration)

        secure_url = cdn.generate_secure_url(
            path=sample_path,
            expiration_seconds=3600,
            allowed_ip="192.168.1.100",
        )

        base_url = "https://testcdn.azureedge.net/media/original/2024/01/30/sample.jpg"
        assert secure_url.startswith(base_url + "?token=")
        assert "expires=" in secure_url
        assert "ip=192.168.1.100" in secure_url

    def test_purge_cache_single_url(self, cdn_configuration, sample_path):
        """単一URLキャッシュパージテスト."""
        with patch("bounded_contexts.storage.infrastructure.azure_blob.BlobServiceClient"):
            with patch("requests.post") as mock_post:
                mock_post.return_value.status_code = 202
                mock_post.return_value.json.return_value = {"operationId": "test-operation-id"}

                cdn = AzureCDN(cdn_configuration)

                purge_request = CDNPurgeRequest(
                    paths=[sample_path],
                    purge_type="url",
                    priority=1,
                )

                job_id = cdn.purge_cache(purge_request)

                assert job_id == "test-operation-id"
                mock_post.assert_called_once()

    def test_purge_cache_prefix(self, cdn_configuration):
        """プレフィックスキャッシュパージテスト."""
        prefix_path = StoragePath(
            domain="media",
            intent="thumbnails",
            relative_path="2024/01/",
        )

        with patch("bounded_contexts.storage.infrastructure.azure_blob.BlobServiceClient"):
            with patch("requests.post") as mock_post:
                mock_post.return_value.status_code = 202
                mock_post.return_value.json.return_value = {"operationId": "prefix-operation-id"}

                cdn = AzureCDN(cdn_configuration)

                purge_request = CDNPurgeRequest(
                    paths=[prefix_path],
                    purge_type="prefix",
                    priority=2,
                )

                job_id = cdn.purge_cache(purge_request)

                assert job_id == "prefix-operation-id"

    def test_get_analytics(self, cdn_configuration):
        """アナリティクス取得テスト."""
        analytics_path = StoragePath(
            domain="media",
            intent="original",
            relative_path="popular/",
        )

        mock_analytics_data = [
            {
                "path": "/media/original/popular/image1.jpg",
                "requests": 1500,
                "bytes": 2048000,
                "cache_hit_ratio": 0.85,
                "timestamp": "2024-01-30T12:00:00Z",
            },
            {
                "path": "/media/original/popular/image2.jpg", 
                "requests": 1200,
                "bytes": 1536000,
                "cache_hit_ratio": 0.78,
                "timestamp": "2024-01-30T12:00:00Z",
            },
        ]

        with patch("bounded_contexts.storage.infrastructure.azure_blob.BlobServiceClient"):
            with patch("requests.get") as mock_get:
                mock_get.return_value.status_code = 200
                mock_get.return_value.json.return_value = {"data": mock_analytics_data}

                cdn = AzureCDN(cdn_configuration)

                analytics = cdn.get_analytics(
                    path_prefix=analytics_path,
                    start_time="2024-01-30T00:00:00Z",
                    end_time="2024-01-30T23:59:59Z",
                )

                assert len(analytics) == 2

                first_record = analytics[0]
                assert first_record.path == "/media/original/popular/image1.jpg"
                assert first_record.requests_count == 1500
                assert first_record.bandwidth_bytes == 2048000
                assert first_record.cache_hit_ratio == 0.85

    def test_upload_to_origin_and_invalidate(self, cdn_configuration, sample_path, mock_origin_backend):
        """オリジンアップロード＋無効化テスト."""
        with patch("bounded_contexts.storage.infrastructure.azure_blob.BlobServiceClient"):
            with patch("requests.post") as mock_post:
                mock_post.return_value.status_code = 202
                mock_post.return_value.json.return_value = {"operationId": "upload-purge-id"}

                cdn = AzureCDN(cdn_configuration)
                cdn._origin_backend = mock_origin_backend

                content = b"test image content for CDN"
                
                result = cdn.upload_to_origin_and_invalidate(sample_path, content)

                # オリジンバックエンドのアップロードが呼ばれることを確認
                mock_origin_backend.upload.assert_called_once_with(sample_path, content)

                # 結果確認
                assert result.size == 1024  # mock_origin_backend の戻り値
                assert result.cdn_url == "https://testcdn.azureedge.net/media/original/2024/01/30/sample.jpg"
                assert result.cache_status == "PURGED"
                assert result.purge_job_id == "upload-purge-id"

    def test_prefetch_resources(self, cdn_configuration):
        """リソースプリフェッチテスト."""
        paths = [
            StoragePath(domain="media", intent="original", relative_path="hot1.jpg"),
            StoragePath(domain="media", intent="original", relative_path="hot2.jpg"),
        ]

        with patch("bounded_contexts.storage.infrastructure.azure_blob.BlobServiceClient"):
            with patch("requests.post") as mock_post:
                mock_post.return_value.status_code = 202

                cdn = AzureCDN(cdn_configuration)

                # プリフェッチ実行（例外が発生しないことを確認）
                cdn.prefetch_resources(paths)

                # Azure CDNのプリロードAPIが呼ばれることを確認
                assert mock_post.call_count == 2  # 各パスでAPIコール

    def test_secure_url_token_generation(self, cdn_configuration, sample_path):
        """セキュアURLトークン生成テスト."""
        with patch("bounded_contexts.storage.infrastructure.azure_blob.BlobServiceClient"):
            cdn = AzureCDN(cdn_configuration)

        # 同じパラメータで複数回生成した場合、異なるトークンが生成される（nonce使用）
        url1 = cdn.generate_secure_url(sample_path, 3600, "192.168.1.100")
        url2 = cdn.generate_secure_url(sample_path, 3600, "192.168.1.100")

        assert url1 != url2
        assert "token=" in url1
        assert "token=" in url2

    def test_error_handling(self, cdn_configuration, sample_path):
        """エラーハンドリングテスト."""
        with patch("bounded_contexts.storage.infrastructure.azure_blob.BlobServiceClient"):
            with patch("requests.post") as mock_post:
                # Azure CDN API がエラーを返す
                mock_post.return_value.status_code = 400
                mock_post.return_value.json.return_value = {"error": "Invalid request"}

                cdn = AzureCDN(cdn_configuration)

                purge_request = CDNPurgeRequest(
                    paths=[sample_path],
                    purge_type="url",
                    priority=1,
                )

                with pytest.raises(RuntimeError, match="Failed to purge CDN cache"):
                    cdn.purge_cache(purge_request)

    def test_cdn_configuration_validation(self):
        """CDN設定バリデーションテスト."""
        # 不完全なAzure CDN認証情報
        incomplete_credentials = StorageCredentials(
            backend_type=StorageBackendType.AZURE_CDN,
            account_name="test",
            # access_key, cdn_profile, cdn_endpoint が不足
        )

        origin_credentials = StorageCredentials(
            backend_type=StorageBackendType.AZURE_BLOB,
            connection_string="DefaultEndpointsProtocol=https;AccountName=origin;AccountKey=key==",
        )

        with pytest.raises(ValueError):
            CDNConfiguration(
                credentials=incomplete_credentials,
                origin_backend_type=StorageBackendType.AZURE_BLOB,
                origin_credentials=origin_credentials,
            )