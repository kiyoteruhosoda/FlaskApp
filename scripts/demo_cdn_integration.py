#!/usr/bin/env python3
"""PhotoNest CDN統合デモ.

このスクリプトは、PhotoNestのCDN対応機能をデモンストレーションします。
Azure CDNとCloudFlare CDNの両方に対応し、画像の配信を高速化します。

Usage:
    python demo_cdn_integration.py
"""

import tempfile
from pathlib import Path

from bounded_contexts.storage.application import StorageApplicationService
from bounded_contexts.storage.domain import (
    StorageBackendType,
    StorageConfiguration,
    StorageCredentials,
    StorageDomain,
    StorageIntent,
    StoragePath,
)
from bounded_contexts.storage.infrastructure import InMemoryStorageRepository


def demo_azure_cdn_integration():
    """Azure CDN統合のデモンストレーション."""
    print("🔵 Azure CDN統合デモを開始します...")
    
    # リポジトリとサービスを初期化
    repository = InMemoryStorageRepository()
    service = StorageApplicationService(repository)
    
    # Azure CDN設定
    cdn_credentials = StorageCredentials(
        backend_type=StorageBackendType.AZURE_CDN,
        account_name="photonestcdn",
        access_key="azure-cdn-access-key-12345",
        cdn_profile="photonest-profile",
        cdn_endpoint="photonestcdn",
    )
    
    # オリジンストレージ（Azure Blob）設定
    origin_credentials = StorageCredentials(
        backend_type=StorageBackendType.AZURE_BLOB,
        connection_string="DefaultEndpointsProtocol=https;AccountName=photonestorigin;AccountKey=origin-key==",
        container_name="images",
    )
    
    cdn_config = StorageConfiguration(
        backend_type=StorageBackendType.AZURE_CDN,
        credentials=cdn_credentials,
        origin_backend_type=StorageBackendType.AZURE_BLOB,
        origin_credentials=origin_credentials,
        cache_ttl=7200,  # 2時間
        enable_compression=True,
    )
    
    domain = "azure-cdn-photos"
    
    try:
        # ストレージドメイン設定
        service.configure_storage(domain, cdn_config)
        print(f"✅ Azure CDNストレージドメイン '{domain}' を設定しました")
        
        # サンプル画像パス
        photo_path = StoragePath(
            domain=StorageDomain.MEDIA,
            intent=StorageIntent.ORIGINAL,
            relative_path="2024/01/30/family_vacation.jpg",
        )
        
        # CDN URLを生成
        cdn_url = service.get_cdn_url(domain, photo_path)
        print(f"📸 CDN URL: {cdn_url}")
        
        # セキュアCDN URL（1時間有効、特定IPからのみアクセス可能）
        secure_url = service.generate_secure_cdn_url(
            domain,
            photo_path,
            expiration_seconds=3600,
            allowed_ip="203.0.113.100",
        )
        print(f"🔐 セキュアCDN URL: {secure_url}")
        
        # サンプル画像をアップロードしてCDNで配信
        sample_image = b"Sample JPEG image data for PhotoNest CDN demo"
        metadata = service.upload_and_distribute(domain, photo_path, sample_image)
        
        print(f"⬆️  画像アップロード完了:")
        print(f"   - サイズ: {metadata.size} bytes")
        print(f"   - CDN URL: {metadata.cdn_url}")
        print(f"   - キャッシュステータス: {metadata.cache_status}")
        
        # キャッシュパージ（画像を更新した場合）
        purge_job_id = service.purge_cdn_cache(domain, [photo_path], purge_type="url", priority=1)
        print(f"🧹 キャッシュパージジョブID: {purge_job_id}")
        
        # アナリティクス取得
        analytics_prefix = StoragePath(
            domain=StorageDomain.MEDIA,
            intent=StorageIntent.ORIGINAL,
            relative_path="2024/01/",
        )
        
        analytics = service.get_cdn_analytics(
            domain,
            analytics_prefix,
            "2024-01-30T00:00:00Z",
            "2024-01-30T23:59:59Z",
        )
        
        print(f"📊 1月30日のアナリティクス: {len(analytics)} 件のレコード")
        if analytics:
            top_record = analytics[0]
            print(f"   - トップパス: {top_record.path}")
            print(f"   - リクエスト数: {top_record.requests_count}")
            print(f"   - キャッシュヒット率: {top_record.cache_hit_ratio:.2%}")
        
    except Exception as e:
        print(f"❌ Azure CDNデモでエラーが発生: {e}")
    
    print("🔵 Azure CDNデモ終了\n")


