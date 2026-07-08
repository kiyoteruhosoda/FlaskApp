"""CDN設定管理 API（FastAPI）。

Flask-Smorest 版 ``presentation/web/api/admin/cdn.py`` を移植。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from shared.application.authenticated_principal import AuthenticatedPrincipal
from shared.kernel.settings.settings import settings
from presentation.fastapi.dependencies.auth import get_current_principal

router = APIRouter(prefix="/admin/cdn", tags=["admin:cdn"])


def _require_admin(principal: AuthenticatedPrincipal) -> None:
    if not principal.can("admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "forbidden", "message": "admin permission required"},
        )


class CDNStatusResponse(BaseModel):
    enabled: bool
    provider: str
    cache_ttl: int
    compression_enabled: bool
    secure_urls_enabled: bool
    azure_configured: bool
    cloudflare_configured: bool
    generic_configured: bool


class CDNConfigValidationResponse(BaseModel):
    provider: str
    valid: bool
    missing_fields: list[str]
    warnings: list[str]


@router.get("/status", response_model=CDNStatusResponse)
async def get_cdn_status(
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
) -> CDNStatusResponse:
    """CDN機能の現在の状態を取得。"""
    _require_admin(principal)

    azure_configured = all([
        settings.cdn_azure_account_name,
        settings.cdn_azure_access_key,
        settings.cdn_azure_profile,
        settings.cdn_azure_endpoint,
    ])

    cloudflare_configured = all([
        settings.cdn_cloudflare_api_token,
        settings.cdn_cloudflare_zone_id,
        settings.cdn_cloudflare_origin_hostname,
    ])

    generic_configured = all([
        settings.cdn_generic_endpoint,
        settings.cdn_generic_api_token,
    ])

    return CDNStatusResponse(
        enabled=bool(settings.cdn_enabled),
        provider=str(settings.cdn_provider or "none"),
        cache_ttl=int(settings.cdn_cache_ttl or 3600),
        compression_enabled=bool(settings.cdn_enable_compression),
        secure_urls_enabled=bool(settings.cdn_secure_urls_enabled),
        azure_configured=azure_configured,
        cloudflare_configured=cloudflare_configured,
        generic_configured=generic_configured,
    )


@router.get("/validate-config", response_model=CDNConfigValidationResponse)
async def validate_cdn_config(
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
) -> CDNConfigValidationResponse:
    """現在のCDN設定を検証。"""
    _require_admin(principal)

    provider = str(settings.cdn_provider or "none")
    valid = False
    missing_fields: list[str] = []
    warnings: list[str] = []

    if provider == "none" or not settings.cdn_enabled:
        return CDNConfigValidationResponse(
            provider=provider,
            valid=True,
            missing_fields=[],
            warnings=["CDNが無効になっています"],
        )

    if provider == "azure":
        required_fields = [
            ("cdn_azure_account_name", "Azure CDNアカウント名"),
            ("cdn_azure_access_key", "Azure CDNアクセスキー"),
            ("cdn_azure_profile", "Azure CDNプロファイル"),
            ("cdn_azure_endpoint", "Azure CDNエンドポイント"),
        ]
        for field_name, field_label in required_fields:
            if not getattr(settings, field_name, None):
                missing_fields.append(field_label)
        if not missing_fields:
            valid = True
        if settings.cdn_secure_urls_enabled and not getattr(settings, "cdn_access_key", None):
            warnings.append("セキュアURL機能が有効ですが、アクセスキーが設定されていません")

    elif provider == "cloudflare":
        required_fields = [
            ("cdn_cloudflare_api_token", "CloudFlare APIトークン"),
            ("cdn_cloudflare_zone_id", "CloudFlare ゾーンID"),
            ("cdn_cloudflare_origin_hostname", "CloudFlare オリジンホスト名"),
        ]
        for field_name, field_label in required_fields:
            if not getattr(settings, field_name, None):
                missing_fields.append(field_label)
        if not missing_fields:
            valid = True
        if settings.cdn_secure_urls_enabled and not getattr(settings, "cdn_access_key", None):
            warnings.append("セキュアURL機能が有効ですが、アクセスキーが設定されていません")

    elif provider == "generic":
        required_fields = [
            ("cdn_generic_endpoint", "Generic CDN エンドポイント"),
            ("cdn_generic_api_token", "Generic CDN APIトークン"),
        ]
        for field_name, field_label in required_fields:
            if not getattr(settings, field_name, None):
                missing_fields.append(field_label)
        if not missing_fields:
            valid = True

    else:
        warnings.append(f"未対応のCDNプロバイダー: {provider}")

    cache_ttl = int(getattr(settings, "cdn_cache_ttl", 3600) or 3600)
    if cache_ttl < 60:
        warnings.append("キャッシュTTLが60秒未満です（推奨: 3600秒以上）")
    elif cache_ttl > 86400 * 7:
        warnings.append("キャッシュTTLが7日を超えています（推奨: 1日以内）")

    return CDNConfigValidationResponse(
        provider=provider,
        valid=valid,
        missing_fields=missing_fields,
        warnings=warnings,
    )
