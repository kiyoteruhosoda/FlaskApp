# PhotoNest 使い方手順書

## 1. 概要
PhotoNest はDDD（ドメイン駆動設計）アーキテクチャを採用したFlaskベースの家族写真管理・同期プラットフォームです。Google Photos同期、ローカルファイルインポート、動画変換、サムネイル生成などの処理をCeleryによるバックグラウンドジョブで実行します。

本番環境ではDockerコンテナでのデプロイを推奨しており、Web、Celery Worker、Celery Beat、MariaDB、Redisが個別のコンテナで動作します。開発環境では従来通りローカル環境でのセットアップも可能です。

## 2. 必要環境

### 2.1 本番環境（Docker推奨）
- Docker 20.10以上
- Docker Compose v2以上
- 2GB以上のRAM
- 10GB以上のディスク容量

### 2.2 開発環境
- Python 3.10 以上
- Redis（Celery の broker / backend 用）
- MariaDB 10.11（データベース）
- FFmpeg（動画変換用）
- 仮想環境（`.venv`）

## 3. 初期セットアップ
```bash
# 仮想環境作成・有効化
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate  # Windows

# パッケージインストール
pip install --upgrade pip
pip install -r requirements.txt

# 環境設定
cp .env.example .env
# .envファイルを編集してデータベース接続情報やAPIキーを設定

# データベースマイグレーション
flask db upgrade

# マスタデータ投入
flask seed-master
```

## 3.1 マスタデータ管理

PhotoNestでは、ロール・権限・初期ユーザーなどのマスタデータをmigrationファイルとは分離して管理しています。これにより、migrationファイルの再作成時にマスタデータを手動で追加する手間を省けます。

### 3.1.1 Flaskコマンドでの投入（推奨）
```bash
# 仮想環境を有効化
source .venv/bin/activate

# マスタデータ投入
flask seed-master

# 既存データがあっても強制投入
flask seed-master --force
```

### 3.1.2 YAMLファイルからの投入
```bash
# デフォルトYAMLから投入
python scripts/seed_from_yaml.py

# 特定のYAMLファイルから投入
python scripts/seed_from_yaml.py data/production_master.yml
```

### 3.1.3 Pythonスクリプトでの投入
```bash
python scripts/seed_master_data.py
```

### 3.1.4 マスタデータの構成
投入されるマスタデータは以下の通りです：

#### ロール（Roles）
- `admin` (ID: 1) - 管理者
- `manager` (ID: 2) - マネージャー  
- `member` (ID: 3) - メンバー
- `guest` (ID: 4) - ゲスト

#### 権限（Permissions）
- `admin:photo-settings` - 写真設定管理
- `admin:job-settings` - ジョブ設定管理
- `user:manage` - ユーザー管理
- `album:create` - アルバム作成
- `album:edit` - アルバム編集
- `album:view` - アルバム閲覧
- `media:view` - メディア閲覧
- `media:tag-manage` - メディアのタグ管理
- `permission:manage` - 権限管理
- `role:manage` - ロール管理
- `system:manage` - システム管理
- `wiki:admin` - Wiki管理
- `wiki:read` - Wiki読み取り
- `wiki:write` - Wiki書き込み

#### デフォルトユーザー
- Email: `admin@example.com`
- Password: `admin@example.com` (初回ログイン後に変更してください)
- Role: `admin`

### 3.1.5 環境別マスタデータ管理
本番環境と開発環境で異なるマスタデータを使用する場合：

```bash
# 開発環境用
python scripts/seed_from_yaml.py data/master_data.yml

# 本番環境用
python scripts/seed_from_yaml.py data/production_master.yml
```

`data/master_data.yml`ファイルを編集することで、マスタデータをカスタマイズできます。

## 4. Dockerデプロイ（本番環境推奨）

### 4.1 Dockerを使った簡単デプロイ

PhotoNestは本番環境向けにDockerコンテナでのデプロイをサポートしています。

#### 4.1.1 前提条件
- Docker 20.10以上
- Docker Compose v2以上

#### 4.1.2 リリースパッケージの準備
```bash
# リリースパッケージを作成
./create-release.sh

# パッケージを本番サーバーに転送
scp photonest-*.tar.gz production-server:/opt/

# サーバー上で展開
ssh production-server
cd /opt/
tar -xzf photonest-*.tar.gz
cd release-*/
```

