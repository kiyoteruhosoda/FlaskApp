"""Blob Storage設定管理API."""

from __future__ import annotations

from flask_smorest import Blueprint
from flask_smorest import Page
from marshmallow import Schema, fields

from core.settings import settings
from core.models.authz import require_perms

__all__ = ["bp"]

bp = Blueprint("blob", __name__, url_prefix="/api/admin/blob")


class BlobStatusSchema(Schema):
    """Blob Storage状態レスポンス."""
    
    enabled = fields.Boolean(required=True, metadata={"description": "Blob Storage機能の有効/無効"})
    provider = fields.String(required=True, metadata={"description": "Blobストレージプロバイダー"})
    container_name = fields.String(required=True, metadata={"description": "コンテナ名"})
    endpoint_suffix = fields.String(required=True, metadata={"description": "エンドポイントサフィックス"})
    secure_transfer = fields.Boolean(required=True, metadata={"description": "セキュア転送の有効/無効"})
    auto_create_container = fields.Boolean(required=True, metadata={"description": "コンテナ自動作成の有効/無効"})
    public_access_level = fields.String(required=True, metadata={"description": "パブリックアクセスレベル"})
    connection_configured = fields.Boolean(required=True, metadata={"description": "接続設定の有無"})
    account_configured = fields.Boolean(required=True, metadata={"description": "アカウント設定の有無"})
    sas_token_configured = fields.Boolean(required=True, metadata={"description": "SASトークン設定の有無"})


class BlobConfigValidationSchema(Schema):
    """Blob Storage設定検証レスポンス."""
    
    provider = fields.String(required=True, metadata={"description": "検証対象プロバイダー"})
    valid = fields.Boolean(required=True, metadata={"description": "設定の有効性"})
    missing_fields = fields.List(fields.String(), required=True, metadata={"description": "不足している設定項目"})
    warnings = fields.List(fields.String(), required=True, metadata={"description": "警告メッセージ"})
    recommendations = fields.List(fields.String(), required=True, metadata={"description": "推奨事項"})


@bp.get("/status")
@bp.response(200, BlobStatusSchema)
@require_perms("admin")
def get_blob_status():
    """Blob Storage機能の現在の状態を取得."""
    # 接続文字列設定のチェック
    connection_configured = bool(settings.blob_connection_string)
    
    # アカウント設定のチェック（接続文字列の代替）
    account_configured = all([
        settings.blob_account_name,
        settings.blob_access_key,
    ])
    
    # SASトークン設定のチェック
    sas_token_configured = bool(settings.blob_sas_token)
    
    return {
        "enabled": settings.blob_enabled,
        "provider": settings.blob_provider,
        "container_name": settings.blob_container_name,
        "endpoint_suffix": settings.blob_endpoint_suffix,
        "secure_transfer": settings.blob_secure_transfer,
        "auto_create_container": settings.blob_create_container_if_not_exists,
        "public_access_level": settings.blob_public_access_level,
        "connection_configured": connection_configured,
        "account_configured": account_configured,
        "sas_token_configured": sas_token_configured,
    }


@bp.get("/validate-config")
@bp.response(200, BlobConfigValidationSchema)
@require_perms("admin")
def validate_blob_config():
    """現在のBlob Storage設定を検証."""
    provider = settings.blob_provider
    valid = False
    missing_fields = []
    warnings = []
    recommendations = []
    
    if provider == "none" or not settings.blob_enabled:
        return {
            "provider": provider,
            "valid": True,
            "missing_fields": [],
            "warnings": ["Blob Storageが無効になっています"],
            "recommendations": ["ローカルストレージのみを使用します"],
        }
    
    if provider == "local":
        return {
            "provider": provider,
            "valid": True,
            "missing_fields": [],
            "warnings": [],
            "recommendations": [
                "ローカルファイルシステムを使用します",
                "スケーラビリティを向上するにはAzure Blob Storageを検討してください"
            ],
        }
    
    # Azure Blob Storage設定の検証
    if provider == "azure":
        has_connection_string = bool(settings.blob_connection_string)
        has_account_credentials = all([
            settings.blob_account_name,
            settings.blob_access_key,
        ])
        has_sas_token = bool(settings.blob_sas_token)
        
        # 認証方法のチェック
        if not (has_connection_string or has_account_credentials or has_sas_token):
            missing_fields.extend([
                "接続文字列",
                "または アカウント名＋アクセスキー",
                "または SASトークン"
            ])
        else:
            valid = True
            
            # 推奨認証方法の確認
            if has_connection_string:
                recommendations.append("接続文字列を使用（推奨方法）")
            elif has_account_credentials:
                recommendations.append("アカウント名＋アクセスキーを使用")
                warnings.append("接続文字列の使用を推奨します")
            elif has_sas_token:
                recommendations.append("SASトークンを使用")
                warnings.append("SASトークンの有効期限を定期的に確認してください")
        
        # コンテナ名のチェック
        if not settings.blob_container_name:
            missing_fields.append("コンテナ名")
            valid = False
        else:
            container_name = settings.blob_container_name.lower()
            if not (3 <= len(container_name) <= 63):
                warnings.append("コンテナ名は3-63文字である必要があります")
            elif not container_name.replace('-', '').replace('_', '').isalnum():
                warnings.append("コンテナ名に無効な文字が含まれている可能性があります")
        
        # セキュリティ設定のチェック
        if not settings.blob_secure_transfer:
            warnings.append("セキュア転送が無効です（セキュリティリスク）")
        else:
            recommendations.append("セキュア転送が有効（推奨）")
        
        # パブリックアクセスレベルのチェック
        if settings.blob_public_access_level == "container":
            warnings.append("コンテナが完全にパブリックアクセス可能です（セキュリティリスク）")
        elif settings.blob_public_access_level == "blob":
            recommendations.append("Blobレベルのパブリックアクセスが設定されています")
        else:
            recommendations.append("プライベートアクセス（最もセキュア）")
        
        # エンドポイントサフィックスのチェック
        if settings.blob_endpoint_suffix != "core.windows.net":
            if settings.blob_endpoint_suffix in ["core.chinacloudapi.cn", "core.cloudapi.de", "core.usgovcloudapi.net"]:
                recommendations.append(f"特別なAzureクラウド環境: {settings.blob_endpoint_suffix}")
            else:
                warnings.append(f"非標準のエンドポイントサフィックス: {settings.blob_endpoint_suffix}")
    
    else:
        warnings.append(f"未対応のBlobプロバイダー: {provider}")
    
    # コンテナ自動作成の推奨事項
    if settings.blob_create_container_if_not_exists:
        recommendations.append("コンテナ自動作成が有効（便利）")
    else:
        warnings.append("コンテナ自動作成が無効（手動でコンテナを作成してください）")
    
    return {
        "provider": provider,
        "valid": valid,
        "missing_fields": missing_fields,
        "warnings": warnings,
        "recommendations": recommendations,
    }