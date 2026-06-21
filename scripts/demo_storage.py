"""Storage境界文脈の使用例デモ.

DDD + ポリモーフィズム実装による画像配置システムの例。
AzureBlobとローカルストレージの両方をサポート。
"""

from __future__ import annotations

import tempfile
from pathlib import Path

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


def demo_local_storage():
    """ローカルストレージでの画像配置デモ."""
    print("=== ローカルストレージ画像配置デモ ===")
    
    # 設定
    repository = InMemoryStorageRepository()
    storage_service = StorageApplicationService(repository)
    
    with tempfile.TemporaryDirectory() as temp_dir:
        # ローカルストレージ設定
        credentials = StorageCredentials(backend_type=StorageBackendType.LOCAL)
        config = StorageConfiguration(
            backend_type=StorageBackendType.LOCAL,
            credentials=credentials,
            base_path=temp_dir,
        )
        
        domain = "photos"
        storage_service.configure_storage(domain, config)
        
        # 画像ファイルをアップロード
        image_path = StoragePath(
            domain=StorageDomain.MEDIA,
            intent=StorageIntent.ORIGINAL,
            relative_path="2024/01/30/vacation.jpg",
        )
        
        image_content = b"fake JPEG image content"
        metadata = storage_service.upload_file(domain, image_path, image_content)
        
        print(f"アップロード完了: {metadata.path.relative_path}")
        print(f"ファイルサイズ: {metadata.size} bytes")
        
        # サムネイルも作成
        thumb_path = StoragePath(
            domain=StorageDomain.THUMBNAILS,
            intent=StorageIntent.THUMBNAIL,
            relative_path="2024/01/30/vacation.jpg",
        )
        
        thumb_content = b"fake thumbnail JPEG content"
        thumb_metadata = storage_service.upload_file(domain, thumb_path, thumb_content)
        
        print(f"サムネイル作成: {thumb_metadata.path.relative_path}")
        
        # 画像ダウンロード
        downloaded = storage_service.download_file(domain, image_path)
        print(f"ダウンロード確認: {len(downloaded)} bytes")
        
        # ファイル一覧取得
        prefix = StoragePath(
            domain=StorageDomain.MEDIA,
            intent=StorageIntent.ORIGINAL,
            relative_path="2024/01/30/",
        )
        
        files = list(storage_service.list_files(domain, prefix))
        print(f"画像一覧: {len(files)} 件")
        for file in files:
            print(f"  - {file.path.relative_path} ({file.size} bytes)")


def demo_azure_blob_storage():
    """AzureBlob画像配置のデモ（設定のみ、実際の接続は不要）."""
    print("\n=== AzureBlob画像配置設定デモ ===")
    
    # 設定
    repository = InMemoryStorageRepository()
    storage_service = StorageApplicationService(repository)
    
    try:
        # AzureBlob設定
        credentials = StorageCredentials(
            backend_type=StorageBackendType.AZURE_BLOB,
            connection_string="DefaultEndpointsProtocol=https;AccountName=photonest;AccountKey=xxxxxxxxxxxx;EndpointSuffix=core.windows.net",
            container_name="photos",
        )
        config = StorageConfiguration(
            backend_type=StorageBackendType.AZURE_BLOB,
            credentials=credentials,
            base_path="media",
            region="eastus",
            timeout=60,
        )
        
        domain = "azure-photos"
        storage_service.configure_storage(domain, config)
        
        print(f"AzureBlob設定完了: domain={domain}")
        print(f"バックエンドタイプ: {config.backend_type.value}")
        print(f"コンテナ名: {config.credentials.container_name}")
        print(f"リージョン: {config.region}")
        
        # ポリモーフィズムの実証 - 設定済みドメインの一覧
        domains = storage_service.get_storage_domains()
        print(f"設定済みドメイン: {domains}")
        
        # 画像パスの例
        image_path = StoragePath(
            domain=StorageDomain.MEDIA,
            intent=StorageIntent.ORIGINAL,
            relative_path="user123/2024/01/30/beach_photo.jpg",
        )
        
        print(f"画像パス例: {image_path.relative_path}")
        print(f"ドメイン: {image_path.domain.value}")
        print(f"用途: {image_path.intent.value}")
        
        # この時点でAzureへの実際の接続は行われていない
        # 実際のファイル操作時にBlobServiceClientが初期化される
        print("（実際のAzure接続は、ファイル操作時に行われます）")
        
    except Exception as e:
        print(f"AzureBlob設定エラー: {e}")


def demo_polymorphism():
    """ポリモーフィズム実証デモ."""
    print("\n=== ポリモーフィズム実証デモ ===")
    
    from bounded_contexts.storage.application import StorageBackendFactory
    
    factory = StorageBackendFactory()
    
    # ローカルストレージ
    local_creds = StorageCredentials(backend_type=StorageBackendType.LOCAL)
    local_config = StorageConfiguration(
        backend_type=StorageBackendType.LOCAL,
        credentials=local_creds,
        base_path="/tmp/storage",
    )
    
    local_backend = factory.create_backend(local_config)
    print(f"ローカルバックエンド: {type(local_backend).__name__}")
    
    # Azure Blob（設定のみ）
    azure_creds = StorageCredentials(
        backend_type=StorageBackendType.AZURE_BLOB,
        connection_string="DefaultEndpointsProtocol=https;AccountName=test;AccountKey=key==",
    )
    azure_config = StorageConfiguration(
        backend_type=StorageBackendType.AZURE_BLOB,
        credentials=azure_creds,
    )
    
    try:
        azure_backend = factory.create_backend(azure_config)
        print(f"Azureバックエンド: {type(azure_backend).__name__}")
    except Exception as e:
        print(f"Azureバックエンド作成（期待通りのエラー）: {e}")
    
    # すべてStorageBackendプロトコルを実装
    print("全てのバックエンドがStorageBackendプロトコルに準拠")
    
    # 同じインターフェースで異なる実装を使用可能
    # これによりDDDの境界文脈内でポリモーフィズムが実現されている


def main():
    """メインデモ実行."""
    print("Storage境界文脈 - DDD + ポリモーフィズム実装デモ")
    print("=" * 60)
    
    demo_local_storage()
    demo_azure_blob_storage()
    demo_polymorphism()
    
    print("\n" + "=" * 60)
    print("デモ完了")
    print("✅ DDD原則に基づく設計")
    print("✅ ポリモーフィズムによる柔軟な実装")
    print("✅ AzureBlob対応画像配置システム")


if __name__ == "__main__":
    main()