#### 4.1.3 環境変数の設定
```bash
# 本番環境用の環境変数をコピー
cp .env.production .env

# 重要: セキュリティキーとパスワードを変更
nano .env
```

**必須変更項目:**
- `SECRET_KEY`: 強力なランダム文字列
- `AES_KEY`: 32バイトのランダムキー
- `DB_ROOT_PASSWORD`: MariaDBのrootパスワード
- `DB_PASSWORD`: アプリケーション用DBパスワード
- `GOOGLE_CLIENT_ID`: Google OAuth設定
- `GOOGLE_CLIENT_SECRET`: Google OAuth設定

#### 4.1.4 Dockerイメージのビルドと起動
```bash
# イメージをビルド
./build-release.sh latest

# 全サービスを起動（Web, Celery, DB, Redis）
docker-compose up -d

# ログを確認
docker-compose logs -f web worker beat
```

#### 4.1.5 動作確認
```bash
# ヘルスチェック
curl http://localhost:5000/api/health

# Celeryの状態確認
./check-celery.sh

# 全サービスの状態確認
docker-compose ps
```

### 4.2 Docker個別サービス管理

#### 4.2.1 サービス別起動・停止
```bash
# Webサーバーのみ起動
docker-compose up -d web

# Celeryワーカーのみ起動
docker-compose up -d worker

# Celeryスケジューラのみ起動
docker-compose up -d beat

# データベースとRedisのみ起動
docker-compose up -d db redis

# 特定サービスの停止
docker-compose stop worker

# 全サービス停止
docker-compose down
```

#### 4.2.2 ログとモニタリング
```bash
# リアルタイムログ表示
docker-compose logs -f web worker beat

# 最新100行のログ表示
docker-compose logs --tail=100 web

# Celeryタスクの監視
docker-compose exec worker celery -A cli.src.celery.tasks inspect active
docker-compose exec worker celery -A cli.src.celery.tasks inspect stats
```

### 4.3 Docker環境での保守作業

#### 4.3.1 データベースマイグレーション
```bash
# コンテナ内でマイグレーション実行
docker-compose exec web flask db upgrade

# マスタデータの投入
docker-compose exec web flask seed-master
```

#### 4.3.2 バックアップとリストア
```bash
# データベースバックアップ
docker-compose exec db mysqldump -u root -p photonest > backup_$(date +%Y%m%d).sql

# メディアファイルバックアップ
docker run --rm -v photonest_media_data:/data -v $(pwd):/backup alpine tar czf /backup/media_backup_$(date +%Y%m%d).tar.gz /data

# データベースリストア
docker-compose exec -T db mysql -u root -p photonest < backup_20240830.sql
```

#### 4.3.3 アップデート手順
```bash
# 新しいリリースパッケージで更新
./create-release.sh v2.0.0
docker-compose down
./build-release.sh v2.0.0
docker-compose up -d

# データベースマイグレーション（必要に応じて）
docker-compose exec web flask db upgrade
```

### 4.4 Dockerトラブルシューティング

#### 4.4.1 一般的な問題
```bash
# コンテナの強制再起動
docker-compose restart web worker beat

# イメージの再ビルド
docker-compose build --no-cache web

# ボリュームの確認
docker volume ls
docker volume inspect photonest_mariadb_data

# ネットワークの確認
docker network ls
docker-compose exec web ping db
docker-compose exec web ping redis
```

#### 4.4.2 Celeryの問題診断
```bash
# Celeryワーカーのデバッグ情報
docker-compose exec worker celery -A cli.src.celery.tasks inspect stats
docker-compose exec worker celery -A cli.src.celery.tasks inspect registered

# Redisの接続確認
docker-compose exec redis redis-cli ping
docker-compose exec worker python -c "import redis; r=redis.Redis(host='redis', port=6379); print(r.ping())"

# タスクキューの確認
docker-compose exec redis redis-cli llen celery
```

## 5. アプリケーション起動手順（開発環境）

### 5.1 開発サーバーの起動
```bash
# 仮想環境を有効化
source .venv/bin/activate

# Flaskアプリケーションを起動
python main.py
```
デフォルトで `http://localhost:5000` でアクセス可能です。

