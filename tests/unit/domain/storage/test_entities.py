"""Storage境界文脈のドメイン層テスト."""

import pytest
from pathlib import Path

from bounded_contexts.storage.domain import (
    StoragePath,
    StorageCredentials,
    StorageConfiguration,
    StorageMetadata,
    StorageException,
    StorageNotFoundException,
    StoragePermissionException,
    StorageBackendType,
    StorageDomain,
    StorageIntent,
    StorageResolution,
    StoragePathResolverService,
)


class TestStoragePath:
    """StoragePath値オブジェクトのテスト."""
    
    def test_valid_path_creation(self) -> None:
        """有効なパス作成テスト."""
        path = StoragePath(
            domain=StorageDomain.MEDIA,
            intent=StorageIntent.ORIGINAL,
            relative_path="photos/2024/01/image.jpg",
        )
        
        assert path.domain == StorageDomain.MEDIA
        assert path.intent == StorageIntent.ORIGINAL
        assert path.relative_path == "photos/2024/01/image.jpg"
        assert path.resolution is None
    
    def test_path_with_resolution(self) -> None:
        """解像度付きパステスト."""
        path = StoragePath(
            domain=StorageDomain.THUMBNAILS,
            intent=StorageIntent.THUMBNAIL,
            relative_path="thumbs/image.jpg",
            resolution=StorageResolution.MEDIUM,
        )
        
        assert path.resolution == StorageResolution.MEDIUM
    
    def test_empty_relative_path_raises_error(self) -> None:
        """空の相対パスでエラーテスト."""
        with pytest.raises(ValueError, match="relative_pathは空文字列にできません"):
            StoragePath(
                domain=StorageDomain.MEDIA,
                intent=StorageIntent.ORIGINAL,
                relative_path="",
            )
    
    def test_absolute_path_raises_error(self) -> None:
        """絶対パスでエラーテスト."""
        with pytest.raises(ValueError, match="absolute pathは使用できません"):
            StoragePath(
                domain=StorageDomain.MEDIA,
                intent=StorageIntent.ORIGINAL,
                relative_path="/absolute/path/image.jpg",
            )
    
    def test_path_parts(self) -> None:
        """パス要素の分割テスト."""
        path = StoragePath(
            domain=StorageDomain.MEDIA,
            intent=StorageIntent.ORIGINAL,
            relative_path="photos/2024/01/image.jpg",
        )
        
        assert path.path_parts == ("photos", "2024", "01", "image.jpg")
    
    def test_with_resolution(self) -> None:
        """解像度指定での新インスタンス作成テスト."""
        original = StoragePath(
            domain=StorageDomain.THUMBNAILS,
            intent=StorageIntent.THUMBNAIL,
            relative_path="thumbs/image.jpg",
        )
        
        with_resolution = original.with_resolution(StorageResolution.LARGE)
        
        assert with_resolution.resolution == StorageResolution.LARGE
        assert with_resolution.domain == original.domain
        assert with_resolution.intent == original.intent
        assert with_resolution.relative_path == original.relative_path
        # 元のインスタンスは変更されない
        assert original.resolution is None


class TestStorageCredentials:
    """StorageCredentials値オブジェクトのテスト."""
    
    def test_azure_blob_with_connection_string(self) -> None:
        """Azure Blob接続文字列認証テスト."""
        creds = StorageCredentials(
            backend_type=StorageBackendType.AZURE_BLOB,
            connection_string="DefaultEndpointsProtocol=https;AccountName=test;AccountKey=key==;EndpointSuffix=core.windows.net",
        )
        
        assert creds.backend_type == StorageBackendType.AZURE_BLOB
        assert creds.connection_string is not None
    
    def test_azure_blob_with_account_key(self) -> None:
        """Azure Blobアカウントキー認証テスト."""
        creds = StorageCredentials(
            backend_type=StorageBackendType.AZURE_BLOB,
            account_name="testaccount",
            access_key="testkey",
            container_name="photos",
        )
        
        assert creds.account_name == "testaccount"
        assert creds.access_key == "testkey"
        assert creds.container_name == "photos"
    
    def test_azure_blob_invalid_credentials_raises_error(self) -> None:
        """Azure Blob不正認証情報でエラーテスト."""
        with pytest.raises(ValueError, match="Azure Blob requires connection_string or account_name"):
            StorageCredentials(
                backend_type=StorageBackendType.AZURE_BLOB,
                # connection_stringもaccount_name+access_keyも未設定
            )
    
    def test_s3_credentials(self) -> None:
        """S3認証情報テスト."""
        creds = StorageCredentials(
            backend_type=StorageBackendType.S3,
            access_key="access123",
            secret_key="secret456",
            endpoint_url="https://s3.amazonaws.com",
        )
        
        assert creds.backend_type == StorageBackendType.S3
        assert creds.access_key == "access123"
        assert creds.secret_key == "secret456"
    
    def test_s3_invalid_credentials_raises_error(self) -> None:
        """S3不正認証情報でエラーテスト."""
        with pytest.raises(ValueError, match="S3 requires access_key and secret_key"):
            StorageCredentials(
                backend_type=StorageBackendType.S3,
                access_key="access123",
                # secret_keyが未設定
            )


