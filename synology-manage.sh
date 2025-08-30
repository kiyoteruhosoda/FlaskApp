#!/bin/bash
# Synology PhotoNest 管理スクリプト

DOCKER_DIR="/volume1/docker/photonest"
cd $DOCKER_DIR

case "$1" in
    start)
        echo "PhotoNest サービスを起動中..."
        docker-compose up -d
        echo "✅ PhotoNest が起動しました"
        echo "アクセスURL: http://localhost:5000"
        ;;
    
    stop)
        echo "PhotoNest サービスを停止中..."
        docker-compose down
        echo "✅ PhotoNest が停止しました"
        ;;
    
    restart)
        echo "PhotoNest サービスを再起動中..."
        docker-compose restart
        echo "✅ PhotoNest が再起動しました"
        ;;
    
    status)
        echo "=== PhotoNest サービス状態 ==="
        docker-compose ps
        echo ""
        echo "=== ヘルスチェック ==="
        curl -s http://localhost:5000/api/health && echo "✅ Web服务正常" || echo "❌ Web服务异常"
        ;;
    
    logs)
        SERVICE=${2:-"photonest-web"}
        echo "=== $SERVICE ログ ==="
        docker-compose logs -f --tail=50 $SERVICE
        ;;
    
    backup)
        BACKUP_DIR="$DOCKER_DIR/backups"
        DATE=$(date +%Y%m%d_%H%M%S)
        mkdir -p $BACKUP_DIR
        
        echo "データベースバックアップ中..."
        docker-compose exec -T photonest-db mysqldump -u root -p${DB_ROOT_PASSWORD} \
            --single-transaction photonest > $BACKUP_DIR/photonest_db_$DATE.sql
        
        echo "設定ファイルバックアップ中..."
        cp config/.env $BACKUP_DIR/env_$DATE.backup
        
        echo "✅ バックアップ完了: $BACKUP_DIR/photonest_db_$DATE.sql"
        ;;
    
    update)
        echo "PhotoNest アップデート中..."
        echo "⚠️  データベースバックアップを取得することを推奨します"
        read -p "続行しますか? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            # バックアップを自動実行
            $0 backup
            
            # イメージを再ビルド
            docker-compose build --no-cache
            
            # サービスを再起動
            docker-compose up -d
            
            # マイグレーション実行
            echo "データベースマイグレーション実行中..."
            docker-compose exec photonest-web flask db upgrade
            
            echo "✅ アップデート完了"
        else
            echo "アップデートをキャンセルしました"
        fi
        ;;
    
    shell)
        SERVICE=${2:-"photonest-web"}
        echo "$SERVICE コンテナにシェル接続中..."
        docker-compose exec $SERVICE bash
        ;;
    
    clean)
        echo "未使用のDockerリソースをクリーンアップ中..."
        docker system prune -f
        docker volume prune -f
        echo "✅ クリーンアップ完了"
        ;;
    
    monitor)
        echo "=== PhotoNest リアルタイム監視 ==="
        echo "Ctrl+C で終了"
        echo ""
        
        while true; do
            clear
            echo "=== $(date) ==="
            echo ""
            echo "コンテナ状態:"
            docker-compose ps
            echo ""
            echo "リソース使用量:"
            docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" \
                $(docker-compose ps -q)
            echo ""
            echo "ディスク使用量:"
            du -sh data/* 2>/dev/null || echo "データディレクトリなし"
            echo ""
            echo "最新ログ:"
            docker-compose logs --tail=3 photonest-web
            
            sleep 10
        done
        ;;
    
    help|*)
        echo "PhotoNest Synology 管理スクリプト"
        echo ""
        echo "使用方法: $0 <コマンド> [オプション]"
        echo ""
        echo "コマンド:"
        echo "  start          PhotoNestサービスを起動"
        echo "  stop           PhotoNestサービスを停止"
        echo "  restart        PhotoNestサービスを再起動"
        echo "  status         サービス状態を表示"
        echo "  logs [service] ログを表示 (デフォルト: photonest-web)"
        echo "  backup         データベースと設定をバックアップ"
        echo "  update         PhotoNestをアップデート"
        echo "  shell [service] コンテナにシェル接続"
        echo "  clean          未使用リソースをクリーンアップ"
        echo "  monitor        リアルタイム監視"
        echo "  help           このヘルプを表示"
        echo ""
        echo "例:"
        echo "  $0 start"
        echo "  $0 logs photonest-worker"
        echo "  $0 shell photonest-web"
        ;;
esac