### 5.2 Celeryワーカーの起動（重要）

PhotoNestのバックグラウンド処理（メディア変換、サムネイル生成、Google Photos同期など）にはCeleryワーカーが必須です。

#### 5.2.1 基本的な起動方法
```bash
# 仮想環境を有効化
source .venv/bin/activate

# Celeryワーカーを起動
celery -A cli.src.celery.tasks worker --loglevel=info --concurrency=2

# より詳細なログを見たい場合
celery -A cli.src.celery.tasks worker --loglevel=debug

# バックグラウンドで実行する場合
nohup celery -A cli.src.celery.tasks worker --loglevel=info --concurrency=2 &
```

#### 5.2.2 利用可能なCeleryタスク
PhotoNestで使用可能な主要なタスク：

- **メディア処理**
  - `transcode_worker()` - 動画のH.264/AAC変換
  - `thumbs_generate()` - サムネイル生成（256px/1024px/2048px）
  
- **インポート処理**
  - `picker_import_item()` - フォトピッカーからのアイテムインポート
  - `local_import_task()` - ローカルファイルのインポート
  - `picker_import_watchdog()` - ファイル監視とインポート

- **セッション管理**
  - `cleanup_stale_sessions()` - 古いセッションのクリーンアップ
  - `force_cleanup_all_processing_sessions()` - 処理中セッションの強制クリーンアップ

#### 5.2.3 Celeryワーカーの監視
```bash
# ワーカーの状態確認
celery -A cli.src.celery.tasks inspect stats

# アクティブなタスク確認
celery -A cli.src.celery.tasks inspect active

# 登録されたタスク一覧
celery -A cli.src.celery.tasks inspect registered

# キューの状態確認
celery -A cli.src.celery.tasks inspect reserved
```

### 5.3 Celeryスケジューラの起動（定期実行タスク用）

定期実行タスク（セッションクリーンアップなど）のためのスケジューラです。

```bash
# Celeryビートスケジューラを起動
celery -A cli.src.celery.tasks beat --loglevel=info

# バックグラウンドで実行する場合
nohup celery -A cli.src.celery.tasks beat --loglevel=info &
```

### 5.4 開発環境でのCeleryデバッグ

#### 5.4.1 タスクの手動実行
```python
# Pythonコンソールまたはスクリプトで
from cli.src.celery.tasks import app as celery_app

# タスクの非同期実行
result = celery_app.send_task('core.tasks.thumbs_generate.thumbs_generate', 
                             args=[media_item_id])
print(f"タスクID: {result.id}")

# タスクの結果確認
print(f"状態: {result.status}")
print(f"結果: {result.result}")
```

#### 5.4.2 Celeryの設定確認
```bash
# Celery設定の表示
celery -A cli.src.celery.tasks inspect conf

# ブローカー（Redis）の接続確認
redis-cli ping

# キューの内容確認
redis-cli llen celery
```

#### 5.4.3 データベースに保存されたタスク一覧
Celeryタスクの永続化テーブルに記録された内容を確認するには、次のスクリプトを使用します。

```bash
# 直近のタスク一覧を表形式で確認
python -m cli.src.celery.inspect_tasks

# 実行中・待機中タスクのみを抽出
python -m cli.src.celery.inspect_tasks --pending

# JSON形式で全件取得（監視ツール連携など）
python -m cli.src.celery.inspect_tasks --json --limit 0
```

`--include-payload` や `--include-result` を付けると、レコードに保存された詳細JSONも出力されます。

### 5.5 Redis の起動確認（開発環境）

CeleryのブローカーとしてRedisが必要です。

#### 5.5.1 Redis接続確認
```bash
# Redisが動作しているか確認
redis-cli ping
# "PONG" が返ってくればOK

# Redis設定確認
redis-cli config get "*"

# Celeryキューの状態確認
redis-cli llen celery
redis-cli llen celery.task.default
```

#### 5.5.2 Redis起動方法
```bash
# システムサービスとして起動
sudo systemctl start redis-server
sudo systemctl enable redis-server

# Dockerで起動（推奨）
docker run -d -p 6379:6379 --name redis-dev redis:7-alpine

# 手動起動
redis-server
```