def demo_cloudflare_cdn_integration():
    """CloudFlare CDN統合のデモンストレーション."""
    print("🟠 CloudFlare CDN統合デモを開始します...")
    
    # リポジトリとサービスを初期化
    repository = InMemoryStorageRepository()
    service = StorageApplicationService(repository)
    
    with tempfile.TemporaryDirectory() as temp_dir:
        # CloudFlare CDN設定
        cdn_credentials = StorageCredentials(
            backend_type=StorageBackendType.CLOUDFLARE_CDN,
            api_token="cloudflare-api-token-67890",
            zone_id="cf-zone-id-12345",
            origin_hostname="photos.photonest.example",
            access_key="cf-signing-key-secret",
        )
        
        # オリジンストレージ（ローカル）設定
        origin_credentials = StorageCredentials(
            backend_type=StorageBackendType.LOCAL,
        )
        
        cdn_config = StorageConfiguration(
            backend_type=StorageBackendType.CLOUDFLARE_CDN,
            credentials=cdn_credentials,
            origin_backend_type=StorageBackendType.LOCAL,
            origin_credentials=origin_credentials,
            base_path=temp_dir,
            cache_ttl=3600,  # 1時間
        )
        
        domain = "cloudflare-cdn-photos"
        
        try:
            # ストレージドメイン設定
            service.configure_storage(domain, cdn_config)
            print(f"✅ CloudFlare CDNストレージドメイン '{domain}' を設定しました")
            
            # サンプル動画パス（CDNで配信）
            video_path = StoragePath(
                domain=StorageDomain.MEDIA,
                intent=StorageIntent.CDN_OPTIMIZED,
                relative_path="2024/01/30/birthday_party.mp4",
            )
            
            # CDN URLを生成
            cdn_url = service.get_cdn_url(domain, video_path)
            print(f"🎥 動画CDN URL: {cdn_url}")
            
            # 地域制限付きセキュアURL（日本からのみアクセス可能）
            geo_restricted_url = service.generate_secure_cdn_url(
                domain,
                video_path,
                expiration_seconds=1800,  # 30分
                allowed_countries=["JP"],
            )
            print(f"🌏 地域制限URL: {geo_restricted_url}")
            
            # 複数ファイルのプリフェッチ（人気コンテンツを事前にキャッシュ）
            popular_paths = [
                StoragePath(domain=StorageDomain.MEDIA, intent=StorageIntent.ORIGINAL, relative_path="trending/photo1.jpg"),
                StoragePath(domain=StorageDomain.MEDIA, intent=StorageIntent.ORIGINAL, relative_path="trending/photo2.jpg"),
                StoragePath(domain=StorageDomain.THUMBNAILS, intent=StorageIntent.THUMBNAIL, relative_path="trending/thumb1.jpg"),
            ]
            
            service.prefetch_to_cdn(domain, popular_paths)
            print(f"🚀 {len(popular_paths)} 件のファイルをプリフェッチしました")
            
            # タグベースでのキャッシュパージ（特定カテゴリ全体を更新）
            tag_path = StoragePath(
                domain=StorageDomain.MEDIA,
                intent=StorageIntent.ORIGINAL,
                relative_path="category:family",
            )
            
            tag_purge_job = service.purge_cdn_cache(domain, [tag_path], purge_type="tag", priority=2)
            print(f"🏷️  'family'タグのキャッシュパージジョブ: {tag_purge_job}")
            
            # CloudFlareゾーン全体のアナリティクス
            zone_analytics = service.get_cdn_analytics(
                domain,
                StoragePath(domain="*", intent="*", relative_path=""),
                "2024-01-30T00:00:00Z", 
                "2024-01-30T23:59:59Z",
            )
            
            print(f"📈 CloudFlareゾーン全体のアナリティクス:")
            if zone_analytics:
                zone_stats = zone_analytics[0]
                print(f"   - 総リクエスト数: {zone_stats.requests_count:,}")
                print(f"   - 総転送量: {zone_stats.bandwidth_bytes / 1024 / 1024:.1f} MB")
                print(f"   - 平均キャッシュヒット率: {zone_stats.cache_hit_ratio:.2%}")
            
        except Exception as e:
            print(f"❌ CloudFlare CDNデモでエラーが発生: {e}")
    
    print("🟠 CloudFlare CDNデモ終了\n")


