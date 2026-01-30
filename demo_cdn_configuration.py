#!/usr/bin/env python3
"""CDN・Blob Storage設定のデモ・検証スクリプト."""

import os
import sys
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv()

from core.settings import settings


def print_cdn_settings():
    """現在のCDN設定を表示."""
    print("=== PhotoNest CDN設定確認 ===\n")
    
    # 基本設定
    print("【基本設定】")
    print(f"CDN有効: {settings.cdn_enabled}")
    print(f"CDNプロバイダー: {settings.cdn_provider}")
    print(f"キャッシュTTL: {settings.cdn_cache_ttl}秒")
    print(f"圧縮有効: {settings.cdn_enable_compression}")
    print(f"セキュアURL有効: {settings.cdn_secure_urls_enabled}")
    print()
    
    if not settings.cdn_enabled:
        print("⚠️  CDNが無効になっています")
        print("   システム設定で CDN_ENABLED=True に変更してください")
        return
    
    if settings.cdn_provider == "none":
        print("📄 CDNプロバイダーが 'none' に設定されています")
        print("   直接ストレージからの配信になります")
        return
    
    # Azure CDN設定
    if settings.cdn_provider == "azure":
        print("【Azure CDN設定】")
        print(f"アカウント名: {settings.cdn_azure_account_name or '(未設定)'}")
        print(f"アクセスキー: {'設定済み' if settings.cdn_azure_access_key else '(未設定)'}")
        print(f"プロファイル: {settings.cdn_azure_profile or '(未設定)'}")
        print(f"エンドポイント: {settings.cdn_azure_endpoint or '(未設定)'}")
        
        azure_configured = all([
            settings.cdn_azure_account_name,
            settings.cdn_azure_access_key,
            settings.cdn_azure_profile,
            settings.cdn_azure_endpoint,
        ])
        
        if azure_configured:
            print("✅ Azure CDN設定が完了しています")
        else:
            print("❌ Azure CDN設定が不完全です")
            print("   必要な設定項目をシステム設定で追加してください")
        
    # CloudFlare CDN設定
    elif settings.cdn_provider == "cloudflare":
        print("【CloudFlare CDN設定】")
        print(f"APIトークン: {'設定済み' if settings.cdn_cloudflare_api_token else '(未設定)'}")
        print(f"ゾーンID: {settings.cdn_cloudflare_zone_id or '(未設定)'}")
        print(f"オリジンホスト名: {settings.cdn_cloudflare_origin_hostname or '(未設定)'}")
        
        cf_configured = all([
            settings.cdn_cloudflare_api_token,
            settings.cdn_cloudflare_zone_id,
            settings.cdn_cloudflare_origin_hostname,
        ])
        
        if cf_configured:
            print("✅ CloudFlare CDN設定が完了しています")
        else:
            print("❌ CloudFlare CDN設定が不完全です")
            print("   必要な設定項目をシステム設定で追加してください")
    
    # Generic CDN設定
    elif settings.cdn_provider == "generic":
        print("【Generic CDN設定】")
        print(f"エンドポイント: {settings.cdn_generic_endpoint or '(未設定)'}")
        print(f"APIトークン: {'設定済み' if settings.cdn_generic_api_token else '(未設定)'}")
        
        generic_configured = all([
            settings.cdn_generic_endpoint,
            settings.cdn_generic_api_token,
        ])
        
        if generic_configured:
            print("✅ Generic CDN設定が完了しています")
        else:
            print("❌ Generic CDN設定が不完全です")
            print("   必要な設定項目をシステム設定で追加してください")
    
    else:
        print(f"❌ 未対応のCDNプロバイダー: {settings.cdn_provider}")
    
    print()
    
    # セキュアURL設定
    if settings.cdn_secure_urls_enabled:
        print("【セキュアURL設定】")
        if settings.cdn_access_key:
            print("✅ アクセスキーが設定されています")
        else:
            print("⚠️  セキュアURL機能が有効ですが、アクセスキーが未設定です")
            print("   CDN_ACCESS_KEY を設定してください")
        print()
    
    # 推奨事項
    print("【推奨設定】")
    if settings.cdn_cache_ttl < 3600:
        print("⚠️  キャッシュTTLが短すぎます（推奨: 3600秒以上）")
    elif settings.cdn_cache_ttl > 86400 * 7:
        print("⚠️  キャッシュTTLが長すぎます（推奨: 7日以内）")
    else:
        print("✅ キャッシュTTLが適切に設定されています")
    
    if settings.cdn_enable_compression:
        print("✅ 圧縮が有効になっています（推奨）")
    else:
        print("ℹ️  圧縮が無効になっています（有効化を推奨）")


