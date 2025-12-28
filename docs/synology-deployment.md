# nolumia Synology NAS デプロイガイド

## 概要
このガイドでは、SynologyのContainer Manager（旧Docker）を使用してnolumiaを本番環境にデプロイし、外部からアクセス可能にする手順を説明します。

## 前提条件

## システム要件

### Synology NAS最小要件
- **モデル**: DS220+以上（Intel Celeron J4025 2.0GHz以上推奨）
- **RAM**: 2GB以上（4GB以上推奨）
- **ストレージ**: 20GB以上の空き容量
- **DSM**: 7.0以上
- **Container Manager**: インストール済み

### 外部データベース要件
nolumiaは外部のMariaDB/MySQLデータベースを利用します：

#### オプション1: Synology MariaDB パッケージ
- **パッケージセンター** > **MariaDB 10** をインストール
- **推奨設定**: 
  - データベース名: `photonest`
  - ユーザー名: `photonest_user`
  - 文字セット: `utf8mb4`

#### オプション2: 別サーバーのMySQL/MariaDB
- **バージョン**: MySQL 8.0+ または MariaDB 10.11+
- **接続要件**: Synology NASからアクセス可能
- **権限**: データベース作成・操作権限

### 必要な知識
- SynologyのDSM操作
- 基本的なDocker概念
- ネットワーク設定の基礎知識

## 1. セットアップ手順

### Step 1: 事前準備

#### 1.1 外部データベースの準備

**Synology MariaDBパッケージを使用する場合:**
```bash
# パッケージセンターからMariaDB 10をインストール後
# MariaDB管理画面で以下を実行:

# 1. データベース作成
CREATE DATABASE photonest CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

# 2. ユーザー作成
CREATE USER '<photonest_user>'@'%' IDENTIFIED BY '<your-strong-password>';

# 3. 権限付与
GRANT ALL PRIVILEGES ON photonest.* TO '<photonest_user>'@'%';
FLUSH PRIVILEGES;
```

**外部MySQL/MariaDBサーバーを使用する場合:**
```bash
# 外部サーバーで以下を実行（管理者権限）
mysql -u root -p

CREATE DATABASE photonest CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER '<photonest_user>'@'%' IDENTIFIED BY '<your-strong-password>';
GRANT ALL PRIVILEGES ON photonest.* TO '<photonest_user>'@'%';
FLUSH PRIVILEGES;

# ファイアウォール設定（必要に応じて）
# ポート3306をSynology NASのIPアドレスに対して開放
```

#### 1.2 ストレージディレクトリ作成

### 1.1 Container Managerの有効化
1. DSMにログイン
2. パッケージセンターを開く
3. Container Managerを検索してインストール
4. Container Managerを起動

### 1.2 フォルダ構造の作成
DSMのFile Stationで以下のフォルダを作成：

```
/docker/photonest/
├── config/
├── data/
│   ├── media/
│   ├── thumbs/
│   ├── playback/
│   └── redis/
└── backups/
```

### 1.3 docker-compose.ymlとDockerイメージの準備
nolumiaのdocker-compose.ymlは外部データベース対応済みです。開発環境でDockerイメージをビルドしてSynologyにインポートします。

## 2. 環境設定ファイルの準備

### 2.1 .envファイルの作成
Synology上で`/volume1/docker/photonest/.env`ファイルを作成します。
`.env.example`をコピーして、**以下の項目のみ変更**してください：

