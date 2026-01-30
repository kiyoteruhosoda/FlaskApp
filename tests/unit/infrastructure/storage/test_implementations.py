"""Storage境界文脈のインフラストラクチャ層テスト."""

import io
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bounded_contexts.storage.domain import (
    StorageBackendType,
    StorageConfiguration,
    StorageCredentials,
    StorageDomain,
    StorageException,
    StorageIntent,
    StorageNotFoundException,
    StoragePath,
    StoragePermissionException,
)
from bounded_contexts.storage.infrastructure import (
    AzureBlobStorage,
    InMemoryStorageRepository,
    JsonFileStorageRepository,
    LocalStorage,
)


class TestLocalStorage:
    """LocalStorageインフラ実装のテスト."""
    
    @pytest.fixture
    def temp_storage_dir(self):
        """テンポラリストレージディレクトリ."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir
    
    @pytest.fixture
    def local_storage(self, temp_storage_dir):
        """LocalStorageインスタンス."""
        credentials = StorageCredentials(backend_type=StorageBackendType.LOCAL)
        config = StorageConfiguration(
            backend_type=StorageBackendType.LOCAL,
            credentials=credentials,
            base_path=temp_storage_dir,
        )
        
        storage = LocalStorage()
        storage.initialize(config)
        return storage
    
    @pytest.fixture
    def sample_path(self):
        """サンプルストレージパス."""
        return StoragePath(
            domain=StorageDomain.MEDIA,
            intent=StorageIntent.ORIGINAL,
            relative_path="test/sample.txt",
        )
    
    def test_initialize_creates_base_directory(self, temp_storage_dir):
        """初期化時のベースディレクトリ作成テスト."""
        base_path = Path(temp_storage_dir) / "nonexistent"
        
        credentials = StorageCredentials(backend_type=StorageBackendType.LOCAL)
        config = StorageConfiguration(
            backend_type=StorageBackendType.LOCAL,
            credentials=credentials,
            base_path=str(base_path),
        )
        
        storage = LocalStorage()
        storage.initialize(config)
        
        assert base_path.exists()
        assert base_path.is_dir()
    
    def test_write_and_read(self, local_storage, sample_path):
        """書き込みと読み込みテスト."""
        content = b"test content"
        
        local_storage.write(sample_path, content)
        
        assert local_storage.exists(sample_path)
        read_content = local_storage.read(sample_path)
        assert read_content == content
    
    def test_write_stream_and_read_stream(self, local_storage, sample_path):
        """ストリーミング書き込み・読み込みテスト."""
        content = b"stream test content"
        stream_in = io.BytesIO(content)
        
        local_storage.write_stream(sample_path, stream_in)
        
        assert local_storage.exists(sample_path)
        
        stream_out = local_storage.read_stream(sample_path)
        read_content = stream_out.read()
        stream_out.close()
        
        assert read_content == content
    
    def test_get_metadata(self, local_storage, sample_path):
        """メタデータ取得テスト."""
        content = b"metadata test"
        local_storage.write(sample_path, content)
        
        metadata = local_storage.get_metadata(sample_path)
        
        assert metadata.path == sample_path
        assert metadata.size == len(content)
        assert metadata.content_type == "text/plain"  # mimetypesによる推測
        assert metadata.etag is not None
        assert metadata.last_modified is not None
    
    def test_copy(self, local_storage, sample_path):
        """ファイルコピーテスト."""
        content = b"copy test content"
        local_storage.write(sample_path, content)
        
        destination = StoragePath(
            domain=StorageDomain.MEDIA,
            intent=StorageIntent.ORIGINAL,
            relative_path="test/copy_dest.txt",
        )
        
        local_storage.copy(sample_path, destination)
        
        assert local_storage.exists(destination)
        assert local_storage.read(destination) == content
        # 元ファイルも残っている
        assert local_storage.exists(sample_path)
    
    def test_move(self, local_storage, sample_path):
        """ファイル移動テスト."""
        content = b"move test content"
        local_storage.write(sample_path, content)
        
        destination = StoragePath(
            domain=StorageDomain.MEDIA,
            intent=StorageIntent.ORIGINAL,
            relative_path="test/move_dest.txt",
        )
        
        local_storage.move(sample_path, destination)
        
        assert local_storage.exists(destination)
        assert local_storage.read(destination) == content
        # 元ファイルは削除されている
        assert not local_storage.exists(sample_path)
    
    def test_delete(self, local_storage, sample_path):
        """ファイル削除テスト."""
        content = b"delete test content"
        local_storage.write(sample_path, content)
        
        assert local_storage.exists(sample_path)
        local_storage.delete(sample_path)
        assert not local_storage.exists(sample_path)
    
    def test_delete_nonexistent_file(self, local_storage, sample_path):
        """存在しないファイル削除テスト（エラーなし）."""
        assert not local_storage.exists(sample_path)
        # エラーなく完了する
        local_storage.delete(sample_path)
    
    def test_list_objects(self, local_storage):
        """オブジェクト一覧取得テスト."""
        # 複数ファイルを作成
        files = [
            ("test/file1.txt", b"content1"),
            ("test/file2.txt", b"content2"),
            ("test/subdir/file3.txt", b"content3"),
        ]
        
        for rel_path, content in files:
            path = StoragePath(
                domain=StorageDomain.MEDIA,
                intent=StorageIntent.ORIGINAL,
                relative_path=rel_path,
            )
            local_storage.write(path, content)
        
        # プレフィックスで一覧取得
        prefix = StoragePath(
            domain=StorageDomain.MEDIA,
            intent=StorageIntent.ORIGINAL,
            relative_path="test/",
        )
        
        objects = list(local_storage.list_objects(prefix))
        
        assert len(objects) == 3
        relative_paths = [obj.path.relative_path for obj in objects]
        assert all(path in relative_paths for path, _ in files)
    
    def test_generate_presigned_url(self, local_storage, sample_path):
        """署名付きURL生成テスト（ローカルはfile://スキーム）."""
        content = b"url test content"
        local_storage.write(sample_path, content)
        
        url = local_storage.generate_presigned_url(sample_path)
        
        assert url.startswith("file://")
        assert sample_path.relative_path.replace("/", "%2F") in url or sample_path.relative_path in url
    
    def test_read_nonexistent_file_raises_not_found(self, local_storage, sample_path):
        """存在しないファイル読み込みでNotFound例外テスト."""
        with pytest.raises(StorageNotFoundException):
            local_storage.read(sample_path)
    
    def test_get_metadata_nonexistent_file_raises_not_found(self, local_storage, sample_path):
        """存在しないファイルメタデータ取得でNotFound例外テスト."""
        with pytest.raises(StorageNotFoundException):
            local_storage.get_metadata(sample_path)