class TestStorageConfiguration:
    """StorageConfiguration値オブジェクトのテスト."""
    
    def test_valid_configuration(self) -> None:
        """有効な設定作成テスト."""
        credentials = StorageCredentials(
            backend_type=StorageBackendType.AZURE_BLOB,
            connection_string="DefaultEndpointsProtocol=https;AccountName=test;AccountKey=key==",
        )
        
        config = StorageConfiguration(
            backend_type=StorageBackendType.AZURE_BLOB,
            credentials=credentials,
            base_path="/storage/photos",
            region="eastus",
            timeout=60,
            retry_count=5,
        )
        
        assert config.backend_type == StorageBackendType.AZURE_BLOB
        assert config.credentials == credentials
        assert config.base_path == "/storage/photos"
        assert config.region == "eastus"
        assert config.timeout == 60
        assert config.retry_count == 5
    
    def test_invalid_timeout_raises_error(self) -> None:
        """無効なタイムアウトでエラーテスト."""
        credentials = StorageCredentials(
            backend_type=StorageBackendType.AZURE_BLOB,
            connection_string="test",
        )
        
        with pytest.raises(ValueError, match="timeoutは正数である必要があります"):
            StorageConfiguration(
                backend_type=StorageBackendType.AZURE_BLOB,
                credentials=credentials,
                timeout=0,  # 無効値
            )
    
    def test_invalid_retry_count_raises_error(self) -> None:
        """無効なリトライ回数でエラーテスト."""
        credentials = StorageCredentials(
            backend_type=StorageBackendType.AZURE_BLOB,
            connection_string="test",
        )
        
        with pytest.raises(ValueError, match="retry_countは非負数である必要があります"):
            StorageConfiguration(
                backend_type=StorageBackendType.AZURE_BLOB,
                credentials=credentials,
                retry_count=-1,  # 無効値
            )
    
    def test_mismatched_backend_type_raises_error(self) -> None:
        """バックエンドタイプ不一致でエラーテスト."""
        credentials = StorageCredentials(
            backend_type=StorageBackendType.S3,
            access_key="key",
            secret_key="secret",
        )
        
        with pytest.raises(ValueError, match="credentials.backend_typeとbackend_typeが一致しません"):
            StorageConfiguration(
                backend_type=StorageBackendType.AZURE_BLOB,  # 不一致
                credentials=credentials,
            )


class TestStorageMetadata:
    """StorageMetadata値オブジェクトのテスト."""
    
    def test_valid_metadata(self) -> None:
        """有効なメタデータ作成テスト."""
        path = StoragePath(
            domain=StorageDomain.MEDIA,
            intent=StorageIntent.ORIGINAL,
            relative_path="image.jpg",
        )
        
        metadata = StorageMetadata(
            path=path,
            size=1024,
            content_type="image/jpeg",
            etag="abc123",
            last_modified="2024-01-30T12:00:00Z",
            custom_metadata={"user": "test", "version": "1"},
        )
        
        assert metadata.path == path
        assert metadata.size == 1024
        assert metadata.content_type == "image/jpeg"
        assert metadata.etag == "abc123"
        assert metadata.last_modified == "2024-01-30T12:00:00Z"
        assert metadata.custom_metadata == {"user": "test", "version": "1"}
    
    def test_negative_size_raises_error(self) -> None:
        """負のサイズでエラーテスト."""
        path = StoragePath(
            domain=StorageDomain.MEDIA,
            intent=StorageIntent.ORIGINAL,
            relative_path="image.jpg",
        )
        
        with pytest.raises(ValueError, match="sizeは非負数である必要があります"):
            StorageMetadata(
                path=path,
                size=-1,  # 無効値
            )