```env
# 必ず変更が必要な項目
SECRET_KEY=<your-very-strong-secret-key-here-change-this-immediately>
JWT_SECRET_KEY=<your-jwt-secret-key-here>

# 外部データベース設定（Synology MariaDB または別サーバー）
DATABASE_URI=mysql+pymysql://<photonest_user>:<your-password>@<your-db-host>:3306/photonest

# Redis認証設定
REDIS_PASSWORD=<strong-redis-password-here>
REDIS_URL=redis://:<strong-redis-password-here>@photonest-redis:6379/0
CELERY_BROKER_URL=redis://:<strong-redis-password-here>@photonest-redis:6379/0
CELERY_RESULT_BACKEND=redis://:<strong-redis-password-here>@photonest-redis:6379/0

# Google OAuth設定（使用する場合のみ）
GOOGLE_CLIENT_ID=<your-google-client-id>
GOOGLE_CLIENT_SECRET=<your-google-client-secret>

# ダウンロードURL署名設定
MEDIA_DOWNLOAD_SIGNING_KEY=<your-download-signing-key-here>

# NASパス（Nginx X-Accel-Redirectを使う場合の例）
MEDIA_THUMBNAILS_DIRECTORY=/volume1/docker/photonest/data/thumbs
MEDIA_PLAYBACK_DIRECTORY=/volume1/docker/photonest/data/playback
MEDIA_THUMBNAILS_CONTAINER_DIRECTORY=/app/data/thumbs
MEDIA_PLAYBACK_CONTAINER_DIRECTORY=/app/data/playback
MEDIA_ACCEL_THUMBNAILS_LOCATION=/media/thumbs
MEDIA_ACCEL_PLAYBACK_LOCATION=/media/playback
MEDIA_ACCEL_REDIRECT_ENABLED=true  # デフォルトは false のため、X-Accel-Redirect を使う場合のみ true に設定
```

**注意**: その他の設定項目（TZ、PUID、PGID等）はデフォルト値のまま使用可能です。

X-Accel-Redirectを使用しない構成の場合は、`MEDIA_ACCEL_REDIRECT_ENABLED=false`を設定するか、
`MEDIA_ACCEL_THUMBNAILS_LOCATION`および`MEDIA_ACCEL_PLAYBACK_LOCATION`の値を空にしてください。
この設定により、Flaskアプリが直接ファイルを配信します。

### 2.2 docker-compose.ymlの設定確認
nolumiaのdocker-compose.ymlは外部データベース対応済みです：

- **外部データベース接続**: `.env`ファイルで設定
- **Redis認証**: パスワード保護されたRedis
- **ボリュームマウント**: Synologyの適切なパスに設定

設定例：
```env
# .env
DATABASE_URI=mysql+pymysql://<photonest_user>:<password>@<your-db-host>:3306/photonest
REDIS_PASSWORD=<strong-redis-password-here>
REDIS_URL=redis://:<strong-redis-password-here>@photonest-redis:6379/0
```

## 3. Container Managerでのデプロイ

### 3.1 Dockerイメージのビルドとデプロイ

開発環境でDockerイメージをビルドして、SynologyのContainer Managerにインポートします。

```bash
# 開発マシンでイメージをビルド
cd /path/to/photonest/project
docker build -t photonest:latest .

# イメージをtarファイルとして保存
docker save photonest:latest > photonest-latest.tar

# tarファイルをSynologyにアップロード（scp、File Station、USBなど）
scp photonest-latest.tar <admin>@<your-nas-ip>:/volume1/docker/

# Container Managerでインポート
# Container Manager > イメージ > 追加 > ファイルからインポート > photonest-latest.tar を選択
```

### 3.2 プロジェクトの作成
1. Container Managerで「プロジェクト」タブを選択
2. 「作成」をクリック
3. 設定：
   - **プロジェクト名**: `photonest`
   - **パス**: `/volume1/docker/photonest/`
   - **ソース**: 「既存のdocker-compose.ymlをアップロード」を選択
   - **ファイル**: `/volume1/docker/photonest/docker-compose.yml`を選択

### 3.3 サービスの起動
1. プロジェクト一覧で「photonest」を選択
2. 「アクション」→「ビルドして起動」を選択
3. 起動順序を確認：
   - photonest-redis（Redis）
   - photonest-web（Webアプリ）
   - photonest-worker（Celeryワーカー）
   - photonest-beat（Celeryスケジューラ）

**注意**: 外部データベースを使用するため、データベース接続が正常に行えることを事前に確認してください。

## 4. ネットワーク設定とアクセス公開

### 4.1 ポート設定の確認
Container Managerで各コンテナのポートを確認：
- **photonest-web**: 5000:5000
- **photonest-redis**: 6379:6379（内部アクセスのみ）

**注意**: 外部データベースを使用するため、photonest-dbコンテナは存在しません。

### 4.2 DSMでのアクセス設定

