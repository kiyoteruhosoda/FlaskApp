#!/bin/bash
# Redis AOF修復スクリプト

set -e

echo "=== Redis AOF修復開始 ==="

# Redisコンテナを停止
echo "1. Redisコンテナを停止中..."
docker stop photonest-redis-1 || true

# AOFファイルの場所を確認（docker volumeを使用している場合）
REDIS_VOLUME=$(docker volume ls -q | grep redis)
if [ -n "$REDIS_VOLUME" ]; then
    echo "2. Redisボリューム発見: $REDIS_VOLUME"
    
    # 一時コンテナでボリュームをマウントしてAOFファイルを確認
    echo "3. AOFファイルをバックアップ中..."
    docker run --rm -v $REDIS_VOLUME:/data alpine sh -c "cd /data && ls -la appendonly.aof.* 2>/dev/null || echo 'AOFファイルが見つかりません'"
    
    # AOFファイルを修復
    echo "4. AOFファイルを修復中..."
    docker run --rm -v $REDIS_VOLUME:/data redis:7-alpine redis-check-aof --fix /data/appendonly.aof.manifest
    
    echo "5. 修復完了"
else
    echo "Redisボリュームが見つかりません"
fi

# Redisコンテナを再起動
echo "6. Redisコンテナを起動中..."
docker start photonest-redis-1

echo "7. Redisログを確認中（Ctrl+Cで終了）..."
sleep 3
docker logs -f --tail 50 photonest-redis-1