#### 5.5.3 Redis設定の最適化
開発環境用の`redis.conf`設定例：
```conf
# メモリ使用量の制限
maxmemory 256mb
maxmemory-policy allkeys-lru

# パーシステンス設定
save 900 1
save 300 10
save 60 10000

# ログレベル
loglevel notice
```

### 5.6 完全な開発環境起動手順

すべてのサービスを順序立てて起動する手順：

```bash
# 1. 仮想環境を有効化
source .venv/bin/activate

# 2. Redisを起動（Docker使用）
docker run -d -p 6379:6379 --name redis-dev redis:7-alpine

# 3. Redisの接続確認
redis-cli ping

# 4. データベースマイグレーション（必要時）
flask db upgrade

# 5. マスタデータ投入（初回のみ）
flask seed-master

# 6. Celeryワーカーを起動（別ターミナル）
celery -A cli.src.celery.tasks worker --loglevel=info --concurrency=2

# 7. Celeryスケジューラを起動（別ターミナル、必要時）
celery -A cli.src.celery.tasks beat --loglevel=info

# 8. Flaskアプリケーションを起動
python main.py
```

### 5.7 開発時のCeleryテスト方法

#### 5.7.1 提供されたテストスクリプトの使用
```bash
# Celeryの動作確認
./check-celery.sh

# Celeryタスクのテスト実行
./test-celery.sh
```

#### 5.7.2 手動でのタスクテスト
```python
# Pythonコンソールで実行
from webapp import create_app
from cli.src.celery.tasks import app as celery_app

app = create_app()
with app.app_context():
    # サムネイル生成タスクの例
    result = celery_app.send_task('core.tasks.thumbs_generate.thumbs_generate', 
                                 args=[1])  # media_item_id = 1
    print(f"タスクID: {result.id}")
    
    # 結果の確認（非同期なので即座には完了しない）
    import time
    time.sleep(5)
    print(f"状態: {result.status}")
    print(f"結果: {result.result}")
```

## 5. プロジェクト構成とアーキテクチャ

### 5.1 ディレクトリ構成
```
PhotoNest/
├── webapp/           # Webアプリケーション層
│   ├── api/         # REST API エンドポイント
│   ├── auth/        # 認証機能
│   ├── admin/       # 管理機能
│   ├── photo-view/  # 写真表示機能
│   └── templates/   # HTMLテンプレート
├── domain/          # ドメイン層（DDD）
├── application/     # アプリケーションサービス層（DDD）
├── infrastructure/  # インフラストラクチャ層（DDD）
├── core/           # コア機能（DB、暗号化、タスク）
├── cli/            # Celery設定とタスク定義
├── migrations/     # データベースマイグレーション
└── tests/         # テストコード
```

### 5.2 主要機能
- **ローカルインポート**: ローカルディレクトリから写真・動画をインポート
- **Google Photos同期**: Google PhotosのOAuth認証とコンテンツ同期
- **動画変換**: FFmpegによるH.264/AAC MP4変換（1080p、CRF20）
- **サムネイル生成**: 256px/1024px/2048pxの多段階サムネイル
- **セッション管理**: インポート処理の進行状況管理
- **ロールベース認証**: Permission モデルによる権限管理

## 6. 環境変数と設定
`.env.example` をコピーして必要な値を設定します。
```bash
cp .env.example .env
# エディタで .env を編集
```

### 6.1 主要設定項目
```bash
# Flask基本設定
SECRET_KEY=your-secret-key-here
FLASK_ENV=development

# データベース接続（MariaDB）
DATABASE_URI=mysql+pymysql://username:password@localhost/photonest

# Redis接続（Celery用）
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

# Google OAuth（Google Photos同期用）
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret

# OAuth トークン暗号化用鍵（AES-256-GCM）
OAUTH_TOKEN_KEY=base64:your-32-byte-base64-encoded-key
# または
OAUTH_TOKEN_KEY_FILE=/path/to/key/file

# メディアストレージパス
MEDIA_STORAGE_PATH=/path/to/media/storage
LOCAL_IMPORT_PATH=/path/to/local/import/directory
```

### 6.2 Google OAuth設定

