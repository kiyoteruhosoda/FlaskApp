# PhotoNest 使い方手順書

## 1. 概要
PhotoNest は Flask をベースにしたウェブアプリケーションで、Google フォト同期やサムネイル生成などの処理をバックグラウンドジョブ（Celery）で行う構成です。

## 2. 必要環境
- Python 3.10 以上
- Redis（Celery の broker / backend 用）
- `requirements.txt` に記載されたライブラリ

## 3. セットアップ
```bash
pip install -r requirements.txt
cp .env.example .env  # 必要に応じて編集
python main.py        # 開発サーバーを起動
```

古い pip を使っている場合は先にアップデートします。
```bash
python -m pip install --upgrade pip
```

## 4. 開発サーバーの起動
アプリケーションファクトリから Flask アプリを生成し、デバッグモードで起動します。
```bash
python main.py
```

## 5. 翻訳ファイルのコンパイル
多言語対応のメッセージファイルを更新したら、次のコマンドでコンパイルします。
```bash
pybabel compile -d webapp/translations -f
```

## 6. 環境変数と設定
`.env` をコピーして必要な値を設定します。
```bash
cp .env.example .env
# 値を編集
```
主な設定項目（抜粋）:
- `SECRET_KEY`: アプリケーションの秘密鍵
- `DATABASE_URI`: SQLAlchemy の接続文字列
- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`: Google OAuth
- `OAUTH_TOKEN_KEY` または `OAUTH_TOKEN_KEY_FILE`: OAuth トークン暗号化用鍵

## 7. データベースマイグレーション
1. モデル変更後にマイグレーションファイルを作成  
   ```bash
   flask db migrate -m "変更内容のコメント"
   ```
2. マイグレーションを適用  
   ```bash
   flask db upgrade
   ```

## 8. Celery バックグラウンドジョブ
定義済みタスクを実行するにはワーカーとスケジューラを起動します。

### 8.1 ワーカーの起動
```bash
# ワーカー（修正後のアプリケーションコンテキスト対応版）
celery -A cli.src.celery.celery_app worker --loglevel=info --concurrency=2

# バックグラウンドで実行する場合
nohup celery -A cli.src.celery.celery_app worker --loglevel=info --concurrency=2 &
```

### 8.2 スケジューラの起動
```bash
# スケジューラ (beat)
celery -A cli.src.celery.celery_app beat --loglevel=info

# バックグラウンドで実行する場合
nohup celery -A cli.src.celery.celery_app beat --loglevel=info &
```

### 8.3 重要な修正内容
- **アプリケーションコンテキスト対応**: Celeryタスクが自動的にFlaskアプリケーションコンテキスト内で実行されるよう修正されました
- **"Working outside of application context" エラーの解消**: ContextTaskクラスにより、すべてのCeleryタスクがデータベースアクセス可能になりました
- **タスク登録の改善**: `cli.src.celery.celery_app` から統一的にタスクを管理

### 8.4 利用可能なタスク
- `picker_import.watchdog`: Photo picker のwatchdogタスク（1分毎に自動実行）
- `picker_import.item`: 個別のpicker importタスク
- `cli.src.celery.tasks.dummy_long_task`: サンプルの長時間実行タスク
- `cli.src.celery.tasks.download_file`: ファイルダウンロードタスク

### 8.5 手動でのタスク実行例
```python
# Python shell でのタスク実行例
from cli.src.celery.tasks import picker_import_watchdog_task
result = picker_import_watchdog_task.delay()
print(f'Task ID: {result.id}')
```

## 9. Google OAuth トークン暗号化
`google_account.oauth_token_json` は AES-256-GCM で暗号化されます。`OAUTH_TOKEN_KEY`（Base64 形式 32 バイト）または鍵ファイルを `.env` で指定してください。

## 10. テストの実行
`pytest` を使用してユニットテストを実行できます。

### 10.1 全テストの実行
```bash
pytest
```

### 10.2 Celeryテストの実行
今回のアプリケーションコンテキスト修正に対応したCeleryテストも追加されています：
```bash
# Celery関連のテストのみ実行
pytest tests/test_celery_*.py -v

# 特定のテストクラス実行
pytest tests/test_celery_context.py::TestCeleryAppContext -v

# Celeryアプリケーション設定テスト
pytest tests/test_celery_app.py::TestCeleryAppConfiguration -v
```

### 10.3 テストカバレッジ
Celeryテストは以下をカバーします：
- アプリケーションコンテキストの正常動作
- データベースアクセスの確認  
- タスク登録の確認
- エラーハンドリング
- パフォーマンステスト

## 11. トラブルシューティング

### 11.1 Celeryタスクで "Working outside of application context" エラーが発生する場合
このエラーは修正済みですが、もし発生した場合：
```bash
# 古いワーカープロセスを停止
pkill -f "celery.*worker"
pkill -f "celery.*beat"

# 新しいワーカーを起動（修正版）
celery -A cli.src.celery.celery_app worker --loglevel=info --concurrency=2
celery -A cli.src.celery.celery_app beat --loglevel=info
```

### 11.2 Redisへの接続エラー
```bash
# Redisの状態確認
redis-cli ping

# Redisが停止している場合は起動
sudo systemctl start redis-server
# または Docker の場合
docker run -d -p 6379:6379 redis:alpine
```

### 11.3 データベースマイグレーションエラー
```bash
# マイグレーション状態確認
flask db current

# 強制的にマイグレーション実行
flask db stamp head
flask db upgrade
```

### 11.4 OAuth トークン暗号化エラー
`.env`で以下が正しく設定されているか確認：
```bash
# 32バイトのBase64エンコードされたキー
OAUTH_TOKEN_KEY=base64:...

# またはキーファイルのパス
OAUTH_TOKEN_KEY_FILE=/path/to/key/file
```
