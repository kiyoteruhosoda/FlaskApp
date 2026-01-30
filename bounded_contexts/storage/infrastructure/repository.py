"""Storage設定の永続化リポジトリ実装."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..domain import (
    StorageBackendType,
    StorageConfiguration,
    StorageCredentials,
    StorageRepository,
)

__all__ = ["JsonFileStorageRepository", "InMemoryStorageRepository"]


class JsonFileStorageRepository:
    """JSONファイルベースのStorage設定リポジトリ."""
    
    def __init__(self, config_file_path: str | Path) -> None:
        self._config_path = Path(config_file_path)
        self._ensure_config_file()
    
    def get_configuration(self, domain: str) -> StorageConfiguration | None:
        """ドメイン別設定を取得."""
        configs = self._load_configs()
        config_data = configs.get(domain)
        
        if not config_data:
            return None
        
        return self._deserialize_configuration(config_data)
    
    def save_configuration(self, domain: str, config: StorageConfiguration) -> None:
        """ドメイン別設定を保存."""
        configs = self._load_configs()
        configs[domain] = self._serialize_configuration(config)
        self._save_configs(configs)
    
    def delete_configuration(self, domain: str) -> None:
        """ドメイン別設定を削除."""
        configs = self._load_configs()
        if domain in configs:
            del configs[domain]
            self._save_configs(configs)
    
    def list_domains(self) -> list[str]:
        """設定済みドメインの一覧を取得."""
        configs = self._load_configs()
        return list(configs.keys())
    
    def _ensure_config_file(self) -> None:
        """設定ファイルが存在しない場合は作成."""
        if not self._config_path.exists():
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            self._config_path.write_text("{}")
    
    def _load_configs(self) -> dict[str, Any]:
        """設定ファイルを読み込み."""
        try:
            return json.loads(self._config_path.read_text())
        except (json.JSONDecodeError, FileNotFoundError):
            return {}
    
    def _save_configs(self, configs: dict[str, Any]) -> None:
        """設定ファイルに保存."""
        self._config_path.write_text(
            json.dumps(configs, indent=2, ensure_ascii=False)
        )
    
    def _serialize_configuration(self, config: StorageConfiguration) -> dict[str, Any]:
        """StorageConfigurationをJSONにシリアライズ."""
        return {
            "backend_type": config.backend_type.value,
            "credentials": {
                "backend_type": config.credentials.backend_type.value,
                "connection_string": config.credentials.connection_string,
                "access_key": config.credentials.access_key,
                "secret_key": config.credentials.secret_key,
                "account_name": config.credentials.account_name,
                "container_name": config.credentials.container_name,
                "endpoint_url": config.credentials.endpoint_url,
            },
            "base_path": config.base_path,
            "region": config.region,
            "timeout": config.timeout,
            "retry_count": config.retry_count,
        }
    
    def _deserialize_configuration(self, data: dict[str, Any]) -> StorageConfiguration:
        """JSONからStorageConfigurationをデシリアライズ."""
        credentials = StorageCredentials(
            backend_type=StorageBackendType(data["credentials"]["backend_type"]),
            connection_string=data["credentials"].get("connection_string"),
            access_key=data["credentials"].get("access_key"),
            secret_key=data["credentials"].get("secret_key"),
            account_name=data["credentials"].get("account_name"),
            container_name=data["credentials"].get("container_name"),
            endpoint_url=data["credentials"].get("endpoint_url"),
        )
        
        return StorageConfiguration(
            backend_type=StorageBackendType(data["backend_type"]),
            credentials=credentials,
            base_path=data.get("base_path", ""),
            region=data.get("region"),
            timeout=data.get("timeout", 30),
            retry_count=data.get("retry_count", 3),
        )


class InMemoryStorageRepository:
    """インメモリStorage設定リポジトリ（テスト用）."""
    
    def __init__(self) -> None:
        self._configurations: dict[str, StorageConfiguration] = {}
    
    def get_configuration(self, domain: str) -> StorageConfiguration | None:
        """ドメイン別設定を取得."""
        return self._configurations.get(domain)
    
    def save_configuration(self, domain: str, config: StorageConfiguration) -> None:
        """ドメイン別設定を保存."""
        self._configurations[domain] = config
    
    def delete_configuration(self, domain: str) -> None:
        """ドメイン別設定を削除."""
        if domain in self._configurations:
            del self._configurations[domain]
    
    def list_domains(self) -> list[str]:
        """設定済みドメインの一覧を取得."""
        return list(self._configurations.keys())