#### 開発環境
1. Google Cloud Console でプロジェクトを作成
2. OAuth 2.0クライアントIDを作成
3. 認証済みリダイレクトURIに `http://localhost:5000/auth/google/callback` を追加
4. `.env` にクライアントIDとシークレットを設定

#### 本番環境
1. 本番ドメインでリダイレクトURIを追加（例：`https://yourdomain.com/auth/google/callback`）
2. `.env` に `PREFERRED_URL_SCHEME=https` を設定
3. リバースプロキシ（nginx等）で適切な `X-Forwarded-Proto` ヘッダーを設定

##### nginx設定例
```nginx
server {
    listen 443 ssl;
    server_name n.nolumia.com;
    
    # SSL設定
    ssl_certificate /path/to/ssl/cert.pem;
    ssl_certificate_key /path/to/ssl/private.key;
    
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;  # 重要: HTTPSスキームを渡す
        proxy_set_header X-Forwarded-Host $host;
    }
}
```

**重要**: `X-Forwarded-Proto $scheme` の設定がないと、FlaskアプリケーションはHTTPSリクエストを認識できません。

## 7. データベースマイグレーション
Alembicを使用してデータベーススキーマを管理します。

### 7.1 初回セットアップ
```bash
# マイグレーションディレクトリの初期化（既存の場合は不要）
flask db init

# 初回マイグレーション適用
flask db upgrade
```

### 7.2 モデル変更時の手順
1. `core/models/` のモデルファイルを変更
2. マイグレーションファイルを生成
   ```bash
   flask db migrate -m "変更内容の説明"
   ```
3. 生成されたマイグレーションファイルを確認・編集
4. マイグレーションを適用
   ```bash
   flask db upgrade
   ```

### 7.3 マイグレーション管理コマンド
```bash
# 現在のマイグレーション状態確認
flask db current

# マイグレーション履歴表示
flask db history

# 特定バージョンに戻す
flask db downgrade <revision>

# 強制的にヘッドに設定（緊急時のみ）
flask db stamp head
```

## 8. Celeryバックグラウンドジョブ

### 8.1 重要な注意事項
**正しいCeleryアプリケーション**: `cli.src.celery.tasks` を使用してください。
`cli.src.celery.celery_app` ではAPIからのタスク呼び出しが失敗します。

### 8.2 ワーカーの起動
```bash
# 仮想環境を有効化
source .venv/bin/activate

# 正しいワーカー起動コマンド
celery -A cli.src.celery.tasks worker --loglevel=info --concurrency=2

# バックグラウンド実行
nohup celery -A cli.src.celery.tasks worker --loglevel=info --concurrency=2 &

# プロセス確認
ps aux | grep celery
```

### 8.3 スケジューラの起動（定期実行タスク + 自動リカバリ）
```bash
# ビートスケジューラ（定期実行タスク）
celery -A cli.src.celery.tasks beat --loglevel=info

# バックグラウンド実行
nohup celery -A cli.src.celery.tasks beat --loglevel=info &
```

**スケジューラが実行する定期タスク**:
- `picker_import.watchdog`: Photo picker監視（1分毎）
- `session_recovery.cleanup_stale_sessions`: 厳密なセッション自動リカバリ（5分毎）

**厳密な自動リカバリ機能**: 
以下の条件をすべて満たすセッションのみをエラー状態に変更します：
1. ステータスが「processing」
2. 最終更新から一定時間経過（ローカルインポート：2時間、その他：1時間）
3. Celeryワーカーで実際のタスクが実行されていない

これにより、動画変換などの長時間処理が誤ってタイムアウトすることを防ぎ、真に停止したセッションのみを適切にクリーンアップします。

### 8.4 利用可能なタスク
- `local_import.run`: ローカルファイルインポート処理
- `picker_import.item`: 個別アイテムインポート
- `picker_import.watchdog`: Photo picker監視タスク（1分毎実行）
- `session_recovery.cleanup_stale_sessions`: 厳密なセッション自動リカバリ（5分毎実行）
- `session_recovery.force_cleanup_all`: 全セッション強制クリーンアップ（緊急時用）
- `session_recovery.status_report`: セッション状況詳細レポート（デバッグ用）
- `transcode_worker`: 動画変換処理（H.264/AAC MP4）
- `thumbs_generate`: サムネイル生成（256/1024/2048px）
- `cli.src.celery.tasks.download_file`: ファイルダウンロード
- `cli.src.celery.tasks.dummy_long_task`: テスト用長時間タスク

