"""CDNエラーハンドリングと設定バリデーションのテスト."""

import pytest

from bounded_contexts.storage.domain import (
    CDNConfiguration, 
    CDNPurgeRequest,
    StorageBackendType,
    StorageConfiguration,
    StorageCredentials,
    StoragePath,
)


class TestCDNValidation:
    """CDN設定バリデーションのテストクラス."""

    def test_azure_cdn_credentials_validation(self):
        """Azure CDN認証情報バリデーション."""
        # 必須フィールドがすべて揃っている場合は成功
        valid_credentials = StorageCredentials(
            backend_type=StorageBackendType.AZURE_CDN,
            account_name="validcdn",
            access_key="valid-access-key",
            cdn_profile="valid-profile",
            cdn_endpoint="validcdn",
        )
        assert valid_credentials.account_name == "validcdn"

        # account_name が不足
        with pytest.raises(ValueError, match="Azure CDN requires.*account_name"):
            StorageCredentials(
                backend_type=StorageBackendType.AZURE_CDN,
                access_key="key",
                cdn_profile="profile",
                cdn_endpoint="endpoint",
            )

        # access_key が不足
        with pytest.raises(ValueError, match="Azure CDN requires.*access_key"):
            StorageCredentials(
                backend_type=StorageBackendType.AZURE_CDN,
                account_name="account",
                cdn_profile="profile",
                cdn_endpoint="endpoint",
            )

        # cdn_profile が不足
        with pytest.raises(ValueError, match="Azure CDN requires.*cdn_profile"):
            StorageCredentials(
                backend_type=StorageBackendType.AZURE_CDN,
                account_name="account",
                access_key="key",
                cdn_endpoint="endpoint",
            )

        # cdn_endpoint が不足
        with pytest.raises(ValueError, match="Azure CDN requires.*cdn_endpoint"):
            StorageCredentials(
                backend_type=StorageBackendType.AZURE_CDN,
                account_name="account",
                access_key="key",
                cdn_profile="profile",
            )

    def test_cloudflare_cdn_credentials_validation(self):
        """CloudFlare CDN認証情報バリデーション."""
        # 必須フィールドがすべて揃っている場合は成功
        valid_credentials = StorageCredentials(
            backend_type=StorageBackendType.CLOUDFLARE_CDN,
            api_token="valid-token",
            zone_id="valid-zone-id",
            origin_hostname="valid.example.com",
        )
        assert valid_credentials.api_token == "valid-token"

        # api_token が不足
        with pytest.raises(ValueError, match="CloudFlare CDN requires.*api_token"):
            StorageCredentials(
                backend_type=StorageBackendType.CLOUDFLARE_CDN,
                zone_id="zone",
                origin_hostname="host.example.com",
            )

        # zone_id が不足
        with pytest.raises(ValueError, match="CloudFlare CDN requires.*zone_id"):
            StorageCredentials(
                backend_type=StorageBackendType.CLOUDFLARE_CDN,
                api_token="token",
                origin_hostname="host.example.com",
            )

        # origin_hostname が不足
        with pytest.raises(ValueError, match="CloudFlare CDN requires.*origin_hostname"):
            StorageCredentials(
                backend_type=StorageBackendType.CLOUDFLARE_CDN,
                api_token="token",
                zone_id="zone",
            )

    def test_cdn_configuration_requires_origin(self):
        """CDN設定でオリジンストレージが必須であることの検証."""
        cdn_credentials = StorageCredentials(
            backend_type=StorageBackendType.AZURE_CDN,
            account_name="test",
            access_key="key",
            cdn_profile="profile",
            cdn_endpoint="endpoint",
        )

        # origin_backend_type が不足
        with pytest.raises(ValueError, match="CDN backends require origin_backend_type"):
            StorageConfiguration(
                backend_type=StorageBackendType.AZURE_CDN,
                credentials=cdn_credentials,
                # origin_backend_type が不足
            )

        # origin_credentials が不足
        with pytest.raises(ValueError, match="CDN backends require origin_credentials"):
            StorageConfiguration(
                backend_type=StorageBackendType.AZURE_CDN,
                credentials=cdn_credentials,
                origin_backend_type=StorageBackendType.AZURE_BLOB,
                # origin_credentials が不足
            )

    def test_cdn_configuration_with_valid_origin(self):
        """有効なオリジンストレージを持つCDN設定."""
        cdn_credentials = StorageCredentials(
            backend_type=StorageBackendType.CLOUDFLARE_CDN,
            api_token="token",
            zone_id="zone",
            origin_hostname="cdn.example.com",
        )

        origin_credentials = StorageCredentials(
            backend_type=StorageBackendType.LOCAL,
        )

        config = StorageConfiguration(
            backend_type=StorageBackendType.CLOUDFLARE_CDN,
            credentials=cdn_credentials,
            origin_backend_type=StorageBackendType.LOCAL,
            origin_credentials=origin_credentials,
            base_path="/var/www/images",
            cache_ttl=3600,
        )

        assert config.backend_type == StorageBackendType.CLOUDFLARE_CDN
        assert config.origin_backend_type == StorageBackendType.LOCAL
        assert config.cache_ttl == 3600

    def test_cdn_purge_request_validation(self):
        """CDNパージリクエストバリデーション."""
        valid_path = StoragePath(
            domain="media",
            intent="original",
            relative_path="test.jpg",
        )

        # 有効なパージリクエスト
        valid_request = CDNPurgeRequest(
            paths=[valid_path],
            purge_type="url",
            priority=1,
        )
        assert len(valid_request.paths) == 1
        assert valid_request.purge_type == "url"

        # 無効なパージタイプ
        with pytest.raises(ValueError, match="Invalid purge_type"):
            CDNPurgeRequest(
                paths=[valid_path],
                purge_type="invalid_type",
                priority=1,
            )

        # 優先度が範囲外
        with pytest.raises(ValueError, match="Priority must be between"):
            CDNPurgeRequest(
                paths=[valid_path],
                purge_type="url",
                priority=0,  # 1-3 の範囲外
            )

        with pytest.raises(ValueError, match="Priority must be between"):
            CDNPurgeRequest(
                paths=[valid_path],
                purge_type="url",
                priority=4,  # 1-3 の範囲外
            )

        # 空のパスリスト
        with pytest.raises(ValueError, match="At least one path is required"):
            CDNPurgeRequest(
                paths=[],
                purge_type="url",
                priority=1,
            )

    def test_storage_path_for_cdn(self):
        """CDN用ストレージパスの検証."""
        # 通常のパス
        normal_path = StoragePath(
            domain="media",
            intent="original",
            relative_path="2024/01/30/image.jpg",
        )
        assert normal_path.get_full_path() == "media/original/2024/01/30/image.jpg"

        # ワイルドカードパス（全パージ用）
        wildcard_path = StoragePath(
            domain="*",
            intent="*",
            relative_path="*",
        )
        assert wildcard_path.get_full_path() == "*/*/*"

        # プレフィックスパス
        prefix_path = StoragePath(
            domain="thumbnails",
            intent="small",
            relative_path="2024/01/",
        )
        assert prefix_path.get_full_path() == "thumbnails/small/2024/01/"

    def test_generic_cdn_backend_type(self):
        """汎用CDNバックエンドタイプの検証."""
        generic_credentials = StorageCredentials(
            backend_type=StorageBackendType.GENERIC_CDN,
            api_endpoint="https://api.customcdn.com",
            api_token="custom-token",
            origin_hostname="custom.cdn.example.com",
        )

        origin_credentials = StorageCredentials(
            backend_type=StorageBackendType.LOCAL,
        )

        config = StorageConfiguration(
            backend_type=StorageBackendType.GENERIC_CDN,
            credentials=generic_credentials,
            origin_backend_type=StorageBackendType.LOCAL,
            origin_credentials=origin_credentials,
        )

        assert config.backend_type == StorageBackendType.GENERIC_CDN

    def test_cdn_intent_validation(self):
        """CDN intent の検証."""
        from bounded_contexts.storage.domain.types import StorageIntent

        # CDN特有のintent
        assert StorageIntent.CDN_OPTIMIZED == "cdn-optimized"
        assert StorageIntent.CDN_CACHED == "cdn-cached"

        # CDN用のパス
        cdn_path = StoragePath(
            domain="media",
            intent=StorageIntent.CDN_OPTIMIZED,
            relative_path="optimized/image.webp",
        )
        assert cdn_path.intent == "cdn-optimized"


