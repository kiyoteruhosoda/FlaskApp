"""Storage境界文脈のドメインサービスとリポジトリプロトコル."""

from __future__ import annotations

from typing import IO, Any, Iterator, Protocol, runtime_checkable

from .entities import (
    CDNAnalytics,
    CDNConfiguration,
    CDNPurgeRequest,
    StorageConfiguration,
    StorageException,
    StorageMetadata,
    StoragePath,
)

__all__ = [
    "StorageBackend",
    "CDNBackend",
    "StorageRepository",
    "StoragePathResolverService",
]


@runtime_checkable
class StorageBackend(Protocol):
    """ストレージバックエンドの抽象プロトコル.
    
    ポリモーフィズムにより、異なるストレージ実装（Local、S3、AzureBlob等）を
    統一的なインターフェースで扱う。
    """
    
    def initialize(self, configuration: StorageConfiguration) -> None:
        """バックエンドを初期化する."""
        ...
    
    def exists(self, path: StoragePath) -> bool:
        """指定パスにオブジェクトが存在するかチェック."""
        ...
    
    def get_metadata(self, path: StoragePath) -> StorageMetadata:
        """オブジェクトのメタデータを取得."""
        ...
    
    def read(self, path: StoragePath) -> bytes:
        """オブジェクトの内容を読み込み."""
        ...
    
    def read_stream(self, path: StoragePath) -> IO[bytes]:
        """オブジェクトをストリーミング読み込み."""
        ...
    
    def write(self, path: StoragePath, content: bytes) -> None:
        """オブジェクトを書き込み."""
        ...
    
    def write_stream(self, path: StoragePath, stream: IO[bytes]) -> None:
        """ストリーミングでオブジェクトを書き込み."""
        ...
    
    def copy(self, source: StoragePath, destination: StoragePath) -> None:
        """オブジェクトをコピー."""
        ...
    
    def move(self, source: StoragePath, destination: StoragePath) -> None:
        """オブジェクトを移動."""
        ...
    
    def delete(self, path: StoragePath) -> None:
        """オブジェクトを削除."""
        ...
    
    def list_objects(self, path_prefix: StoragePath) -> Iterator[StorageMetadata]:
        """指定プレフィックス配下のオブジェクト一覧を取得."""
        ...
    
    def generate_presigned_url(
        self, 
        path: StoragePath, 
        expiration_seconds: int = 3600,
        method: str = "GET",
    ) -> str:
        """署名付きURLを生成（可能な場合）."""
        ...


@runtime_checkable
class CDNBackend(Protocol):
    """CDNバックエンドの抽象プロトコル.
    
    ポリモーフィズムにより、異なるCDN実装（Azure CDN、CloudFlare等）を
    統一的なインターフェースで扱う。
    """
    
    def initialize(self, configuration: StorageConfiguration) -> None:
        """CDNバックエンドを初期化する."""
        ...
    
    def get_cdn_url(self, path: StoragePath) -> str:
        """CDN配信URLを取得."""
        ...
    
    def generate_secure_url(
        self, 
        path: StoragePath, 
        expiration_seconds: int = 3600,
        allowed_ip: str | None = None,
    ) -> str:
        """セキュアトークン付きCDN URLを生成."""
        ...
    
    def purge_cache(self, purge_request: CDNPurgeRequest) -> str:
        """CDNキャッシュをパージ（無効化）."""
        ...
    
    def get_cache_status(self, path: StoragePath) -> str:
        """キャッシュステータスを取得（HIT/MISS/BYPASS）."""
        ...
    
    def update_cdn_configuration(self, config: CDNConfiguration) -> None:
        """CDN設定を更新."""
        ...
    
    def get_analytics(
        self, 
        path_prefix: StoragePath,
        start_time: str,
        end_time: str,
    ) -> Iterator[CDNAnalytics]:
        """CDNアナリティクスデータを取得."""
        ...
    
    def prefetch_content(self, paths: list[StoragePath]) -> None:
        """コンテンツをCDNエッジに事前フェッチ."""
        ...
    
    # オリジンストレージとの統合操作
    def upload_to_origin_and_invalidate(
        self, 
        path: StoragePath, 
        content: bytes,
    ) -> StorageMetadata:
        """オリジンにアップロードしてCDNキャッシュを無効化."""
        ...
    
    def delete_from_origin_and_purge(self, path: StoragePath) -> None:
        """オリジンから削除してCDNキャッシュをパージ."""
        ...


@runtime_checkable
class StorageRepository(Protocol):
    """ストレージ設定の永続化リポジトリプロトコル."""
    
    def get_configuration(self, domain: str) -> StorageConfiguration | None:
        """ドメイン別設定を取得."""
        ...
    
    def save_configuration(self, domain: str, config: StorageConfiguration) -> None:
        """ドメイン別設定を保存."""
        ...
    
    def delete_configuration(self, domain: str) -> None:
        """ドメイン別設定を削除."""
        ...
    
    def list_domains(self) -> list[str]:
        """設定済みドメインの一覧を取得."""
        ...


class StoragePathResolverService:
    """ストレージパス解決ドメインサービス."""
    
    def resolve_full_path(
        self,
        storage_path: StoragePath,
        configuration: StorageConfiguration,
    ) -> str:
        """完全なストレージパスを解決する."""
        base = configuration.base_path.rstrip("/")
        parts = [base] if base else []
        
        # ドメイン + Intent + 解像度 でディレクトリ構造を作成
        if storage_path.domain:
            parts.append(storage_path.domain.value)
        
        if storage_path.intent:
            parts.append(storage_path.intent.value)
        
        if storage_path.resolution:
            parts.append(storage_path.resolution.value)
            
        parts.extend(storage_path.path_parts)
        
        return "/".join(parts)
    
    def build_hierarchical_path(
        self,
        storage_path: StoragePath,
    ) -> str:
        """階層的なパス構造を構築する."""
        parts = []
        
        # YYYY/MM/DD 形式でメディアファイルを階層化
        if storage_path.domain in [storage_path.domain.MEDIA, storage_path.domain.THUMBNAILS]:
            # 日付ベースの階層化ロジック（ファイル名から推定）
            relative = storage_path.relative_path
            if "/" in relative:
                # すでに階層化済み
                parts.append(relative)
            else:
                # 単純なファイル名の場合は現在日付で階層化
                from datetime import datetime
                now = datetime.utcnow()
                parts.extend([str(now.year), f"{now.month:02d}", f"{now.day:02d}", relative])
        else:
            parts.append(storage_path.relative_path)
        
        return "/".join(parts)