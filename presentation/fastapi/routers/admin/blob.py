"""Blob Storage 設定管理 API（FastAPI）。

Flask-Smorest 版 ``presentation/web/api/admin/blob.py`` を移植。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from shared.application.authenticated_principal import AuthenticatedPrincipal
from shared.kernel.settings.settings import settings
from presentation.fastapi.dependencies.auth import get_current_principal

router = APIRouter(prefix="/admin/blob", tags=["admin:blob"])


def _require_admin(principal: AuthenticatedPrincipal) -> None:
    if not principal.can("admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "forbidden", "message": "admin permission required"},
        )


class BlobStatusResponse(BaseModel):
    enabled: bool
    provider: str
    container_name: str
    endpoint_suffix: str
    secure_transfer: bool
    auto_create_container: bool
    public_access_level: str
    connection_configured: bool
    account_configured: bool
    sas_token_configured: bool


class BlobConfigValidationResponse(BaseModel):
    provider: str
    valid: bool
    missing_fields: list[str]
    warnings: list[str]
    recommendations: list[str]


@router.get("/status", response_model=BlobStatusResponse)
async def get_blob_status(
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
) -> BlobStatusResponse:
    """Blob Storage 機能の現在の状態を取得。"""
    _require_admin(principal)

    connection_configured = bool(getattr(settings, "blob_connection_string", None))
    account_configured = all([
        getattr(settings, "blob_account_name", None),
        getattr(settings, "blob_access_key", None),
    ])
    sas_token_configured = bool(getattr(settings, "blob_sas_token", None))

    return BlobStatusResponse(
        enabled=bool(getattr(settings, "blob_enabled", False)),
        provider=str(getattr(settings, "blob_provider", "local")),
        container_name=str(getattr(settings, "blob_container_name", "") or ""),
        endpoint_suffix=str(getattr(settings, "blob_endpoint_suffix", "core.windows.net") or "core.windows.net"),
        secure_transfer=bool(getattr(settings, "blob_secure_transfer", True)),
        auto_create_container=bool(getattr(settings, "blob_create_container_if_not_exists", False)),
        public_access_level=str(getattr(settings, "blob_public_access_level", "private") or "private"),
        connection_configured=connection_configured,
        account_configured=account_configured,
        sas_token_configured=sas_token_configured,
    )


@router.get("/validate-config", response_model=BlobConfigValidationResponse)
async def validate_blob_config(
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
) -> BlobConfigValidationResponse:
    """現在の Blob Storage 設定を検証。"""
    _require_admin(principal)

    provider = str(getattr(settings, "blob_provider", "local") or "local")
    valid = False
    missing_fields: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []

    if provider == "none" or not getattr(settings, "blob_enabled", False):
        return BlobConfigValidationResponse(
            provider=provider,
            valid=True,
            missing_fields=[],
            warnings=["Blob Storageが無効になっています"],
            recommendations=["ローカルストレージのみを使用します"],
        )

    if provider == "local":
        return BlobConfigValidationResponse(
            provider=provider,
            valid=True,
            missing_fields=[],
            warnings=[],
            recommendations=[
                "ローカルファイルシステムを使用します",
                "スケーラビリティを向上するにはAzure Blob Storageを検討してください",
            ],
        )

    if provider == "azure":
        has_connection_string = bool(getattr(settings, "blob_connection_string", None))
        has_account_credentials = all([
            getattr(settings, "blob_account_name", None),
            getattr(settings, "blob_access_key", None),
        ])
        has_sas_token = bool(getattr(settings, "blob_sas_token", None))

        if not (has_connection_string or has_account_credentials or has_sas_token):
            missing_fields.extend([
                "接続文字列",
                "または アカウント名＋アクセスキー",
                "または SASトークン",
            ])
        else:
            valid = True
            if has_connection_string:
                recommendations.append("接続文字列を使用（推奨方法）")
            elif has_account_credentials:
                recommendations.append("アカウント名＋アクセスキーを使用")
                warnings.append("接続文字列の使用を推奨します")
            elif has_sas_token:
                recommendations.append("SASトークンを使用")
                warnings.append("SASトークンの有効期限を定期的に確認してください")

        container_name = str(getattr(settings, "blob_container_name", "") or "")
        if not container_name:
            missing_fields.append("コンテナ名")
            valid = False
        else:
            cn_lower = container_name.lower()
            if not (3 <= len(cn_lower) <= 63):
                warnings.append("コンテナ名は3-63文字である必要があります")
            elif not cn_lower.replace("-", "").replace("_", "").isalnum():
                warnings.append("コンテナ名に無効な文字が含まれている可能性があります")

        if not getattr(settings, "blob_secure_transfer", True):
            warnings.append("セキュア転送が無効です（セキュリティリスク）")
        else:
            recommendations.append("セキュア転送が有効（推奨）")

        public_access_level = str(getattr(settings, "blob_public_access_level", "private") or "private")
        if public_access_level == "container":
            warnings.append("コンテナが完全にパブリックアクセス可能です（セキュリティリスク）")
        elif public_access_level == "blob":
            recommendations.append("Blobレベルのパブリックアクセスが設定されています")
        else:
            recommendations.append("プライベートアクセス（最もセキュア）")

        endpoint_suffix = str(getattr(settings, "blob_endpoint_suffix", "core.windows.net") or "core.windows.net")
        if endpoint_suffix != "core.windows.net":
            known = {"core.chinacloudapi.cn", "core.cloudapi.de", "core.usgovcloudapi.net"}
            if endpoint_suffix in known:
                recommendations.append(f"特別なAzureクラウド環境: {endpoint_suffix}")
            else:
                warnings.append(f"非標準のエンドポイントサフィックス: {endpoint_suffix}")

    else:
        warnings.append(f"未対応のBlobプロバイダー: {provider}")

    if getattr(settings, "blob_create_container_if_not_exists", False):
        recommendations.append("コンテナ自動作成が有効（便利）")
    else:
        warnings.append("コンテナ自動作成が無効（手動でコンテナを作成してください）")

    return BlobConfigValidationResponse(
        provider=provider,
        valid=valid,
        missing_fields=missing_fields,
        warnings=warnings,
        recommendations=recommendations,
    )
