"""Azure Blob Storage実装."""

from __future__ import annotations

import io
from typing import IO, Iterator
from urllib.parse import quote

from ..domain import (
    StorageBackend,
    StorageConfiguration,
    StorageException,
    StorageMetadata,
    StorageNotFoundException,
    StoragePath,
    StoragePathResolverService,
    StoragePermissionException,
)

__all__ = ["AzureBlobStorage"]


class AzureBlobStorage:
    """Azure Blob Storageのストレージバックエンド実装."""
    
    def __init__(self) -> None:
        self._blob_service_client: Any = None
        self._container_client: Any = None
        self._configuration: StorageConfiguration | None = None
        self._path_resolver = StoragePathResolverService()
    
    def initialize(self, configuration: StorageConfiguration) -> None:
        """Azure Blob Storageクライアントを初期化."""
        # ImportErrorを避けるために、グローバル宣言を最初に
        global BlobServiceClient, ResourceExistsError, ResourceNotFoundError, HttpResponseError
        
        try:
            # azure-storage-blobが利用可能な場合のみインポート
            from azure.core.exceptions import (
                ResourceExistsError,
                ResourceNotFoundError,
                HttpResponseError,
            )
            from azure.storage.blob import BlobServiceClient
            
            self._configuration = configuration
            
            # 接続文字列またはアカウント情報で認証
            if configuration.credentials.connection_string:
                self._blob_service_client = BlobServiceClient.from_connection_string(
                    configuration.credentials.connection_string
                )
            elif configuration.credentials.account_name and configuration.credentials.access_key:
                account_url = f"https://{configuration.credentials.account_name}.blob.core.windows.net"
                self._blob_service_client = BlobServiceClient(
                    account_url=account_url,
                    credential=configuration.credentials.access_key,
                )
            else:
                raise StorageException("Azure Blob認証情報が不正です")
            
            # コンテナクライアントを取得
            container_name = configuration.credentials.container_name or "default"
            self._container_client = self._blob_service_client.get_container_client(container_name)
            
            # コンテナが存在しない場合は作成
            try:
                self._container_client.create_container()
            except ResourceExistsError:
                pass  # 既に存在する場合は無視
                
        except ImportError as import_error:
            raise StorageException(
                f"Azure Blob Storage初期化エラー: 必要なパッケージが正しくインストールされていません。\n"
                f"詳細: {import_error}\n"
                f"requirements.txtの依存関係を確認してください。"
            )
        except Exception as e:
            raise StorageException(f"Azure Blob Storage初期化エラー: {e}")
    
    def exists(self, path: StoragePath) -> bool:
        """ブロブが存在するかチェック."""
        if not self._container_client:
            raise StorageException("Storageが初期化されていません")
        
        try:
            blob_name = self._resolve_blob_name(path)
            blob_client = self._container_client.get_blob_client(blob_name)
            return blob_client.exists()
        except Exception as e:
            raise StorageException(f"存在チェックエラー: {e}", path)
    
    def get_metadata(self, path: StoragePath) -> StorageMetadata:
        """ブロブメタデータを取得."""
        if not self._container_client:
            raise StorageException("Storageが初期化されていません")
        
        try:
            blob_name = self._resolve_blob_name(path)
            blob_client = self._container_client.get_blob_client(blob_name)
            
            properties = blob_client.get_blob_properties()
            
            return StorageMetadata(
                path=path,
                size=properties.size,
                content_type=properties.content_settings.content_type,
                etag=properties.etag,
                last_modified=properties.last_modified.isoformat() if properties.last_modified else None,
                custom_metadata=properties.metadata,
            )
        except Exception as e:
            if "BlobNotFound" in str(e):
                raise StorageNotFoundException(f"ブロブが見つかりません: {path.relative_path}", path)
            raise StorageException(f"メタデータ取得エラー: {e}", path)
    
    def read(self, path: StoragePath) -> bytes:
        """ブロブの内容を読み込み."""
        if not self._container_client:
            raise StorageException("Storageが初期化されていません")
        
        try:
            blob_name = self._resolve_blob_name(path)
            blob_client = self._container_client.get_blob_client(blob_name)
            
            download_stream = blob_client.download_blob()
            return download_stream.readall()
        except Exception as e:
            if "BlobNotFound" in str(e):
                raise StorageNotFoundException(f"ブロブが見つかりません: {path.relative_path}", path)
            raise StorageException(f"読み込みエラー: {e}", path)
    
    def read_stream(self, path: StoragePath) -> IO[bytes]:
        """ブロブをストリーミング読み込み."""
        if not self._container_client:
            raise StorageException("Storageが初期化されていません")
        
        try:
            blob_name = self._resolve_blob_name(path)
            blob_client = self._container_client.get_blob_client(blob_name)
            
            download_stream = blob_client.download_blob()
            return io.BytesIO(download_stream.readall())
        except Exception as e:
            if "BlobNotFound" in str(e):
                raise StorageNotFoundException(f"ブロブが見つかりません: {path.relative_path}", path)
            raise StorageException(f"ストリーム読み込みエラー: {e}", path)
    
    def write(self, path: StoragePath, content: bytes) -> None:
        """ブロブに内容を書き込み."""
        if not self._container_client:
            raise StorageException("Storageが初期化されていません")
        
        try:
            blob_name = self._resolve_blob_name(path)
            blob_client = self._container_client.get_blob_client(blob_name)
            
            blob_client.upload_blob(content, overwrite=True)
        except Exception as e:
            if "Forbidden" in str(e):
                raise StoragePermissionException(f"書き込み権限エラー: {path.relative_path}", path)
            raise StorageException(f"書き込みエラー: {e}", path)
    
    def write_stream(self, path: StoragePath, stream: IO[bytes]) -> None:
        """ストリーミングでブロブを書き込み."""
        if not self._container_client:
            raise StorageException("Storageが初期化されていません")
        
        try:
            blob_name = self._resolve_blob_name(path)
            blob_client = self._container_client.get_blob_client(blob_name)
            
            blob_client.upload_blob(stream, overwrite=True)
        except Exception as e:
            if "Forbidden" in str(e):
                raise StoragePermissionException(f"書き込み権限エラー: {path.relative_path}", path)
            raise StorageException(f"ストリーム書き込みエラー: {e}", path)
    
    def copy(self, source: StoragePath, destination: StoragePath) -> None:
        """ブロブをコピー."""
        if not self._container_client:
            raise StorageException("Storageが初期化されていません")
        
        try:
            source_blob_name = self._resolve_blob_name(source)
            dest_blob_name = self._resolve_blob_name(destination)
            
            source_blob_client = self._container_client.get_blob_client(source_blob_name)
            dest_blob_client = self._container_client.get_blob_client(dest_blob_name)
            
            # ブロブURLを取得してコピー
            source_url = source_blob_client.url
            dest_blob_client.start_copy_from_url(source_url)
        except Exception as e:
            raise StorageException(f"コピーエラー: {e}", source)
    
    def move(self, source: StoragePath, destination: StoragePath) -> None:
        """ブロブを移動（コピー後削除）."""
        self.copy(source, destination)
        self.delete(source)
    
    def delete(self, path: StoragePath) -> None:
        """ブロブを削除."""
        if not self._container_client:
            raise StorageException("Storageが初期化されていません")
        
        try:
            blob_name = self._resolve_blob_name(path)
            blob_client = self._container_client.get_blob_client(blob_name)
            
            blob_client.delete_blob()
        except Exception as e:
            if "BlobNotFound" in str(e):
                # 削除対象が存在しない場合は正常終了
                return
            raise StorageException(f"削除エラー: {e}", path)
    
    def list_objects(self, path_prefix: StoragePath) -> Iterator[StorageMetadata]:
        """プレフィックス配下のブロブ一覧を取得."""
        if not self._container_client:
            raise StorageException("Storageが初期化されていません")
        
        try:
            prefix = self._resolve_blob_name(path_prefix)
            blobs = self._container_client.list_blobs(name_starts_with=prefix)
            
            for blob in blobs:
                # ブロブ名からStoragePathを再構築
                relative_path = blob.name
                if self._configuration and self._configuration.base_path:
                    # ベースパスを除去
                    base = self._configuration.base_path.rstrip("/") + "/"
                    if relative_path.startswith(base):
                        relative_path = relative_path[len(base):]
                
                # パスからStoragePathを推測（簡略化）
                storage_path = StoragePath(
                    domain=path_prefix.domain,
                    intent=path_prefix.intent,
                    relative_path=relative_path,
                    resolution=path_prefix.resolution,
                )
                
                yield StorageMetadata(
                    path=storage_path,
                    size=blob.size,
                    content_type=blob.content_settings.content_type if blob.content_settings else None,
                    etag=blob.etag,
                    last_modified=blob.last_modified.isoformat() if blob.last_modified else None,
                    custom_metadata=blob.metadata,
                )
        except Exception as e:
            raise StorageException(f"一覧取得エラー: {e}", path_prefix)
    
    def generate_presigned_url(
        self, 
        path: StoragePath, 
        expiration_seconds: int = 3600,
        method: str = "GET",
    ) -> str:
        """署名付きURLを生成."""
        if not self._container_client:
            raise StorageException("Storageが初期化されていません")
        
        try:
            from datetime import datetime, timedelta
            from azure.storage.blob import generate_blob_sas, BlobSasPermissions
            
            blob_name = self._resolve_blob_name(path)
            
            # SAS権限を設定
            if method.upper() == "GET":
                permission = BlobSasPermissions(read=True)
            elif method.upper() == "PUT":
                permission = BlobSasPermissions(write=True)
            else:
                permission = BlobSasPermissions(read=True, write=True)
            
            # SASトークンを生成
            sas_token = generate_blob_sas(
                account_name=self._blob_service_client.account_name,
                container_name=self._container_client.container_name,
                blob_name=blob_name,
                account_key=self._configuration.credentials.access_key,
                permission=permission,
                expiry=datetime.utcnow() + timedelta(seconds=expiration_seconds),
            )
            
            # 完全なURLを構築
            blob_client = self._container_client.get_blob_client(blob_name)
            return f"{blob_client.url}?{sas_token}"
        except Exception as e:
            raise StorageException(f"署名付きURL生成エラー: {e}", path)
    
    def _resolve_blob_name(self, path: StoragePath) -> str:
        """StoragePathからブロブ名を解決."""
        if not self._configuration:
            raise StorageException("Storageが初期化されていません")
        
        full_path = self._path_resolver.resolve_full_path(path, self._configuration)
        
        # URL エンコーディングを適用（Azure Blobの要件に合わせる）
        return quote(full_path, safe="/")


# オプショナル依存の型とクラスを初期化
BlobServiceClient = None
ResourceExistsError = None
ResourceNotFoundError = None
HttpResponseError = None

# Type hint用（azure-storage-blobがなくても型エラーを回避）
try:
    from typing import TYPE_CHECKING
    if TYPE_CHECKING:
        from azure.storage.blob import BlobServiceClient as _BlobServiceClient, ContainerClient
except ImportError:
    from typing import Any