class TestAzureBlobStorage:
    """AzureBlobStorageインフラ実装のテスト."""
    
    @pytest.fixture
    def azure_config(self):
        """Azureストレージ設定."""
        credentials = StorageCredentials(
            backend_type=StorageBackendType.AZURE_BLOB,
            connection_string="DefaultEndpointsProtocol=https;AccountName=test;AccountKey=key==",
            container_name="test-container",
        )
        return StorageConfiguration(
            backend_type=StorageBackendType.AZURE_BLOB,
            credentials=credentials,
            base_path="test-base",
        )
    
    @pytest.fixture
    def sample_path(self):
        """サンプルストレージパス."""
        return StoragePath(
            domain=StorageDomain.MEDIA,
            intent=StorageIntent.ORIGINAL,
            relative_path="test/sample.jpg",
        )
    
    def test_initialize_without_azure_package_raises_error(self, azure_config):
        """azure-storage-blobパッケージなしで初期化エラーテスト."""
        storage = AzureBlobStorage()
        
        # azure.storage.blobモジュールのimportをモック
        with patch.dict('sys.modules', {'azure.storage.blob': None}):
            with pytest.raises(StorageException, match="azure-storage-blobパッケージがインストールされていません"):
                storage.initialize(azure_config)
    
    def test_initialize_with_connection_string(self, azure_config):
        """接続文字列での初期化テスト."""
        # Azure Blobのモックテスト - 実際のazure-storage-blobは不要
        with patch.dict('sys.modules', {
            'azure.storage.blob': MagicMock(),
            'azure.core.exceptions': MagicMock(),
        }):
            # BlobServiceClientをモック
            mock_service_class = MagicMock()
            mock_client = MagicMock()
            mock_service_class.from_connection_string.return_value = mock_client
            
            mock_container = MagicMock()
            mock_client.get_container_client.return_value = mock_container
            
            # ResourceExistsErrorをモック
            mock_exists_error = MagicMock()
            mock_container.create_container.side_effect = mock_exists_error()
            
            # モックを使って初期化
            with patch('bounded_contexts.storage.infrastructure.azure_blob.BlobServiceClient', mock_service_class):
                with patch('bounded_contexts.storage.infrastructure.azure_blob.ResourceExistsError', mock_exists_error):
                    storage = AzureBlobStorage()
                    storage.initialize(azure_config)
                    
                    mock_service_class.from_connection_string.assert_called_once_with(
                        azure_config.credentials.connection_string
                    )
    
    def test_initialize_with_account_key(self):
        """アカウントキーでの初期化テスト."""
        credentials = StorageCredentials(
            backend_type=StorageBackendType.AZURE_BLOB,
            account_name="testaccount",
            access_key="testkey",
            container_name="test-container",
        )
        config = StorageConfiguration(
            backend_type=StorageBackendType.AZURE_BLOB,
            credentials=credentials,
        )
        
        with patch.dict('sys.modules', {
            'azure.storage.blob': MagicMock(),
            'azure.core.exceptions': MagicMock(),
        }):
            # BlobServiceClientをモック
            mock_service_class = MagicMock()
            mock_client = MagicMock()
            mock_service_class.return_value = mock_client
            
            mock_container = MagicMock()
            mock_client.get_container_client.return_value = mock_container
            
            # ResourceExistsErrorをモック
            mock_exists_error = MagicMock()
            
            with patch('bounded_contexts.storage.infrastructure.azure_blob.BlobServiceClient', mock_service_class):
                with patch('bounded_contexts.storage.infrastructure.azure_blob.ResourceExistsError', mock_exists_error):
                    storage = AzureBlobStorage()
                    storage.initialize(config)
                    
                    # アカウントURLでBlobServiceClientが作成される
                    mock_service_class.assert_called_once()
                    call_kwargs = mock_service_class.call_args[1]
                    assert call_kwargs['account_url'] == "https://testaccount.blob.core.windows.net"
                    assert call_kwargs['credential'] == "testkey"
    
    def test_initialize_with_invalid_credentials_raises_error(self):
        """不正認証情報で初期化エラーテスト."""
        # StorageCredentials自体で検証エラーが発生する
        with pytest.raises(ValueError, match="Azure Blob requires connection_string or account_name"):
            StorageCredentials(
                backend_type=StorageBackendType.AZURE_BLOB,
                # connection_stringもaccount_name+access_keyも未設定
            )
    
    def test_not_initialized_operations_raise_error(self, sample_path):
        """未初期化状態での操作エラーテスト."""
        storage = AzureBlobStorage()
        
        with pytest.raises(StorageException, match="Storageが初期化されていません"):
            storage.exists(sample_path)
        
        with pytest.raises(StorageException, match="Storageが初期化されていません"):
            storage.read(sample_path)
        
        with pytest.raises(StorageException, match="Storageが初期化されていません"):
            storage.write(sample_path, b"test")