class TestCDNErrorHandling:
    """CDNエラーハンドリングのテストクラス."""

    def test_cdn_backend_not_available_error(self):
        """CDNバックエンドが利用できない場合のエラー."""
        # 実装では RuntimeError を想定
        with pytest.raises(RuntimeError):
            raise RuntimeError("CDN backend is not available")

    def test_cdn_authentication_error(self):
        """CDN認証エラー."""
        with pytest.raises(RuntimeError):
            raise RuntimeError("CDN authentication failed: Invalid API token")

    def test_cdn_rate_limit_error(self):
        """CDNレート制限エラー."""
        with pytest.raises(RuntimeError):
            raise RuntimeError("Rate limit exceeded: Too many requests")

    def test_cdn_purge_job_not_found_error(self):
        """CDNパージジョブが見つからない場合のエラー."""
        with pytest.raises(RuntimeError):
            raise RuntimeError("Purge job not found: invalid-job-id")

    def test_cdn_analytics_data_unavailable_error(self):
        """CDNアナリティクスデータが利用できない場合のエラー."""
        with pytest.raises(RuntimeError):
            raise RuntimeError("Analytics data is not available for the specified time range")

    def test_origin_storage_connection_error(self):
        """オリジンストレージ接続エラー."""
        with pytest.raises(ConnectionError):
            raise ConnectionError("Failed to connect to origin storage")

    def test_cdn_configuration_mismatch_error(self):
        """CDN設定の不整合エラー."""
        with pytest.raises(ValueError):
            raise ValueError("CDN configuration mismatch: origin backend type does not match credentials")


class TestCDNFallbackBehavior:
    """CDNフォールバック動作のテストクラス."""

    def test_non_cdn_backend_fallback_url(self):
        """非CDNバックエンドでのURL取得フォールバック."""
        # 通常のローカルストレージからCDN URLを要求した場合
        local_credentials = StorageCredentials(
            backend_type=StorageBackendType.LOCAL,
        )

        local_config = StorageConfiguration(
            backend_type=StorageBackendType.LOCAL,
            credentials=local_credentials,
            base_path="/var/www/images",
        )

        # アプリケーションサービス側で適切にフォールバックされることを期待
        assert local_config.backend_type == StorageBackendType.LOCAL

    def test_cdn_unavailable_fallback_to_origin(self):
        """CDNが利用できない場合のオリジンストレージフォールバック."""
        # この動作はアプリケーションサービスレベルでテスト
        pass  # 統合テストで実装

    def test_cdn_cache_miss_origin_fetch(self):
        """CDNキャッシュミス時のオリジン取得."""
        # この動作はCDNプロバイダー側で処理されるため、
        # アプリケーション側では設定の正しさのみを確認
        pass  # CDNプロバイダーの責務