### 8.5 タスク監視とデバッグ
```bash
# アクティブなタスク確認
python -c "
from cli.src.celery.celery_app import celery
i = celery.control.inspect()
print('Active:', i.active())
print('Scheduled:', i.scheduled())
"

# ワーカー停止
pkill -f celery

# Redis内のタスクキュー確認
redis-cli
> LLEN celery
> LRANGE celery 0 -1
```

## 9. 多言語対応（i18n）
Babel を使用した国際化機能です。

### 9.1 翻訳ファイルのコンパイル
```bash
# 翻訳ファイルをコンパイル
pybabel compile -d webapp/translations -f
```

### 9.2 新しい翻訳の追加
```bash
# メッセージ抽出
pybabel extract -F babel.cfg -k _l -o messages.pot .

# 新しい言語追加
pybabel init -i messages.pot -d webapp/translations -l ja

# 既存翻訳の更新
pybabel update -i messages.pot -d webapp/translations
```

## 10. OAuth トークン暗号化
Google アカウントの OAuth トークンは AES-256-GCM で暗号化して保存されます。

### 10.1 暗号化鍵の生成
```python
import os
import base64

# 32バイトのランダムキーを生成
key = os.urandom(32)
key_b64 = base64.b64encode(key).decode()
print(f"OAUTH_TOKEN_KEY=base64:{key_b64}")
```

### 10.2 暗号化の仕組み
- トークンは `google_account.oauth_token_json` フィールドに暗号化保存
- 復号化は `core/crypto.py` の `decrypt_oauth_token()` で実行
- 鍵は環境変数 `OAUTH_TOKEN_KEY` または `OAUTH_TOKEN_KEY_FILE` で指定

## 11. テストの実行
pytest を使用した包括的なテストスイートが用意されています。

### 11.1 基本的なテスト実行
```bash
# 仮想環境を有効化
source .venv/bin/activate

# 全テスト実行
pytest

# 詳細な出力
pytest -v

# 特定のテストファイル実行
pytest tests/test_local_import.py -v
```

### 11.2 カテゴリ別テスト実行
```bash
# Celery関連テスト
pytest tests/test_celery_*.py -v

# API関連テスト  
pytest tests/test_*_api.py -v

# メディア処理テスト
pytest tests/test_transcode.py tests/test_thumbs_generate.py -v

# 暗号化テスト
pytest tests/test_crypto.py -v
```

### 11.3 テストカバレッジ
```bash
# カバレッジ付きでテスト実行
pytest --cov=webapp --cov=core --cov=domain --cov=application --cov=infrastructure

# HTMLレポート生成
pytest --cov=webapp --cov=core --cov-report=html
```

### 11.4 主要テストコンポーネント
- **Celery統合テスト**: アプリケーションコンテキスト、データベースアクセス
- **API テスト**: REST エンドポイント、認証、ペジネーション
- **メディア処理テスト**: 動画変換、サムネイル生成、ファイルインポート
- **セキュリティテスト**: OAuth トークン暗号化、権限管理

## 12. トラブルシューティング

### 12.1 Celery関連の問題

#### 「Celery処理待ち中...」が消えない
```bash
# 1. セッション状況の詳細レポートを確認
python -c "
from cli.src.celery.tasks import session_status_report_task
result = session_status_report_task.delay()
print(f'Report task ID: {result.id}')
print('レポート結果は、タスク完了後にCeleryログまたは結果バックエンドで確認できます')
"

# 2. スケジューラが動作しているか確認
ps aux | grep "celery.*beat"

# 3. スケジューラが停止している場合は起動
celery -A cli.src.celery.tasks beat --loglevel=info &

# 4. 手動でセッションリカバリを実行
python -c "
from cli.src.celery.tasks import cleanup_stale_sessions_task
result = cleanup_stale_sessions_task.delay()
print(f'Cleanup task ID: {result.id}')
"

# 5. 緊急時: 全セッションを強制クリーンアップ（注意: 実行中タスクも停止）
python -c "
from cli.src.celery.tasks import force_cleanup_all_sessions_task  
result = force_cleanup_all_sessions_task.delay()
print(f'Force cleanup task ID: {result.id}')
"

# 6. ワーカーとスケジューラの状況確認
ps aux | grep celery
```

