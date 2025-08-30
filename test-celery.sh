#!/bin/bash
# Celeryタスクテストスクリプト

echo "=== Celeryタスクテスト ==="

# 現在のプロジェクトディレクトリから実行することを想定
if [ ! -f "docker-compose.yml" ]; then
    echo "エラー: docker-compose.ymlが見つかりません。プロジェクトルートで実行してください。"
    exit 1
fi

# 1. Celeryサービスが起動しているか確認
echo "1. Celeryサービスの確認..."
if ! docker-compose ps worker | grep -q "Up"; then
    echo "Celery Workerが起動していません。起動します..."
    docker-compose up -d worker
    sleep 10
fi

# 2. テスト用Pythonスクリプトを実行
echo "2. テストタスクを実行中..."
docker-compose exec web python -c "
import sys
sys.path.append('/app')

try:
    from cli.src.celery.tasks import app as celery_app
    
    # Celeryアプリの状態確認
    print('Celery app:', celery_app)
    
    # 利用可能なタスクを表示
    print('利用可能なタスク:')
    for task_name in sorted(celery_app.tasks.keys()):
        if not task_name.startswith('celery.'):
            print(f'  - {task_name}')
    
    # 簡単なテストタスク実行（もしあれば）
    # result = celery_app.send_task('some_test_task')
    # print(f'タスクID: {result.id}')
    
except Exception as e:
    print(f'エラー: {e}')
    import traceback
    traceback.print_exc()
"

echo ""
echo "3. Celery Workerの最新ログ:"
docker-compose logs --tail=20 worker