#### 4.2.1 リバースプロキシの設定（推奨）
1. DSMの「コントロールパネル」→「アプリケーションポータル」を開く
2. 「リバースプロキシ」タブを選択
3. 「作成」をクリック
4. 設定：
   - **説明**: nolumia
   - **ソースプロトコル**: HTTPS
   - **ソースホスト名**: <your-nas-domain.synology.me>
   - **ソースポート**: 443
   - **デスティネーションプロトコル**: HTTP
   - **デスティネーションホスト名**: localhost
   - **デスティネーションポート**: 5000

#### 4.2.2 SSL証明書の設定
1. 「コントロールパネル」→「セキュリティ」→「証明書」
2. Let's Encryptで無料SSL証明書を取得
3. リバースプロキシで証明書を適用

### 4.3 外部アクセスの設定

#### 4.3.1 DDNS設定
1. 「コントロールパネル」→「外部アクセス」→「DDNS」
2. Synology DDNS またはカスタムDDNSを設定
3. ドメイン名を取得（例：<your-nas.synology.me>）

#### 4.3.2 ファイアウォール設定
1. 「コントロールパネル」→「セキュリティ」→「ファイアウォール」
2. ルールを作成：
   - **ポート**: 443（HTTPS）、80（HTTP）
   - **プロトコル**: TCP
   - **ソース**: すべて（または特定のIP範囲）

#### 4.3.3 ルーター設定
1. ルーターの管理画面にアクセス
2. ポートフォワーディング設定：
   - **外部ポート**: 443, 80
   - **内部IP**: SynologyのIPアドレス
   - **内部ポート**: 443, 80

## 5. 初期設定とデータベースセットアップ

### 5.1 データベースマイグレーション
Container Managerのターミナルで実行：

```bash
# photonest-webコンテナに接続
docker exec -it photonest-web bash

# データベースマイグレーション
flask db upgrade

# マスタデータ投入
flask seed-master

# 管理者ユーザー作成（必要に応じて）
flask create-admin
```

### 5.2 初回アクセスと動作確認
1. ブラウザで `https://<your-nas-domain.synology.me>` にアクセス
2. nolumiaのログイン画面が表示されることを確認
3. 管理者アカウントでログイン
4. 基本機能の動作確認

## 6. モニタリングと保守

### 6.1 Container Managerでの監視
1. 「コンテナ」タブで各サービスの状態確認
2. CPUとメモリ使用量の監視
3. ログの確認（特にエラーログ）

### 6.2 ログの管理
```bash
# 各コンテナのログ確認
docker logs photonest-web
docker logs photonest-worker
docker logs photonest-beat
docker logs photonest-redis

# 外部データベースのログは、データベースサーバーで直接確認
```

### 6.3 定期メンテナンス

#### 6.3.1 バックアップ設定
```bash
# データベースバックアップスクリプト
#!/bin/bash
SYSTEM_BACKUP_DIRECTORY="/volume1/docker/photonest/backups"
DATE=$(date +%Y%m%d_%H%M%S)

# 外部データベースのバックアップ（例：Synology MariaDBパッケージの場合）
# Synology MariaDBの場合：
mysqldump -h <your-db-host> -u <photonest_user> -p photonest > \
    ${SYSTEM_BACKUP_DIRECTORY}/db_backup_${DATE}.sql

# 別サーバーのMySQL/MariaDBの場合：
# mysqldump -h <your-external-db-server> -u <photonest_user> -p photonest > \
#     ${SYSTEM_BACKUP_DIRECTORY}/db_backup_${DATE}.sql

# メディアファイルバックアップ（必要に応じて）
tar -czf ${SYSTEM_BACKUP_DIRECTORY}/media_backup_${DATE}.tar.gz \
    /volume1/docker/photonest/data/

# 古いバックアップの削除（30日より古い）
find ${SYSTEM_BACKUP_DIRECTORY} -name "*.sql" -mtime +30 -delete
find ${SYSTEM_BACKUP_DIRECTORY} -name "*.tar.gz" -mtime +30 -delete
```

> **補足**: 旧環境変数名 `MEDIA_BACKUP_DIRECTORY` も互換のためにサポートされていますが、運用設定は `SYSTEM_BACKUP_DIRECTORY` に移行してください。