**注意**: 厳密なリカバリシステムにより、通常は実行中の長時間タスク（動画変換など）が誤ってタイムアウトすることはありません。ローカルインポートは2時間、その他は1時間のタイムアウトが設定されており、Celeryで実際に実行中のタスクは保護されます。

### 12.2 マスタデータ関連の問題

#### ログインできない（初期ユーザーが存在しない）
```bash
# マスタデータが投入されているか確認
python -c "
from webapp import create_app
from core.models.user import User, Role
app = create_app()
with app.app_context():
    user_count = User.query.count()
    role_count = Role.query.count()
    print(f'Users: {user_count}, Roles: {role_count}')
    if user_count == 0:
        print('マスタデータが投入されていません')
"

# マスタデータを投入
flask seed-master
```

#### 権限エラーが発生する
```bash
# ロール・権限の状況確認
python -c "
from webapp import create_app
from core.models.user import User, Role, Permission
app = create_app()
with app.app_context():
    admin_user = User.query.filter_by(email='admin@example.com').first()
    if admin_user:
        print(f'Admin roles: {[r.name for r in admin_user.roles]}')
        for role in admin_user.roles:
            print(f'Role {role.name} permissions: {[p.code for p in role.permissions]}')
    else:
        print('Admin user not found')
"

# 権限が不足している場合は再投入
flask seed-master --force
```

#### マスタデータの初期化
```bash
# 全マスタデータを削除して再投入
python -c "
from webapp import create_app
from core.models.user import User, Role, Permission
from core.db import db
app = create_app()
with app.app_context():
    # 注意: 全ユーザー・ロール・権限が削除されます
    db.session.query(User).delete()
    db.session.query(Role).delete()
    db.session.query(Permission).delete()
    db.session.commit()
    print('All master data deleted')
"

flask seed-master
```

### 12.3 Celery関連の問題
```bash
# 1. スケジューラが動作しているか確認
ps aux | grep "celery.*beat"

# 2. スケジューラが停止している場合は起動
celery -A cli.src.celery.tasks beat --loglevel=info &

# 3. 手動でセッションリカバリを実行
python -c "
from cli.src.celery.tasks import cleanup_stale_sessions_task
result = cleanup_stale_sessions_task.delay()
print(f'Task ID: {result.id}')
"

# 4. 緊急時: 全セッションを強制クリーンアップ
python -c "
from cli.src.celery.tasks import force_cleanup_all_sessions_task  
result = force_cleanup_all_sessions_task.delay()
print(f'Force cleanup task ID: {result.id}')
"

# 5. ワーカーとスケジューラの状況確認
ps aux | grep celery
```

**注意**: 通常は5分毎の自動リカバリで解決されるため、手動でのクリーンアップは不要です。

#### "Working outside of application context" エラー
```bash
# Celeryアプリケーション名を確認
# 正しい: cli.src.celery.tasks
# 間違い: cli.src.celery.celery_app

# 正しいワーカーを起動
celery -A cli.src.celery.tasks worker --loglevel=info
```

### 12.2 データベース関連の問題

#### マイグレーションエラー
```bash
# 現在の状態確認
flask db current

# 強制的にヘッドに設定（注意: データ損失の可能性）
flask db stamp head

# マイグレーション再実行
flask db upgrade
```

#### 接続エラー
```bash
# MariaDBサービス確認
sudo systemctl status mariadb
sudo systemctl start mariadb

# 接続テスト
mysql -u username -p database_name
```

### 12.3 Redis関連の問題

#### Redis接続エラー
```bash
# Redis状態確認
redis-cli ping

# Redisサービス開始
sudo systemctl start redis-server

# Docker使用の場合
docker run -d -p 6379:6379 redis:alpine

# キューの確認
redis-cli
> LLEN celery
> FLUSHALL  # 全キューをクリア（注意）
```

### 12.4 Google OAuth関連の問題

