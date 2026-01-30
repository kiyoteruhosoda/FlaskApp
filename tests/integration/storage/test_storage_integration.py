"""Storage境界文脈の結合テスト."""

import io
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bounded_contexts.storage.application import (
    StorageApplicationService,
    StorageBackendFactory,
)
from bounded_contexts.storage.domain import (
    StorageBackendType,
    StorageConfiguration,
    StorageCredentials,
    StorageDomain,
    StorageException,
    StorageIntent,
    StoragePath,
)
from bounded_contexts.storage.infrastructure import (
    InMemoryStorageRepository,
    LocalStorage,
)


class TestStorageIntegration:
    """Storage境界文脈の統合テスト."""
    
    @pytest.fixture
    def temp_storage_dir(self):
        """テンポラリストレージディレクトリ."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir
    
    @pytest.fixture
    def repository(self):
        """インメモリリポジトリ."""
        return InMemoryStorageRepository()
    
    @pytest.fixture
    def local_config(self, temp_storage_dir):
        """ローカルストレージ設定."""
        credentials = StorageCredentials(backend_type=StorageBackendType.LOCAL)
        return StorageConfiguration(
            backend_type=StorageBackendType.LOCAL,
            credentials=credentials,
            base_path=temp_storage_dir,
        )
    
    @pytest.fixture
    def azure_config(self):
        """Azure Blobストレージ設定."""
        credentials = StorageCredentials(
            backend_type=StorageBackendType.AZURE_BLOB,
            connection_string="DefaultEndpointsProtocol=https;AccountName=test;AccountKey=key==",
            container_name="test-container",
        )
        return StorageConfiguration(
            backend_type=StorageBackendType.AZURE_BLOB,
            credentials=credentials,
            base_path="azure-test",
        )
    
    @pytest.fixture
    def storage_service(self, repository):
        """Storageアプリケーションサービス."""
        return StorageApplicationService(repository)
    
    def test_end_to_end_local_storage_workflow(self, storage_service, local_config):
        """エンドツーエンドのローカルストレージワークフローテスト."""
        domain = "media"
        
        # 1. ストレージ設定
        storage_service.configure_storage(domain, local_config)
        
        # 2. 設定確認
        domains = storage_service.get_storage_domains()
        assert domain in domains
        
        # 3. ファイルアップロード
        storage_path = StoragePath(
            domain=StorageDomain.MEDIA,
            intent=StorageIntent.ORIGINAL,
            relative_path="test/integration.jpg",
        )
        
        content = b"integration test content"
        metadata = storage_service.upload_file(domain, storage_path, content)
        
        assert metadata.path == storage_path
        assert metadata.size == len(content)
        
        # 4. ファイル存在確認
        assert storage_service.file_exists(domain, storage_path)
        
        # 5. メタデータ取得
        retrieved_metadata = storage_service.get_file_metadata(domain, storage_path)
        assert retrieved_metadata.size == len(content)
        
        # 6. ファイルダウンロード
        downloaded_content = storage_service.download_file(domain, storage_path)
        assert downloaded_content == content
        
        # 7. ファイルコピー
        copy_path = StoragePath(
            domain=StorageDomain.MEDIA,
            intent=StorageIntent.ORIGINAL,
            relative_path="test/integration_copy.jpg",
        )
        
        copy_metadata = storage_service.copy_file(domain, storage_path, domain, copy_path)
        assert copy_metadata.size == len(content)
        assert storage_service.file_exists(domain, copy_path)
        
        # 8. 署名付きURL生成
        download_url = storage_service.generate_download_url(domain, storage_path)
        assert download_url.startswith("file://")
        
        # 9. ファイル削除
        storage_service.delete_file(domain, storage_path)
        assert not storage_service.file_exists(domain, storage_path)
        
        # 10. 設定削除
        storage_service.remove_storage_configuration(domain)
        assert domain not in storage_service.get_storage_domains()
    
    def test_stream_upload_download(self, storage_service, local_config):
        """ストリーミングアップロード・ダウンロードテスト."""
        domain = "streaming"
        storage_service.configure_storage(domain, local_config)
        
        storage_path = StoragePath(
            domain=StorageDomain.MEDIA,
            intent=StorageIntent.ORIGINAL,
            relative_path="stream/test.bin",
        )
        
        # ストリームアップロード
        content = b"streaming test content with more data"
        stream_in = io.BytesIO(content)
        
        metadata = storage_service.upload_file_stream(domain, storage_path, stream_in)
        assert metadata.size == len(content)
        
        # ストリームダウンロード
        stream_out = storage_service.download_file_stream(domain, storage_path)
        downloaded_content = stream_out.read()
        stream_out.close()
        
        assert downloaded_content == content
    
    def test_cross_domain_copy(self, storage_service, local_config):
        """異なるドメイン間でのファイルコピーテスト."""
        source_domain = "source"
        dest_domain = "destination"
        
        # 両ドメインを設定
        storage_service.configure_storage(source_domain, local_config)
        
        # 別のベースパスで宛先ドメインを設定
        dest_config = StorageConfiguration(
            backend_type=local_config.backend_type,
            credentials=local_config.credentials,
            base_path=local_config.base_path + "_dest",
        )
        storage_service.configure_storage(dest_domain, dest_config)
        
        # ソースファイルをアップロード
        source_path = StoragePath(
            domain=StorageDomain.MEDIA,
            intent=StorageIntent.ORIGINAL,
            relative_path="cross/source.jpg",
        )
        
        content = b"cross-domain copy test"
        storage_service.upload_file(source_domain, source_path, content)
        
        # 別ドメインにコピー
        dest_path = StoragePath(
            domain=StorageDomain.MEDIA,
            intent=StorageIntent.ORIGINAL,
            relative_path="cross/destination.jpg",
        )
        
        copy_metadata = storage_service.copy_file(
            source_domain, source_path,
            dest_domain, dest_path
        )
        
        assert copy_metadata.size == len(content)
        
        # 両方のドメインでファイルが存在することを確認
        assert storage_service.file_exists(source_domain, source_path)
        assert storage_service.file_exists(dest_domain, dest_path)
        
        # 内容も同じであることを確認
        source_content = storage_service.download_file(source_domain, source_path)
        dest_content = storage_service.download_file(dest_domain, dest_path)
        assert source_content == dest_content == content
    
    def test_list_files(self, storage_service, local_config):
        """ファイル一覧取得テスト."""
        domain = "listing"
        storage_service.configure_storage(domain, local_config)
        
        # 複数ファイルをアップロード
        files = [
            ("dir1/file1.txt", b"content1"),
            ("dir1/file2.txt", b"content2"), 
            ("dir1/subdir/file3.txt", b"content3"),
            ("dir2/file4.txt", b"content4"),
        ]
        
        for rel_path, content in files:
            path = StoragePath(
                domain=StorageDomain.MEDIA,
                intent=StorageIntent.ORIGINAL,
                relative_path=rel_path,
            )
            storage_service.upload_file(domain, path, content)
        
        # dir1配下を一覧取得
        prefix = StoragePath(
            domain=StorageDomain.MEDIA,
            intent=StorageIntent.ORIGINAL,
            relative_path="dir1/",
        )
        
        listed_files = list(storage_service.list_files(domain, prefix))
        
        # dir1配下の3ファイルが取得される
        assert len(listed_files) == 3
        relative_paths = [f.path.relative_path for f in listed_files]
        expected_paths = ["dir1/file1.txt", "dir1/file2.txt", "dir1/subdir/file3.txt"]
        for expected in expected_paths:
            assert any(expected in path for path in relative_paths)
    
    def test_backend_factory_polymorphism(self):
        """バックエンドファクトリのポリモーフィズムテスト."""
        factory = StorageBackendFactory()
        
        # ローカルストレージ作成
        local_creds = StorageCredentials(backend_type=StorageBackendType.LOCAL)
        local_config = StorageConfiguration(
            backend_type=StorageBackendType.LOCAL,
            credentials=local_creds,
            base_path="/tmp/test",
        )
        
        local_backend = factory.create_backend(local_config)
        assert isinstance(local_backend, LocalStorage)
        
        # Azure Blob作成（モック使用）
        azure_creds = StorageCredentials(
            backend_type=StorageBackendType.AZURE_BLOB,
            connection_string="DefaultEndpointsProtocol=https;AccountName=test;AccountKey=key==",
        )
        azure_config = StorageConfiguration(
            backend_type=StorageBackendType.AZURE_BLOB,
            credentials=azure_creds,
        )
        
        with patch.dict('sys.modules', {
            'azure.storage.blob': MagicMock(),
            'azure.core.exceptions': MagicMock(),
        }):
            with patch('bounded_contexts.storage.infrastructure.azure_blob.BlobServiceClient'):
                with patch('bounded_contexts.storage.infrastructure.azure_blob.ResourceExistsError'):
                    azure_backend = factory.create_backend(azure_config)
                    from bounded_contexts.storage.infrastructure import AzureBlobStorage
                    assert isinstance(azure_backend, AzureBlobStorage)
        
        # 未対応バックエンド
        unsupported_creds = StorageCredentials(
            backend_type=StorageBackendType.S3,
            access_key="key",
            secret_key="secret",
        )
        unsupported_config = StorageConfiguration(
            backend_type=StorageBackendType.S3,
            credentials=unsupported_creds,
        )
        
        with pytest.raises(StorageException, match="未対応のバックエンドタイプ"):
            factory.create_backend(unsupported_config)
    
    def test_configuration_validation_on_save(self, storage_service):
        """設定保存時のバリデーションテスト."""
        # 不正な設定を保存しようとしてエラーになる
        # StorageCredentialsレベルでバリデーションエラーが発生
        with pytest.raises(ValueError, match="Azure Blob requires connection_string or account_name"):
            invalid_creds = StorageCredentials(
                backend_type=StorageBackendType.AZURE_BLOB,
                # connection_stringもaccount_name+access_keyも未設定
            )
    
    def test_error_handling_for_missing_domain(self, storage_service):
        """存在しないドメインでのエラーハンドリングテスト."""
        storage_path = StoragePath(
            domain=StorageDomain.MEDIA,
            intent=StorageIntent.ORIGINAL,
            relative_path="test.jpg",
        )
        
        # file_existsは例外をキャッチしてFalseを返す
        result = storage_service.file_exists("nonexistent-domain", storage_path)
        assert result is False
        
        # upload_fileは例外を再スローする
        with pytest.raises(StorageException, match="Storage設定が見つかりません"):
            storage_service.upload_file("nonexistent-domain", storage_path, b"test")
    
    def test_backend_caching(self, storage_service, local_config):
        """バックエンドキャッシングテスト."""
        domain = "caching-test"
        storage_service.configure_storage(domain, local_config)
        
        # 最初のアクセス
        backend1 = storage_service._get_backend(domain)
        
        # 2回目のアクセス（キャッシュから取得）
        backend2 = storage_service._get_backend(domain)
        
        # 同じインスタンス
        assert backend1 is backend2
        
        # 設定を削除するとキャッシュもクリアされる
        storage_service.remove_storage_configuration(domain)
        
        # 再設定後は新しいインスタンス
        storage_service.configure_storage(domain, local_config)
        backend3 = storage_service._get_backend(domain)
        
        assert backend3 is not backend1