#### 6.3.2 アップデート手順
1. 新しいnolumiaリリースをダウンロード
2. イメージを再ビルド
3. Container Managerでプロジェクトを停止
4. 新しいイメージでプロジェクトを再起動
5. データベースマイグレーション実行

## 7. セキュリティ強化

### 7.1 アクセス制限
1. 特定IPからのみアクセス許可
2. VPN経由のアクセスのみ許可
3. 2段階認証の有効化

### 7.2 定期的なセキュリティ更新
1. DSMの定期更新
2. Container Managerの更新
3. nolumiaイメージの更新
4. 依存関係の脆弱性チェック

## 8. トラブルシューティング

### 8.1 よくある問題と解決方法

#### 問題1: コンテナが起動しない
```bash
# ログの確認
docker logs photonest-web

# 権限の確認
chmod -R 755 /volume1/docker/photonest/data/
chown -R 1026:100 /volume1/docker/photonest/data/
```

#### 問題2: データベース接続エラー
1. 外部データベースサーバーの状態確認
2. データベース認証情報の確認（.envファイル）
3. ネットワーク接続の確認（ファイアウォール、ポート設定）
4. DATABASE_URLの形式確認

#### 問題3: 外部アクセスできない
1. リバースプロキシ設定の確認
2. ファイアウォール設定の確認
3. DDNS設定の確認
4. ルーターのポートフォワーディング確認

### 8.2 パフォーマンスチューニング
1. SynologyのRAM増設
2. SSDキャッシュの有効化
3. Celeryワーカー数の調整
4. データベースの最適化

## 9. 付録

### 9.1 Synology Docker実行用スクリプト

#### start-photonest.sh
```bash
#!/bin/bash
cd /volume1/docker/photonest/
docker-compose up -d
echo "nolumia started successfully!"
echo "Access URL: https://<your-nas-domain.synology.me>"
```

#### stop-photonest.sh
```bash
#!/bin/bash
cd /volume1/docker/photonest/
docker-compose down
echo "nolumia stopped successfully!"
```

#### backup-photonest.sh
```bash
#!/bin/bash
SYSTEM_BACKUP_DIRECTORY="/volume1/docker/photonest/backups"
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p ${SYSTEM_BACKUP_DIRECTORY}

# 外部データベースバックアップ
# Synology MariaDBパッケージの場合
mysqldump -h localhost -u <photonest_user> -p photonest \
    --single-transaction --routines --triggers > \
    ${SYSTEM_BACKUP_DIRECTORY}/photonest_db_${DATE}.sql

# 別サーバーのデータベースの場合
# mysqldump -h <your-db-server> -u <photonest_user> -p photonest \
#     --single-transaction --routines --triggers > \
#     ${SYSTEM_BACKUP_DIRECTORY}/photonest_db_${DATE}.sql

# 設定ファイルバックアップ
cp /volume1/docker/photonest/.env ${SYSTEM_BACKUP_DIRECTORY}/env_${DATE}.backup

echo "Backup completed: ${SYSTEM_BACKUP_DIRECTORY}"
echo "Database: photonest_db_${DATE}.sql"
echo "Config: env_${DATE}.backup"
```

### 9.2 監視スクリプト

#### check-status.sh
```bash
#!/bin/bash
echo "=== nolumia Status Check ==="
echo "Date: $(date)"
echo ""

# コンテナ状態確認
echo "Container Status:"
docker ps --filter "name=photonest" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
echo ""

# ヘルスチェック
echo "Health Check:"
curl -s http://localhost:5000/api/health || echo "Health check failed"
echo ""

# ディスク使用量
echo "Disk Usage:"
du -sh /volume1/docker/photonest/data/*
echo ""

# メモリ使用量
echo "Memory Usage:"
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" \
    $(docker ps --filter "name=photonest" -q)
```

### 9.3 設定例

#### nginx.conf（外部リバースプロキシ使用時）
```nginx
upstream photonest {
    server <your-nas-ip>:5000;
}

server {
    listen 443 ssl http2;
    server_name <your-domain.com>;

    ssl_certificate <path/to/certificate.crt>;
    ssl_certificate_key <path/to/private.key>;

    location / {
        proxy_pass http://photonest;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket support (if needed)
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

このガイドに従って、Synologyでnolumiaを安全かつ効率的にデプロイしてください。