class TestInMemoryStorageRepository:
    """InMemoryStorageRepositoryのテスト."""
    
    @pytest.fixture
    def repository(self):
        """リポジトリインスタンス."""
        return InMemoryStorageRepository()
    
    @pytest.fixture
    def sample_config(self):
        """サンプル設定."""
        credentials = StorageCredentials(
            backend_type=StorageBackendType.LOCAL,
        )
        return StorageConfiguration(
            backend_type=StorageBackendType.LOCAL,
            credentials=credentials,
            base_path="/test/storage",
        )
    
    def test_save_and_get_configuration(self, repository, sample_config):
        """設定保存・取得テスト."""
        domain = "media"
        
        # 初期状態では設定なし
        assert repository.get_configuration(domain) is None
        
        # 設定保存
        repository.save_configuration(domain, sample_config)
        
        # 設定取得
        retrieved = repository.get_configuration(domain)
        assert retrieved is not None
        assert retrieved.backend_type == sample_config.backend_type
        assert retrieved.base_path == sample_config.base_path
    
    def test_list_domains(self, repository, sample_config):
        """ドメイン一覧取得テスト."""
        assert repository.list_domains() == []
        
        repository.save_configuration("media", sample_config)
        repository.save_configuration("thumbnails", sample_config)
        
        domains = repository.list_domains()
        assert sorted(domains) == ["media", "thumbnails"]
    
    def test_delete_configuration(self, repository, sample_config):
        """設定削除テスト."""
        domain = "media"
        repository.save_configuration(domain, sample_config)
        
        assert repository.get_configuration(domain) is not None
        
        repository.delete_configuration(domain)
        
        assert repository.get_configuration(domain) is None
        assert domain not in repository.list_domains()
    
    def test_delete_nonexistent_configuration(self, repository):
        """存在しない設定削除テスト（エラーなし）."""
        # エラーなく完了する
        repository.delete_configuration("nonexistent")