def demonstrate_cdn_usage():
    """CDN機能のデモンストレーション."""
    print("\n=== CDN機能デモ ===\n")
    
    if not settings.cdn_enabled or settings.cdn_provider == "none":
        print("CDNが無効のため、デモをスキップします")
        return
    
    try:
        from bounded_contexts.storage.application.services import StorageApplicationService
        from bounded_contexts.storage.infrastructure.in_memory_repository import InMemoryStorageRepository
        from bounded_contexts.storage.domain import StoragePath, StorageDomain, StorageIntent
        
        # テスト用サービス
        repository = InMemoryStorageRepository()
        service = StorageApplicationService(repository)
        
        # テスト用パス
        test_path = StoragePath(
            domain=StorageDomain.MEDIA,
            intent=StorageIntent.ORIGINAL,
            relative_path="2024/01/30/demo.jpg"
        )
        
        print(f"テストパス: {test_path.get_full_path()}")
        
        # CDN URL取得のデモ
        try:
            # 注意: 実際の設定が必要（ここではログ出力のみ）
            print("CDN URL取得をテストしています...")
            print("（実際のCDN APIへの接続は行いません）")
            
            # システム設定に基づくCDN設定情報を表示
            print(f"設定されたCDNプロバイダー: {settings.cdn_provider}")
            print(f"キャッシュTTL: {settings.cdn_cache_ttl}秒")
            
            # 模擬CDN URL
            if settings.cdn_provider == "azure":
                demo_url = f"https://{settings.cdn_azure_endpoint}.azureedge.net/{test_path.get_full_path()}"
                print(f"模擬Azure CDN URL: {demo_url}")
            elif settings.cdn_provider == "cloudflare":
                demo_url = f"https://{settings.cdn_cloudflare_origin_hostname}/{test_path.get_full_path()}"
                print(f"模擬CloudFlare CDN URL: {demo_url}")
            elif settings.cdn_provider == "generic":
                demo_url = f"{settings.cdn_generic_endpoint.rstrip('/')}/{test_path.get_full_path()}"
                print(f"模擬Generic CDN URL: {demo_url}")
            
            print("✅ CDN設定は正常に読み込まれています")
            
        except Exception as e:
            print(f"❌ CDN設定エラー: {e}")
    
    except ImportError as e:
        print(f"❌ モジュールインポートエラー: {e}")
        print("必要な依存関係を確認してください")


def show_help():
    """使用方法を表示."""
    print("""
CDN設定デモスクリプト

使用方法:
  python demo_cdn_configuration.py [オプション]

オプション:
  --settings      現在のCDN設定を表示（デフォルト）
  --demo          CDN機能のデモを実行
  --help, -h      このヘルプを表示

設定方法:
  1. 管理画面: http://localhost:5000/admin/system-settings?section=cdn
  2. CDN専用画面: http://localhost:5000/admin/cdn-configuration
  3. 環境変数: .env ファイルまたは環境変数で設定

主要な環境変数:
  CDN_ENABLED=true
  CDN_PROVIDER=azure|cloudflare|generic|none
  CDN_CACHE_TTL=3600
  CDN_ENABLE_COMPRESSION=true

Azure CDN用:
  CDN_AZURE_ACCOUNT_NAME=your-account
  CDN_AZURE_ACCESS_KEY=your-key
  CDN_AZURE_PROFILE=your-profile
  CDN_AZURE_ENDPOINT=your-endpoint

CloudFlare CDN用:
  CDN_CLOUDFLARE_API_TOKEN=your-token
  CDN_CLOUDFLARE_ZONE_ID=your-zone-id
  CDN_CLOUDFLARE_ORIGIN_HOSTNAME=your-hostname

セキュアURL用:
  CDN_SECURE_URLS_ENABLED=true
  CDN_ACCESS_KEY=your-signing-key
""")