class TestStorageExceptions:
    """Storage例外クラスのテスト."""
    
    def test_storage_exception(self) -> None:
        """基底例外テスト."""
        path = StoragePath(
            domain=StorageDomain.MEDIA,
            intent=StorageIntent.ORIGINAL,
            relative_path="test.jpg",
        )
        
        exc = StorageException("テストエラー", path)
        
        assert str(exc) == "テストエラー"
        assert exc.path == path
    
    def test_storage_not_found_exception(self) -> None:
        """NotFound例外テスト."""
        path = StoragePath(
            domain=StorageDomain.MEDIA,
            intent=StorageIntent.ORIGINAL,
            relative_path="missing.jpg",
        )
        
        exc = StorageNotFoundException("ファイルが見つかりません", path)
        
        assert isinstance(exc, StorageException)
        assert str(exc) == "ファイルが見つかりません"
        assert exc.path == path
    
    def test_storage_permission_exception(self) -> None:
        """Permission例外テスト."""
        path = StoragePath(
            domain=StorageDomain.MEDIA,
            intent=StorageIntent.ORIGINAL,
            relative_path="restricted.jpg",
        )
        
        exc = StoragePermissionException("アクセス拒否", path)
        
        assert isinstance(exc, StorageException)
        assert str(exc) == "アクセス拒否"
        assert exc.path == path


class TestStoragePathResolverService:
    """StoragePathResolverServiceドメインサービスのテスト."""
    
    def test_resolve_full_path(self) -> None:
        """完全パス解決テスト."""
        resolver = StoragePathResolverService()
        
        path = StoragePath(
            domain=StorageDomain.MEDIA,
            intent=StorageIntent.ORIGINAL,
            relative_path="photos/image.jpg",
            resolution=StorageResolution.LARGE,
        )
        
        credentials = StorageCredentials(
            backend_type=StorageBackendType.LOCAL,
        )
        
        config = StorageConfiguration(
            backend_type=StorageBackendType.LOCAL,
            credentials=credentials,
            base_path="/storage",
        )
        
        full_path = resolver.resolve_full_path(path, config)
        
        assert full_path == "/storage/media/original/2048/photos/image.jpg"
    
    def test_resolve_full_path_no_base(self) -> None:
        """ベースパスなしの完全パス解決テスト."""
        resolver = StoragePathResolverService()
        
        path = StoragePath(
            domain=StorageDomain.THUMBNAILS,
            intent=StorageIntent.THUMBNAIL,
            relative_path="thumb.jpg",
        )
        
        credentials = StorageCredentials(backend_type=StorageBackendType.LOCAL)
        config = StorageConfiguration(
            backend_type=StorageBackendType.LOCAL,
            credentials=credentials,
            base_path="",
        )
        
        full_path = resolver.resolve_full_path(path, config)
        
        assert full_path == "thumbnails/thumbnail/thumb.jpg"
    
    def test_build_hierarchical_path_media(self) -> None:
        """メディアファイルの階層化パステスト."""
        resolver = StoragePathResolverService()
        
        path = StoragePath(
            domain=StorageDomain.MEDIA,
            intent=StorageIntent.ORIGINAL,
            relative_path="simple_filename.jpg",
        )
        
        hierarchical_path = resolver.build_hierarchical_path(path)
        
        # 現在日付ベースの階層化が行われる
        import datetime
        now = datetime.datetime.utcnow()
        expected = f"{now.year}/{now.month:02d}/{now.day:02d}/simple_filename.jpg"
        
        assert hierarchical_path == expected
    
    def test_build_hierarchical_path_already_hierarchical(self) -> None:
        """既に階層化済みパスのテスト."""
        resolver = StoragePathResolverService()
        
        path = StoragePath(
            domain=StorageDomain.MEDIA,
            intent=StorageIntent.ORIGINAL,
            relative_path="2024/01/30/image.jpg",
        )
        
        hierarchical_path = resolver.build_hierarchical_path(path)
        
        # すでに階層化済みなのでそのまま
        assert hierarchical_path == "2024/01/30/image.jpg"
    
    def test_build_hierarchical_path_non_media(self) -> None:
        """非メディアファイルの階層化テスト."""
        resolver = StoragePathResolverService()
        
        path = StoragePath(
            domain=StorageDomain.TEMP,
            intent=StorageIntent.CACHE,
            relative_path="temp_file.tmp",
        )
        
        hierarchical_path = resolver.build_hierarchical_path(path)
        
        # 非メディアはそのまま
        assert hierarchical_path == "temp_file.tmp"