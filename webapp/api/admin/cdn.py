"""CDN設定管理API."""

from __future__ import annotations

from flask import Blueprint
from flask_smorest import Page
from marshmallow import Schema, fields

from core.settings import settings
from core.models.authz import require_perms

__all__ = ["bp"]

bp = Blueprint("cdn", __name__, url_prefix="/api/admin/cdn")


class CDNStatusSchema(Schema):
    """CDN状態レスポンス."""
    
    enabled = fields.Boolean(required=True, description="CDN機能の有効/無効")
    provider = fields.String(required=True, description="CDNプロバイダー")
    cache_ttl = fields.Integer(required=True, description="キャッシュTTL（秒）")
    compression_enabled = fields.Boolean(required=True, description="圧縮の有効/無効")
    secure_urls_enabled = fields.Boolean(required=True, description="セキュアURL機能の有効/無効")
    azure_configured = fields.Boolean(required=True, description="Azure CDN設定の有無")
    cloudflare_configured = fields.Boolean(required=True, description="CloudFlare CDN設定の有無")
    generic_configured = fields.Boolean(required=True, description="Generic CDN設定の有無")


class CDNConfigValidationSchema(Schema):
    """CDN設定検証レスポンス."""
    
    provider = fields.String(required=True, description="検証対象プロバイダー")
    valid = fields.Boolean(required=True, description="設定の有効性")
    missing_fields = fields.List(fields.String(), required=True, description="不足している設定項目")
    warnings = fields.List(fields.String(), required=True, description="警告メッセージ")


@bp.get("/status")
@bp.response(200, CDNStatusSchema)
@require_perms("admin")
def get_cdn_status():
    """CDN機能の現在の状態を取得."""
    # Azure CDN設定のチェック
    azure_configured = all([
        settings.cdn_azure_account_name,
        settings.cdn_azure_access_key,
        settings.cdn_azure_profile,
        settings.cdn_azure_endpoint,
    ])
    
    # CloudFlare CDN設定のチェック
    cloudflare_configured = all([
        settings.cdn_cloudflare_api_token,
        settings.cdn_cloudflare_zone_id,
        settings.cdn_cloudflare_origin_hostname,
    ])
    
    # Generic CDN設定のチェック
    generic_configured = all([
        settings.cdn_generic_endpoint,
        settings.cdn_generic_api_token,
    ])
    
    return {
        "enabled": settings.cdn_enabled,
        "provider": settings.cdn_provider,
        "cache_ttl": settings.cdn_cache_ttl,
        "compression_enabled": settings.cdn_enable_compression,
        "secure_urls_enabled": settings.cdn_secure_urls_enabled,
        "azure_configured": azure_configured,
        "cloudflare_configured": cloudflare_configured,
        "generic_configured": generic_configured,
    }


@bp.get("/validate-config")
@bp.response(200, CDNConfigValidationSchema)
@require_perms("admin")
def validate_cdn_config():
    """現在のCDN設定を検証."""
    provider = settings.cdn_provider
    valid = False
    missing_fields = []
    warnings = []
    
    if provider == "none" or not settings.cdn_enabled:
        return {
            "provider": provider,
            "valid": True,
            "missing_fields": [],
            "warnings": ["CDNが無効になっています"],
        }
    
    # Azure CDN設定の検証
    if provider == "azure":
        required_fields = [
            ("cdn_azure_account_name", "Azure CDNアカウント名"),
            ("cdn_azure_access_key", "Azure CDNアクセスキー"),
            ("cdn_azure_profile", "Azure CDNプロファイル"),
            ("cdn_azure_endpoint", "Azure CDNエンドポイント"),
        ]
        
        for field_name, field_label in required_fields:
            if not getattr(settings, field_name):
                missing_fields.append(field_label)
        
        if not missing_fields:
            valid = True
            
        # セキュアURL設定のチェック
        if settings.cdn_secure_urls_enabled and not settings.cdn_access_key:
            warnings.append("セキュアURL機能が有効ですが、アクセスキーが設定されていません")
    
    # CloudFlare CDN設定の検証
    elif provider == "cloudflare":
        required_fields = [
            ("cdn_cloudflare_api_token", "CloudFlare APIトークン"),
            ("cdn_cloudflare_zone_id", "CloudFlare ゾーンID"),
            ("cdn_cloudflare_origin_hostname", "CloudFlare オリジンホスト名"),
        ]
        
        for field_name, field_label in required_fields:
            if not getattr(settings, field_name):
                missing_fields.append(field_label)
        
        if not missing_fields:
            valid = True
            
        if settings.cdn_secure_urls_enabled and not settings.cdn_access_key:
            warnings.append("セキュアURL機能が有効ですが、アクセスキーが設定されていません")
    
    # Generic CDN設定の検証
    elif provider == "generic":
        required_fields = [
            ("cdn_generic_endpoint", "Generic CDN エンドポイント"),
            ("cdn_generic_api_token", "Generic CDN APIトークン"),
        ]
        
        for field_name, field_label in required_fields:
            if not getattr(settings, field_name):
                missing_fields.append(field_label)
        
        if not missing_fields:
            valid = True
    
    else:
        warnings.append(f"未対応のCDNプロバイダー: {provider}")
    
    # キャッシュTTLの妥当性チェック
    if settings.cdn_cache_ttl < 60:
        warnings.append("キャッシュTTLが60秒未満です（推奨: 3600秒以上）")
    elif settings.cdn_cache_ttl > 86400 * 7:  # 7日
        warnings.append("キャッシュTTLが7日を超えています（推奨: 1日以内）")
    
    return {
        "provider": provider,
        "valid": valid,
        "missing_fields": missing_fields,
        "warnings": warnings,
    }