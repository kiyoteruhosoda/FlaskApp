"""CloudFlare CDN実装のユニットテスト."""

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
from bounded_contexts.storage.infrastructure.cloudflare_cdn import CloudFlareCDN


class TestCloudFlareCDN:
    """CloudFlare CDN実装のユニットテストクラス."""

    @pytest.fixture
    def cloudflare_cdn_credentials(self):
        """CloudFlare CDN認証情報."""
        return StorageCredentials(
            backend_type=StorageBackendType.CLOUDFLARE_CDN,
            api_token="test-cf-token-123",
            zone_id="test-zone-id-456",
            origin_hostname="cdn.example.com",
            access_key="cf-signing-key",
        )

    @pytest.fixture
    def origin_credentials(self):
        """オリジンストレージ認証情報."""
        return StorageCredentials(
            backend_type=StorageBackendType.LOCAL,
        )

    @pytest.fixture
    def cdn_configuration(self, cloudflare_cdn_credentials, origin_credentials):
        """CDN設定."""
        return CDNConfiguration(
            credentials=cloudflare_cdn_credentials,
            origin_backend_type=StorageBackendType.LOCAL,
            origin_credentials=origin_credentials,
            cache_ttl=3600,
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
            size=2048,
            etag="cf-mock-etag",
            content_type="image/jpeg",
            last_modified=datetime.now(timezone.utc),
        )
        return mock

    def test_get_cdn_url(self, cdn_configuration, sample_path):
        """CDN URL生成テスト."""
        with patch("bounded_contexts.storage.infrastructure.local_storage.LocalStorage"):
            cdn = CloudFlareCDN(cdn_configuration)

        url = cdn.get_cdn_url(sample_path)

        assert url == "https://cdn.example.com/media/original/2024/01/30/sample.jpg"

    def test_generate_secure_url_with_signed_token(self, cdn_configuration, sample_path):
        """署名付きセキュアURL生成テスト."""
        with patch("bounded_contexts.storage.infrastructure.local_storage.LocalStorage"):
            cdn = CloudFlareCDN(cdn_configuration)

        secure_url = cdn.generate_secure_url(
            path=sample_path,
            expiration_seconds=1800,
            allowed_ip="203.0.113.10",
        )

        base_url = "https://cdn.example.com/media/original/2024/01/30/sample.jpg"
        assert secure_url.startswith(base_url + "?")
        assert "auth=" in secure_url
        assert "exp=" in secure_url
        assert "ip=203.0.113.10" in secure_url

    def test_purge_cache_by_urls(self, cdn_configuration, sample_path):
        """URL指定キャッシュパージテスト."""
        with patch("bounded_contexts.storage.infrastructure.local_storage.LocalStorage"):
            with patch("requests.post") as mock_post:
                mock_post.return_value.status_code = 200
                mock_post.return_value.json.return_value = {"success": True, "id": "cf-purge-job-123"}

                cdn = CloudFlareCDN(cdn_configuration)

                purge_request = CDNPurgeRequest(
                    paths=[sample_path],
                    purge_type="url",
                    priority=1,
                )

                job_id = cdn.purge_cache(purge_request)

                assert job_id == "cf-purge-job-123"
                mock_post.assert_called_once()

                # リクエストボディを確認
                call_args = mock_post.call_args
                json_data = call_args.kwargs["json"]
                assert "files" in json_data
                assert "https://cdn.example.com/media/original/2024/01/30/sample.jpg" in json_data["files"]

    def test_purge_cache_by_tags(self, cdn_configuration):
        """タグ指定キャッシュパージテスト."""
        tag_path = StoragePath(
            domain="media",
            intent="thumbnails",
            relative_path="category:sports",
        )

        with patch("bounded_contexts.storage.infrastructure.local_storage.LocalStorage"):
            with patch("requests.post") as mock_post:
                mock_post.return_value.status_code = 200
                mock_post.return_value.json.return_value = {"success": True, "id": "cf-tag-purge-456"}

                cdn = CloudFlareCDN(cdn_configuration)

                purge_request = CDNPurgeRequest(
                    paths=[tag_path],
                    purge_type="tag",
                    priority=2,
                )

                job_id = cdn.purge_cache(purge_request)

                assert job_id == "cf-tag-purge-456"

                # タグパージのリクエストボディを確認
                call_args = mock_post.call_args
                json_data = call_args.kwargs["json"]
                assert "tags" in json_data
                assert "sports" in json_data["tags"]

    def test_purge_everything(self, cdn_configuration):
        """全キャッシュパージテスト."""
        everything_path = StoragePath(
            domain="*",
            intent="*",
            relative_path="*",
        )

        with patch("bounded_contexts.storage.infrastructure.local_storage.LocalStorage"):
            with patch("requests.post") as mock_post:
                mock_post.return_value.status_code = 200
                mock_post.return_value.json.return_value = {"success": True, "id": "cf-purge-all-789"}

                cdn = CloudFlareCDN(cdn_configuration)

                purge_request = CDNPurgeRequest(
                    paths=[everything_path],
                    purge_type="everything",
                    priority=3,
                )

                job_id = cdn.purge_cache(purge_request)

                assert job_id == "cf-purge-all-789"

                # 全パージのリクエストボディを確認
                call_args = mock_post.call_args
                json_data = call_args.kwargs["json"]
                assert json_data["purge_everything"] is True

    def test_get_analytics(self, cdn_configuration):
        """アナリティクス取得テスト."""
        analytics_path = StoragePath(
            domain="media",
            intent="original",
            relative_path="trending/",
        )

        mock_analytics_response = {
            "success": True,
            "result": {
                "data": [
                    {
                        "dimensions": {"path": "/media/original/trending/video1.mp4"},
                        "metrics": [1800, 3072000, 92, 8],  # requests, bytes, cache_hit_ratio%, avg_response_time_ms
                        "datetime": "2024-01-30T14:00:00Z",
                    },
                    {
                        "dimensions": {"path": "/media/original/trending/video2.mp4"},
                        "metrics": [1200, 2048000, 88, 12],
                        "datetime": "2024-01-30T14:00:00Z",
                    },
                ]
            }
        }

        with patch("bounded_contexts.storage.infrastructure.local_storage.LocalStorage"):
            with patch("requests.get") as mock_get:
                mock_get.return_value.status_code = 200
                mock_get.return_value.json.return_value = mock_analytics_response

                cdn = CloudFlareCDN(cdn_configuration)

                analytics = cdn.get_analytics(
                    path_prefix=analytics_path,
                    start_time="2024-01-30T00:00:00Z",
                    end_time="2024-01-30T23:59:59Z",
                )

                assert len(analytics) == 2

                first_record = analytics[0]
                assert first_record.path == "/media/original/trending/video1.mp4"
                assert first_record.requests_count == 1800
                assert first_record.bandwidth_bytes == 3072000
                assert first_record.cache_hit_ratio == 0.92
                assert first_record.avg_response_time_ms == 8

    def test_upload_to_origin_and_invalidate(self, cdn_configuration, sample_path, mock_origin_backend):
        """オリジンアップロード＋無効化テスト."""
        with patch("bounded_contexts.storage.infrastructure.local_storage.LocalStorage"):
            with patch("requests.post") as mock_post:
                mock_post.return_value.status_code = 200
                mock_post.return_value.json.return_value = {"success": True, "id": "cf-upload-purge-321"}

                cdn = CloudFlareCDN(cdn_configuration)
                cdn._origin_backend = mock_origin_backend

                content = b"CloudFlare CDN test content"
                
                result = cdn.upload_to_origin_and_invalidate(sample_path, content)

                # オリジンバックエンドのアップロードが呼ばれることを確認
                mock_origin_backend.upload.assert_called_once_with(sample_path, content)

                # 結果確認
                assert result.size == 2048  # mock_origin_backend の戻り値
                assert result.cdn_url == "https://cdn.example.com/media/original/2024/01/30/sample.jpg"
                assert result.cache_status == "PURGED"
                assert result.purge_job_id == "cf-upload-purge-321"

    def test_prefetch_resources(self, cdn_configuration):
        """リソースプリフェッチテスト."""
        paths = [
            StoragePath(domain="media", intent="original", relative_path="popular1.jpg"),
            StoragePath(domain="media", intent="original", relative_path="popular2.jpg"),
        ]

        with patch("bounded_contexts.storage.infrastructure.local_storage.LocalStorage"):
            with patch("requests.post") as mock_post:
                mock_post.return_value.status_code = 200
                mock_post.return_value.json.return_value = {"success": True}

                cdn = CloudFlareCDN(cdn_configuration)

                # プリフェッチ実行（例外が発生しないことを確認）
                cdn.prefetch_resources(paths)

                # CloudFlareのプリフェッチAPIが適切に呼ばれることを確認
                assert mock_post.called

    def test_zone_analytics_integration(self, cdn_configuration):
        """ゾーンアナリティクス統合テスト."""
        with patch("bounded_contexts.storage.infrastructure.local_storage.LocalStorage"):
            with patch("requests.get") as mock_get:
                # ゾーン全体のアナリティクス
                mock_get.return_value.status_code = 200
                mock_get.return_value.json.return_value = {
                    "success": True,
                    "result": {
                        "totals": {
                            "requests": {"all": 50000, "cached": 42000},
                            "bandwidth": {"all": 104857600, "cached": 92274688},
                        },
                        "timeseries": []
                    }
                }

                cdn = CloudFlareCDN(cdn_configuration)

                # ゾーン全体のアナリティクス取得
                zone_path = StoragePath(domain="*", intent="*", relative_path="")
                
                analytics = cdn.get_analytics(
                    path_prefix=zone_path,
                    start_time="2024-01-30T00:00:00Z",
                    end_time="2024-01-30T23:59:59Z",
                )

                # ゾーン全体の統計が返される
                assert len(analytics) == 1
                total_record = analytics[0]
                assert total_record.path == "zone:test-zone-id-456"
                assert total_record.requests_count == 50000
                assert total_record.bandwidth_bytes == 104857600
                assert total_record.cache_hit_ratio == 0.84  # 42000/50000

    def test_error_handling(self, cdn_configuration, sample_path):
        """エラーハンドリングテスト."""
        with patch("bounded_contexts.storage.infrastructure.local_storage.LocalStorage"):
            with patch("requests.post") as mock_post:
                # CloudFlare API がエラーを返す
                mock_post.return_value.status_code = 403
                mock_post.return_value.json.return_value = {
                    "success": False,
                    "errors": [{"code": 1003, "message": "Invalid API token"}]
                }

                cdn = CloudFlareCDN(cdn_configuration)

                purge_request = CDNPurgeRequest(
                    paths=[sample_path],
                    purge_type="url",
                    priority=1,
                )

                with pytest.raises(RuntimeError, match="Failed to purge CDN cache"):
                    cdn.purge_cache(purge_request)

    def test_custom_cache_headers(self, cdn_configuration, sample_path, mock_origin_backend):
        """カスタムキャッシュヘッダーテスト."""
        # カスタムキャッシュ設定
        custom_cdn_config = CDNConfiguration(
            credentials=cdn_configuration.credentials,
            origin_backend_type=cdn_configuration.origin_backend_type,
            origin_credentials=cdn_configuration.origin_credentials,
            cache_ttl=14400,  # 4時間
            enable_compression=True,
            custom_headers={
                "Cache-Control": "public, max-age=14400, s-maxage=86400",
                "Vary": "Accept-Encoding",
            }
        )

        with patch("bounded_contexts.storage.infrastructure.local_storage.LocalStorage"):
            cdn = CloudFlareCDN(custom_cdn_config)
            cdn._origin_backend = mock_origin_backend

            url = cdn.get_cdn_url(sample_path)

            # カスタムヘッダーがURL生成に影響しないことを確認
            assert url == "https://cdn.example.com/media/original/2024/01/30/sample.jpg"

    def test_rate_limiting_handling(self, cdn_configuration, sample_path):
        """レート制限ハンドリングテスト."""
        with patch("bounded_contexts.storage.infrastructure.local_storage.LocalStorage"):
            with patch("requests.post") as mock_post:
                # CloudFlare API がレート制限を返す
                mock_post.return_value.status_code = 429
                mock_post.return_value.headers = {"Retry-After": "60"}
                mock_post.return_value.json.return_value = {
                    "success": False,
                    "errors": [{"code": 10013, "message": "Rate limit exceeded"}]
                }

                cdn = CloudFlareCDN(cdn_configuration)

                purge_request = CDNPurgeRequest(
                    paths=[sample_path],
                    purge_type="url",
                    priority=1,
                )

                with pytest.raises(RuntimeError, match="Rate limit exceeded"):
                    cdn.purge_cache(purge_request)

    def test_cdn_configuration_validation(self):
        """CDN設定バリデーションテスト."""
        # 不完全なCloudFlare CDN認証情報
        incomplete_credentials = StorageCredentials(
            backend_type=StorageBackendType.CLOUDFLARE_CDN,
            api_token="test-token",
            # zone_id, origin_hostname が不足
        )

        origin_credentials = StorageCredentials(
            backend_type=StorageBackendType.LOCAL,
        )

        with pytest.raises(ValueError):
            CDNConfiguration(
                credentials=incomplete_credentials,
                origin_backend_type=StorageBackendType.LOCAL,
                origin_credentials=origin_credentials,
            )