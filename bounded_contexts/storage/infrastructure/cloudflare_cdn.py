"""CloudFlare CDN実装."""

from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import datetime, timedelta
from typing import Any, Iterator
from urllib.parse import quote, urlencode

import requests

from ..domain import (
    CDNAnalytics,
    CDNBackend,
    CDNConfiguration,
    CDNPurgeRequest,
    StorageConfiguration,
    StorageException,
    StorageMetadata,
    StoragePath,
    StoragePathResolverService,
)
from .local import LocalStorage

__all__ = ["CloudFlareCDN"]

logger = logging.getLogger(__name__)

# CloudFlare API v4 のベース URL。
_CLOUDFLARE_API_BASE = "https://api.cloudflare.com/client/v4"
# API 呼び出しのタイムアウト（秒）。パージ等は同期で待つため短めに設定。
_CLOUDFLARE_API_TIMEOUT = 30


class CloudFlareCDN:
    """CloudFlare CDNのCDNバックエンド実装."""
    
    def __init__(self) -> None:
        self._configuration: StorageConfiguration | None = None
        self._origin_storage: LocalStorage | None = None
        self._path_resolver = StoragePathResolverService()
        self._zone_id: str | None = None
        self._api_token: str | None = None
        self._origin_hostname: str | None = None
    
    def initialize(self, configuration: StorageConfiguration) -> None:
        """CloudFlare CDNクライアントを初期化."""
        try:
            self._configuration = configuration
            
            # CloudFlare API認証情報を取得
            self._api_token = configuration.credentials.api_token
            self._zone_id = configuration.credentials.zone_id
            self._origin_hostname = configuration.credentials.origin_hostname
            
            if not all([self._api_token, self._zone_id, self._origin_hostname]):
                raise StorageException("CloudFlare CDN requires api_token, zone_id, and origin_hostname")
            
            # オリジンストレージを初期化（ローカルまたは他のストレージ）
            if configuration.origin_backend_type and configuration.origin_credentials:
                from ..domain import StorageBackendType
                if configuration.origin_backend_type == StorageBackendType.LOCAL:
                    origin_config = StorageConfiguration(
                        backend_type=configuration.origin_backend_type,
                        credentials=configuration.origin_credentials,
                        base_path=configuration.base_path,
                    )
                    self._origin_storage = LocalStorage()
                    self._origin_storage.initialize(origin_config)
            
            logger.info(f"CloudFlare CDN initialized: zone={self._zone_id}, origin={self._origin_hostname}")
            
        except Exception as e:
            raise StorageException(f"CloudFlare CDN初期化エラー: {e}")
    
    def get_cdn_url(self, path: StoragePath) -> str:
        """CDN配信URLを取得."""
        if not self._origin_hostname:
            raise StorageException("CDNが初期化されていません")
        
        if not self._configuration:
            raise StorageException("CDN設定が初期化されていません")
        
        # ストレージパスをCDN URLに変換
        relative_path = self._path_resolver.resolve_full_path(path, self._configuration)
        
        # URL エンコーディング
        encoded_path = quote(relative_path, safe="/")
        
        # CloudFlareを通したCDN URL
        return f"https://{self._origin_hostname}/{encoded_path}"
    
    def generate_secure_url(
        self, 
        path: StoragePath, 
        expiration_seconds: int = 3600,
        allowed_ip: str | None = None,
    ) -> str:
        """セキュアトークン付きCDN URLを生成."""
        if not self._configuration or not self._configuration.credentials.access_key:
            raise StorageException("セキュアURL生成にはアクセスキーが必要です")
        
        base_url = self.get_cdn_url(path)
        
        # 有効期限を計算
        expiry = datetime.utcnow() + timedelta(seconds=expiration_seconds)
        expiry_timestamp = int(expiry.timestamp())
        
        # CloudFlareのセキュアトークンを生成
        secret_key = self._configuration.credentials.access_key
        
        # トークン用データを構築
        # CloudFlare URL署名仕様に基づく
        url_path = f"/{self._path_resolver.resolve_full_path(path, self._configuration)}"
        token_data = f"{url_path}{expiry_timestamp}"
        if allowed_ip:
            token_data += f"{allowed_ip}"
        
        # HMACでトークンを生成
        token = hmac.new(
            secret_key.encode('utf-8'),
            token_data.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()[:32]  # CloudFlareは32文字
        
        # セキュアURLパラメータを追加
        params = {
            'token': token,
            'expires': str(expiry_timestamp),
        }
        if allowed_ip:
            params['ip'] = allowed_ip
        
        query_string = urlencode(params)
        return f"{base_url}?{query_string}"
    
    def _api_request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """CloudFlare API v4 へ認証付きリクエストを送り、result を返す。

        認証は API トークン（Bearer）。CloudFlare は ``{"success": bool,
        "errors": [...], "result": ...}`` 形式で応答する。``success`` が false の
        場合や HTTP エラーは :class:`StorageException` に変換する。
        """

        if not self._api_token:
            raise StorageException("CDNが初期化されていません")

        url = f"{_CLOUDFLARE_API_BASE}{path}"
        headers = {
            "Authorization": f"Bearer {self._api_token}",
            "Content-Type": "application/json",
        }
        try:
            resp = requests.request(
                method,
                url,
                headers=headers,
                json=json_body,
                timeout=_CLOUDFLARE_API_TIMEOUT,
            )
        except requests.RequestException as exc:
            raise StorageException(f"CloudFlare API リクエスト失敗: {exc}") from exc

        try:
            data = resp.json()
        except ValueError:
            data = {}

        if not resp.ok or not data.get("success", False):
            errors = data.get("errors") if isinstance(data, dict) else None
            raise StorageException(
                f"CloudFlare API エラー ({resp.status_code}): {errors or resp.text[:200]}"
            )

        return data

    def _absolute_purge_url(self, path: str) -> str:
        """パージ対象のパスを完全 URL に正規化する。"""

        if path.startswith("http"):
            return path
        return f"https://{self._origin_hostname}/{path.lstrip('/')}"

    def purge_cache(self, purge_request: CDNPurgeRequest) -> str:
        """CDNキャッシュをパージ（無効化）。CloudFlare API v4 を実際に呼び出す。"""
        if not self._zone_id or not self._api_token:
            raise StorageException("CDNが初期化されていません")

        logger.info(
            f"CloudFlare CDNキャッシュパージ開始: {len(purge_request.paths)} paths "
            f"(type={purge_request.purge_type})"
        )

        # パージリクエストを構築（CloudFlare Purge API の仕様に対応）。
        if purge_request.purge_type == "url":
            payload: dict[str, Any] = {
                "files": [self._absolute_purge_url(p) for p in purge_request.paths]
            }
        elif purge_request.purge_type == "prefix":
            payload = {"prefixes": list(purge_request.paths)}
        elif purge_request.purge_type == "tag":
            payload = {"tags": list(purge_request.paths)}
        elif purge_request.purge_type == "all":
            payload = {"purge_everything": True}
        else:
            raise StorageException(f"未対応のパージタイプ: {purge_request.purge_type}")

        # POST https://api.cloudflare.com/client/v4/zones/{zone_id}/purge_cache
        data = self._api_request(
            "POST",
            f"/zones/{self._zone_id}/purge_cache",
            json_body=payload,
        )

        result = data.get("result") or {}
        # CloudFlare はパージのジョブ ID を result.id で返す。取得できない場合は
        # zone_id ベースの識別子で代替する（成功は success で担保済み）。
        purge_job_id = str(result.get("id") or f"{self._zone_id}:purged")
        logger.info(f"CloudFlare CDNパージ完了: job_id={purge_job_id}")
        return purge_job_id
    
    def get_cache_status(self, path: StoragePath) -> str:
        """キャッシュステータスを取得（HIT/MISS/BYPASS 等）。

        CloudFlare はレスポンスヘッダー ``CF-Cache-Status`` にエッジのキャッシュ
        判定を返す。対象 URL へ HEAD リクエストを送りそのヘッダーを読む。
        """
        try:
            cdn_url = self.get_cdn_url(path)
            resp = requests.head(
                cdn_url, timeout=_CLOUDFLARE_API_TIMEOUT, allow_redirects=True
            )
            status = resp.headers.get("CF-Cache-Status")
            return status or "UNKNOWN"
        except Exception as e:
            logger.warning(f"CDNキャッシュステータス取得エラー: {e}")
            return "UNKNOWN"
    
    def update_cdn_configuration(self, config: CDNConfiguration) -> None:
        """CloudFlare Zone Settings API で設定を更新する。

        設定はキーごとに ``PATCH /zones/{zone}/settings/{key}`` で更新する。
        ``browser_cache_ttl`` とブラウザキャッシュ、``brotli`` 圧縮を反映する。
        （``edge_cache_ttl`` は Page Rules / Cache Rules 側のため個別設定には含めない。）
        """
        if not self._zone_id or not self._api_token:
            raise StorageException("CDNが初期化されていません")

        logger.info(f"CloudFlare CDN設定更新: cache_ttl={config.cache_ttl}")

        settings_to_apply: list[tuple[str, Any]] = [
            ("browser_cache_ttl", int(config.cache_ttl)),
        ]
        if config.enable_brotli:
            settings_to_apply.append(("brotli", "on"))

        for setting_key, value in settings_to_apply:
            # PATCH https://api.cloudflare.com/client/v4/zones/{zone_id}/settings/{key}
            self._api_request(
                "PATCH",
                f"/zones/{self._zone_id}/settings/{setting_key}",
                json_body={"value": value},
            )
    
    def get_analytics(
        self, 
        path_prefix: StoragePath,
        start_time: str,
        end_time: str,
    ) -> Iterator[CDNAnalytics]:
        """""CDNアナリティクスデータを取得."""""
        if not self._zone_id or not self._api_token:
            raise StorageException("CDNが初期化されていません")

        logger.info(
            f"CloudFlare CDNアナリティクス取得: {path_prefix.relative_path} "
            f"({start_time} - {end_time})"
        )

        # CloudFlare GraphQL Analytics API から集計を取得する。
        query = (
            "query($zoneTag: String!, $start: Time!, $end: Time!) {"
            "  viewer { zones(filter: {zoneTag: $zoneTag}) {"
            "    httpRequestsAdaptiveGroups(limit: 1, filter: {datetime_geq: $start, datetime_leq: $end}) {"
            "      count sum { edgeResponseBytes } "
            "    } } } }"
        )
        data = self._api_request(
            "POST",
            "/graphql",
            json_body={
                "query": query,
                "variables": {
                    "zoneTag": self._zone_id,
                    "start": start_time,
                    "end": end_time,
                },
            },
        )

        try:
            zones = data["result"]["data"]["viewer"]["zones"]
            groups = zones[0]["httpRequestsAdaptiveGroups"] if zones else []
        except (KeyError, IndexError, TypeError):
            groups = []

        for group in groups:
            count = int(group.get("count", 0) or 0)
            bytes_sum = int((group.get("sum") or {}).get("edgeResponseBytes", 0) or 0)
            yield CDNAnalytics(
                path=path_prefix,
                requests_count=count,
                cache_hit_ratio=0.0,
                bandwidth_bytes=bytes_sum,
                response_time_ms=0.0,
                status_codes={},
                edge_locations={},
                period_start=start_time,
                period_end=end_time,
            )
    
    def prefetch_content(self, paths: list[StoragePath]) -> None:
        """""コンテンツをCDNエッジに事前フェッチ."""""
        if not self._zone_id or not self._api_token:
            raise StorageException("CDNが初期化されていません")

        # CloudFlare には専用の Prefetch API がないため、対象 URL へ実際に GET して
        # エッジキャッシュを温める。個々の失敗はスキップしログに残す。
        logger.info(f"CloudFlare CDNプリフェッチ開始: {len(paths)} files")

        for path in paths:
            cdn_url = self.get_cdn_url(path)
            try:
                resp = requests.get(cdn_url, timeout=_CLOUDFLARE_API_TIMEOUT, stream=True)
                # 本文は読み込まず接続を閉じる（エッジに載せるのが目的）。
                resp.close()
                logger.info(
                    f"CDNプリフェッチ: {cdn_url} "
                    f"(status={resp.status_code}, cache={resp.headers.get('CF-Cache-Status')})"
                )
            except requests.RequestException as exc:
                logger.warning(f"CDNプリフェッチ失敗: {cdn_url} - {exc}")
    
    def upload_to_origin_and_invalidate(
        self, 
        path: StoragePath, 
        content: bytes,
    ) -> StorageMetadata:
        """""オリジンにアップロードしてCDNキャッシュを無効化."""""
        if not self._origin_storage:
            raise StorageException("オリジンストレージが設定されていません")
        
        try:
            # 1. オリジンストレージにアップロード
            self._origin_storage.write(path, content)
            metadata = self._origin_storage.get_metadata(path)
            
            # 2. CDNキャッシュを無効化
            cdn_url = self.get_cdn_url(path)
            purge_request = CDNPurgeRequest(
                paths=[cdn_url],
                purge_type="url",
                priority=1,
            )
            self.purge_cache(purge_request)
            
            # 3. CDN URLをメタデータに追加
            return StorageMetadata(
                path=metadata.path,
                size=metadata.size,
                content_type=metadata.content_type,
                etag=metadata.etag,
                last_modified=metadata.last_modified,
                custom_metadata=metadata.custom_metadata,
                cdn_url=cdn_url,
                cache_status="PURGED",
            )
            
        except Exception as e:
            raise StorageException(f"オリジンアップロード+CDN無効化エラー: {e}")
    
    def delete_from_origin_and_purge(self, path: StoragePath) -> None:
        """""オリジンから削除してCDNキャッシュをパージ."""""
        if not self._origin_storage:
            raise StorageException("オリジンストレージが設定されていません")
        
        try:
            # 1. オリジンストレージから削除
            self._origin_storage.delete(path)
            
            # 2. CDNキャッシュをパージ
            cdn_url = self.get_cdn_url(path)
            purge_request = CDNPurgeRequest(
                paths=[cdn_url],
                purge_type="url",
                priority=1,
            )
            self.purge_cache(purge_request)
            
            logger.info(f"オリジン削除+CDNパージ完了: {path.relative_path}")
            
        except Exception as e:
            raise StorageException(f"オリジン削除+CDNパージエラー: {e}")