class TestJsonFileStorageRepository:
    """JsonFileStorageRepositoryのテスト."""
    
    @pytest.fixture
    def temp_config_file(self):
        """テンポラリ設定ファイル."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            temp_path = f.name
        
        yield temp_path
        
        # クリーンアップ
        Path(temp_path).unlink(missing_ok=True)
    
    @pytest.fixture
    def repository(self, temp_config_file):
        """リポジトリインスタンス."""
        return JsonFileStorageRepository(temp_config_file)
    
    @pytest.fixture
    def sample_config(self):
        """サンプル設定."""
        credentials = StorageCredentials(
            backend_type=StorageBackendType.AZURE_BLOB,
            connection_string="DefaultEndpointsProtocol=https;AccountName=test;AccountKey=key==",
            container_name="test",
        )
        return StorageConfiguration(
            backend_type=StorageBackendType.AZURE_BLOB,
            credentials=credentials,
            base_path="/azure/storage",
            region="eastus",
            timeout=60,
            retry_count=5,
        )
    
    def test_config_file_creation(self, temp_config_file):
        """設定ファイル作成テスト."""
        # 既存ファイルを削除
        Path(temp_config_file).unlink()
        
        # リポジトリ作成により自動でファイル作成される
        JsonFileStorageRepository(temp_config_file)
        
        assert Path(temp_config_file).exists()
        assert Path(temp_config_file).read_text() == "{}"
    
    def test_save_and_get_configuration(self, repository, sample_config):
        """設定保存・取得テスト（JSON永続化）."""
        domain = "azure-media"
        
        # 設定保存
        repository.save_configuration(domain, sample_config)
        
        # 新しいリポジトリインスタンスでも取得可能（永続化確認）
        new_repository = JsonFileStorageRepository(repository._config_path)
        retrieved = new_repository.get_configuration(domain)
        
        assert retrieved is not None
        assert retrieved.backend_type == sample_config.backend_type
        assert retrieved.credentials.connection_string == sample_config.credentials.connection_string
        assert retrieved.base_path == sample_config.base_path
        assert retrieved.region == sample_config.region
        assert retrieved.timeout == sample_config.timeout
        assert retrieved.retry_count == sample_config.retry_count
    
    def test_serialization_deserialization(self, repository, sample_config):
        """シリアライゼーション・デシリアライゼーションテスト."""
        # 内部メソッドのテスト
        serialized = repository._serialize_configuration(sample_config)
        
        assert serialized["backend_type"] == "azure_blob"
        assert serialized["credentials"]["backend_type"] == "azure_blob"
        assert serialized["credentials"]["connection_string"] == sample_config.credentials.connection_string
        assert serialized["base_path"] == sample_config.base_path
        
        # デシリアライゼーション
        deserialized = repository._deserialize_configuration(serialized)
        
        assert deserialized.backend_type == sample_config.backend_type
        assert deserialized.credentials.connection_string == sample_config.credentials.connection_string
        assert deserialized.base_path == sample_config.base_path