def print_blob_settings():
    """現在のBlob Storage設定を表示."""
    print("=== PhotoNest Blob Storage設定確認 ===\n")
    
    # 基本設定
    print("【基本設定】")
    print(f"Blob有効: {settings.blob_enabled}")
    print(f"Blobプロバイダー: {settings.blob_provider}")
    print(f"コンテナ名: {settings.blob_container_name}")
    print(f"セキュア転送: {settings.blob_secure_transfer}")
    print(f"パブリックアクセス: {settings.blob_public_access_level}")
    print()
    
    if not settings.blob_enabled:
        print("⚠️  Blob Storageが無効になっています")
        print("   システム設定で BLOB_ENABLED=True に変更してください")
        return
    
    if settings.blob_provider == "none":
        print("📄 Blobプロバイダーが 'none' に設定されています")
        print("   ローカルストレージが使用されます")
        return
    
    # Azure Blob Storage設定
    if settings.blob_provider == "azure":
        print("【Azure Blob Storage設定】")
        print(f"アカウント名: {settings.blob_account_name or '(未設定)'}")
        print(f"アクセスキー: {'設定済み' if settings.blob_access_key else '(未設定)'}")
        print(f"接続文字列: {'設定済み' if settings.blob_connection_string else '(未設定)'}")
        print(f"SASトークン: {'設定済み' if settings.blob_sas_token else '(未設定)'}")
        print(f"エンドポイントサフィックス: {settings.blob_endpoint_suffix}")
        
        # 認証方法の判定
        if settings.blob_connection_string:
            print("✅ 認証方法: 接続文字列 (推奨)")
        elif settings.blob_account_name and settings.blob_access_key:
            print("✅ 認証方法: アカウント名 + アクセスキー")
        elif settings.blob_sas_token:
            print("⚠️  認証方法: SASトークン (時間制限あり)")
        else:
            print("❌ 認証情報が不完全です")
            print("   接続文字列、またはアカウント名+アクセスキーを設定してください")
        
        print()
    
    else:
        print(f"❌ 未対応のプロバイダー: {settings.blob_provider}")
        return


def main():
    """メイン実行関数."""
    import argparse
    
    parser = argparse.ArgumentParser(description="PhotoNest CDN・Blob Storage設定デモ・検証")
    parser.add_argument("--cdn", action="store_true", help="CDN設定を表示")
    parser.add_argument("--blob", action="store_true", help="Blob Storage設定を表示")
    parser.add_argument("--settings", action="store_true", help="CDN設定を表示 (後方互換)")
    parser.add_argument("--demo", action="store_true", help="CDN機能のデモを実行")
    
    args = parser.parse_args()
    
    if len(sys.argv) == 1:  # 引数なしの場合はCDN設定を表示
        args.cdn = True
    
    try:
        if args.cdn or args.settings:
            print_cdn_settings()
        
        if args.blob:
            print_blob_settings()
        
        if args.demo:
            demonstrate_cdn_usage()
    
    except KeyboardInterrupt:
        print("\n\n中断されました")
    except Exception as e:
        print(f"\n❌ エラーが発生しました: {e}")
        import traceback
        print(traceback.format_exc())


if __name__ == "__main__":
    main()