#### トークン暗号化エラー
```bash
# 暗号化鍵の確認
echo $OAUTH_TOKEN_KEY

# 新しい鍵を生成
python -c "
import os, base64
key = base64.b64encode(os.urandom(32)).decode()
print(f'OAUTH_TOKEN_KEY=base64:{key}')
"
```

#### OAuth設定エラー
1. Google Cloud Console で設定確認
2. リダイレクトURI: `http://localhost:5000/auth/google/callback`
3. スコープ: `https://www.googleapis.com/auth/photoslibrary.readonly`

### 12.5 メディア処理関連の問題

#### FFmpeg不足
```bash
# Ubuntu/Debian
sudo apt update && sudo apt install ffmpeg

# CentOS/RHEL
sudo yum install epel-release
sudo yum install ffmpeg

# macOS
brew install ffmpeg
```

#### ストレージパス権限エラー
```bash
# メディアディレクトリの権限確認
ls -la /path/to/media/storage

# 権限修正
sudo chown -R username:username /path/to/media/storage
chmod -R 755 /path/to/media/storage
```

### 12.6 パフォーマンス問題

#### ログ監視
```bash
# Celeryワーカーログ
tail -f /var/log/celery/worker.log

# Flaskアプリログ
tail -f logs/app.log

# システムリソース確認
htop
df -h
```

## 13. 本番環境デプロイ

### 13.1 本番環境設定
```bash
# 本番環境用の環境変数
FLASK_ENV=production
SECRET_KEY=strong-production-secret-key

# データベース接続（本番用）
DATABASE_URI=mysql+pymysql://user:pass@prod-db-host/photonest

# セキュリティ設定
SESSION_COOKIE_SECURE=True
SESSION_COOKIE_HTTPONLY=True
```

### 13.2 WSGI設定（Gunicorn）
```bash
# Gunicornでの起動
gunicorn --bind 0.0.0.0:8000 --workers 4 wsgi:app
```

## 14. API仕様概要

### 14.1 主要エンドポイント
- `GET /api/picker/sessions` - セッション一覧
- `POST /api/local-import` - ローカルインポート開始
- `POST /api/media/{id}/thumb-url` - サムネイルURL取得
- `POST /api/media/{id}/playback-url` - 再生URL取得

## 14.2 マスタデータ管理コマンドリファレンス

### 14.2.1 Flaskコマンド
```bash
# 基本的なマスタデータ投入
flask seed-master

# 既存データを無視して強制投入
flask seed-master --force
```

### 14.2.2 YAMLベースの投入
```bash
# デフォルトYAMLファイル（data/master_data.yml）から投入
python scripts/seed_from_yaml.py

# 指定したYAMLファイルから投入
python scripts/seed_from_yaml.py path/to/custom_master.yml
```

### 14.2.3 Pythonスクリプト
```bash
# 単純なPythonスクリプトでの投入
python scripts/seed_master_data.py
```

### 14.2.4 YAMLファイル形式例
```yaml
# data/master_data.yml
roles:
  - id: 1
    name: admin
  - id: 2
    name: manager

permissions:
  - id: 1
    code: admin:photo-settings
  - id: 2
    code: user:manage

role_permissions:
  - role_id: 1
    permissions: [1, 2]

default_users:
  - id: 1
    email: admin@example.com
    password_hash: "scrypt:..."
    roles: [1]
    is_active: true
```

## 15. クイックスタートチェックリスト

- [ ] 仮想環境作成・有効化
- [ ] 依存関係インストール（`requirements.txt`）
- [ ] `.env` ファイル設定
- [ ] MariaDB起動・接続確認
- [ ] Redis起動・接続確認
- [ ] データベースマイグレーション実行（`flask db upgrade`）
- [ ] **マスタデータ投入**（`flask seed-master`）
- [ ] **正しいCeleryワーカー起動**（`cli.src.celery.tasks`）
- [ ] Flaskアプリケーション起動
- [ ] ブラウザで `http://localhost:5000` アクセス確認
- [ ] 初期ユーザーでログイン確認（admin@example.com / admin@example.com）
- [ ] ローカルインポート機能テスト

**重要**: Celeryワーカーは必ず `celery -A cli.src.celery.tasks worker` で起動してください。
