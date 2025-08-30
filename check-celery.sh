#!/bin/bash
# Celery動作確認スクリプト

echo "=== Celery動作確認 ==="

# 1. Celeryコンテナのステータス確認
echo "1. Celeryコンテナの状態:"
docker-compose ps worker beat

echo ""

# 2. Celery Workerのログ確認
echo "2. Celery Workerのログ (最新10行):"
docker-compose logs --tail=10 worker

echo ""

# 3. Celery Beatのログ確認
echo "3. Celery Beatのログ (最新10行):"
docker-compose logs --tail=10 beat

echo ""

# 4. Redisの接続確認
echo "4. Redis接続確認:"
docker-compose exec redis redis-cli ping

echo ""

# 5. Celeryの統計情報取得
echo "5. Celery統計情報:"
docker-compose exec worker celery -A cli.src.celery.tasks inspect stats

echo ""

# 6. アクティブなタスク確認
echo "6. アクティブなタスク:"
docker-compose exec worker celery -A cli.src.celery.tasks inspect active

echo ""

# 7. 登録されたタスク一覧
echo "7. 登録されたタスク一覧:"
docker-compose exec worker celery -A cli.src.celery.tasks inspect registered
