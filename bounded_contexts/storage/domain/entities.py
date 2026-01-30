"""Storage境界文脈のドメイン層 - 値オブジェクトとエンティティ."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from .types import StorageBackendType, StorageDomain, StorageIntent, StorageResolution

__all__ = [
    "StoragePath",
    "StorageCredentials", 
    "StorageConfiguration",
    "StorageMetadata",
    "StorageException",
    "StorageNotFoundException",
    "StoragePermissionException",
    "CDNConfiguration",
    "CDNPurgeRequest",
    "CDNAnalytics",
]


@dataclass(frozen=True, slots=True)
class StoragePath:
    """ストレージパスを表す値オブジェクト."""
    
    domain: StorageDomain
    intent: StorageIntent
    relative_path: str
    resolution: StorageResolution | None = None
    
    def __post_init__(self) -> None:
        """パスの妥当性を検証."""
        if not self.relative_path:
            raise ValueError("relative_pathは空文字列にできません")
        
        # 相対パスであることを確認
        path = Path(self.relative_path)
        if path.is_absolute():
            raise ValueError("absolute pathは使用できません")
    
    @property
    def path_parts(self) -> tuple[str, ...]:
        """パス要素のタプルを返す."""
        return tuple(Path(self.relative_path).parts)
    
    def with_resolution(self, resolution: StorageResolution) -> StoragePath:
        """解像度を指定した新しいインスタンスを作成."""
        return StoragePath(
            domain=self.domain,
            intent=self.intent,
            relative_path=self.relative_path,
            resolution=resolution,
        )


@dataclass(frozen=True, slots=True)
class StorageCredentials:
    """ストレージ認証情報を表す値オブジェクト."""
    
    backend_type: StorageBackendType
    connection_string: str | None = None
    access_key: str | None = None
    secret_key: str | None = None
    account_name: str | None = None
    container_name: str | None = None
    endpoint_url: str | None = None
    
    # CDN specific credentials
    api_token: str | None = None
    zone_id: str | None = None
    cdn_profile: str | None = None
    cdn_endpoint: str | None = None
    origin_hostname: str | None = None
    
    def __post_init__(self) -> None:
        """認証情報の妥当性を検証."""
        if self.backend_type == StorageBackendType.AZURE_BLOB:
            if not self.connection_string and not (self.account_name and self.access_key):
                raise ValueError("Azure Blob requires connection_string or account_name+access_key")
        elif self.backend_type == StorageBackendType.S3:
            if not (self.access_key and self.secret_key):
                raise ValueError("S3 requires access_key and secret_key")
        elif self.backend_type == StorageBackendType.AZURE_CDN:
            if not (self.account_name and self.access_key and self.cdn_profile and self.cdn_endpoint):
                raise ValueError("Azure CDN requires account_name, access_key, cdn_profile, and cdn_endpoint")
        elif self.backend_type == StorageBackendType.CLOUDFLARE_CDN:
            if not (self.api_token and self.zone_id and self.origin_hostname):
                raise ValueError("CloudFlare CDN requires api_token, zone_id, and origin_hostname")
        elif self.backend_type == StorageBackendType.GENERIC_CDN:
            if not (self.endpoint_url and self.origin_hostname):
                raise ValueError("Generic CDN requires endpoint_url and origin_hostname")


@dataclass(frozen=True, slots=True)
class StorageConfiguration:
    """ストレージ設定を表す値オブジェクト."""
    
    backend_type: StorageBackendType
    credentials: StorageCredentials
    base_path: str = ""
    region: str | None = None
    timeout: int = 30
    retry_count: int = 3
    
    # CDN specific configurations
    cache_ttl: int = 3600  # CDN cache TTL in seconds
    enable_compression: bool = True
    origin_backend_type: StorageBackendType | None = None  # For CDN+Storage combinations
    origin_credentials: StorageCredentials | None = None
    custom_headers: dict[str, str] | None = None
    
    def __post_init__(self) -> None:
        """設定の妥当性を検証."""
        if self.timeout <= 0:
            raise ValueError("timeoutは正数である必要があります")
        if self.retry_count < 0:
            raise ValueError("retry_countは非負数である必要があります")
        if self.credentials.backend_type != self.backend_type:
            raise ValueError("credentials.backend_typeとbackend_typeが一致しません")
        if self.cache_ttl < 0:
            raise ValueError("cache_ttlは非負数である必要があります")
        
        # CDN + オリジンストレージ組み合わせの場合
        cdn_backends = {StorageBackendType.AZURE_CDN, StorageBackendType.CLOUDFLARE_CDN, StorageBackendType.AMAZON_CLOUDFRONT, StorageBackendType.GENERIC_CDN}
        if self.backend_type in cdn_backends:
            if not self.origin_backend_type or not self.origin_credentials:
                raise ValueError("CDN backends require origin_backend_type and origin_credentials")


@dataclass(frozen=True, slots=True)
class StorageMetadata:
    """ストレージオブジェクトのメタデータを表す値オブジェクト."""
    
    path: StoragePath
    size: int
    content_type: str | None = None
    etag: str | None = None
    last_modified: str | None = None
    custom_metadata: dict[str, str] | None = None
    
    # CDN specific metadata
    cdn_url: str | None = None
    cache_status: str | None = None  # HIT, MISS, BYPASS etc.
    edge_location: str | None = None
    
    def __post_init__(self) -> None:
        """メタデータの妥当性を検証."""
        if self.size < 0:
            raise ValueError("sizeは非負数である必要があります")


# ドメイン例外クラス
class StorageException(Exception):
    """ストレージドメインの基底例外."""
    
    def __init__(self, message: str, path: StoragePath | None = None) -> None:
        super().__init__(message)
        self.path = path


class StorageNotFoundException(StorageException):
    """ストレージオブジェクトが見つからない例外."""
    pass


class StoragePermissionException(StorageException):
    """ストレージアクセス権限エラー例外."""
    pass


@dataclass(frozen=True, slots=True)
class CDNConfiguration:
    """CDN設定を表す値オブジェクト."""
    
    cache_ttl: int = 3600
    enable_gzip: bool = True
    enable_brotli: bool = True
    cache_query_strings: bool = False
    allowed_origins: list[str] | None = None
    blocked_countries: list[str] | None = None
    custom_rules: dict[str, Any] | None = None
    
    def __post_init__(self) -> None:
        """CDN設定の妥当性を検証."""
        if self.cache_ttl < 0:
            raise ValueError("cache_ttlは非負数である必要があります")


@dataclass(frozen=True, slots=True)
class CDNPurgeRequest:
    """CDNキャッシュパージリクエストを表す値オブジェクト."""
    
    paths: list[str]
    purge_type: str = "url"  # url, prefix, tag
    priority: int = 1  # 1=high, 2=medium, 3=low
    
    def __post_init__(self) -> None:
        """パージリクエストの妥当性を検証."""
        if not self.paths:
            raise ValueError("pathsは空にできません")
        if self.purge_type not in ["url", "prefix", "tag"]:
            raise ValueError("purge_typeは'url', 'prefix', 'tag'のいずれかである必要があります")
        if not 1 <= self.priority <= 3:
            raise ValueError("priorityは1-3の範囲である必要があります")


@dataclass(frozen=True, slots=True)
class CDNAnalytics:
    """CDNアナリティクスデータを表す値オブジェクト."""
    
    path: StoragePath
    requests_count: int
    cache_hit_ratio: float
    bandwidth_bytes: int
    response_time_ms: float
    status_codes: dict[int, int]
    edge_locations: dict[str, int]
    period_start: str
    period_end: str
    
    def __post_init__(self) -> None:
        """アナリティクスデータの妥当性を検証."""
        if self.requests_count < 0:
            raise ValueError("requests_countは非負数である必要があります")
        if not 0 <= self.cache_hit_ratio <= 1:
            raise ValueError("cache_hit_ratioは0-1の範囲である必要があります")
        if self.bandwidth_bytes < 0:
            raise ValueError("bandwidth_bytesは非負数である必要があります")
        if self.response_time_ms < 0:
            raise ValueError("response_time_msは非負数である必要があります")


# ドメインサービス用プロトコル
@runtime_checkable
class StoragePathResolver(Protocol):
    """ストレージパス解決ドメインサービス."""
    
    def resolve_full_path(
        self,
        storage_path: StoragePath,
        configuration: StorageConfiguration,
    ) -> str:
        """完全なストレージパスを解決する."""
        ...
    
    def build_hierarchical_path(
        self,
        storage_path: StoragePath,
    ) -> str:
        """階層的なパス構造を構築する."""
        ...