def demo_cdn_fallback_behavior():
    """CDNフォールバック動作のデモンストレーション."""
    print("⚪ CDNフォールバック動作デモを開始します...")
    
    # リポジトリとサービスを初期化
    repository = InMemoryStorageRepository()
    service = StorageApplicationService(repository)
    
    with tempfile.TemporaryDirectory() as temp_dir:
        # 通常のローカルストレージ設定（CDNなし）
        local_credentials = StorageCredentials(backend_type=StorageBackendType.LOCAL)
        local_config = StorageConfiguration(
            backend_type=StorageBackendType.LOCAL,
            credentials=local_credentials,
            base_path=temp_dir,
        )
        
        domain = "local-fallback"
        service.configure_storage(domain, local_config)
        
        sample_path = StoragePath(
            domain=StorageDomain.MEDIA,
            intent=StorageIntent.ORIGINAL,
            relative_path="test.jpg",
        )
        
        try:
            # CDN URLを要求するが、ローカルファイルURLが返される
            fallback_url = service.get_cdn_url(domain, sample_path)
            print(f"🔄 ローカルストレージフォールバックURL: {fallback_url}")
            
            # CDNプリフェッチを要求するが、警告ログのみでエラーにならない
            service.prefetch_to_cdn(domain, [sample_path])
            print(f"⚠️  CDN非対応バックエンドでプリフェッチ要求（警告ログのみ）")
            
        except Exception as e:
            print(f"❌ フォールバックデモでエラー: {e}")
    
    print("⚪ CDNフォールバック動作デモ終了\n")


def demo_cdn_performance_comparison():
    """CDN性能比較のデモンストレーション."""
    print("📊 CDN性能比較デモを開始します...")
    
    # 実際の性能測定は外部システムに依存するため、
    # ここでは設定の比較とURLパターンの確認を行う
    
    configs = {
        "Azure CDN": {
            "endpoint": "photonestcdn.azureedge.net",
            "cache_ttl": 7200,
            "compression": True,
            "global_pops": 190,
        },
        "CloudFlare CDN": {
            "endpoint": "photos.photonest.example",
            "cache_ttl": 3600,
            "compression": True,
            "global_pops": 320,
        },
    }
    
    print("CDN設定比較:")
    for provider, config in configs.items():
        print(f"  {provider}:")
        print(f"    - エンドポイント: {config['endpoint']}")
        print(f"    - キャッシュTTL: {config['cache_ttl']} 秒")
        print(f"    - 圧縮: {'有効' if config['compression'] else '無効'}")
        print(f"    - グローバルPoP数: {config['global_pops']}")
    
    print("\n📊 CDN性能比較デモ終了\n")


def main():
    """メインデモ実行."""
    print("🌐 PhotoNest CDN統合デモプログラム")
    print("=" * 50)
    
    # Azure CDNデモ
    demo_azure_cdn_integration()
    
    # CloudFlare CDNデモ
    demo_cloudflare_cdn_integration()
    
    # フォールバック動作デモ
    demo_cdn_fallback_behavior()
    
    # 性能比較デモ
    demo_cdn_performance_comparison()
    
    print("🎉 全CDNデモが完了しました！")
    print("\n📝 次のステップ:")
    print("1. 実際のCDNプロバイダーアカウントを設定")
    print("2. API認証情報を環境変数に設定")
    print("3. 本番環境でCDN配信をテスト")
    print("4. アナリティクスデータで性能を監視")


if __name__ == "__main__":
    main()