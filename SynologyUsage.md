# PhotoNest Synology NAS デプロイガイド

## 概要
このガイドでは、SynologyのContainer Manager（旧Docker）を使用してPhotoNestを本番環境にデプロイし、外部からアクセス可能にする手順を説明します。

## 前提条件

## システム要件

### Synology NAS最小要件
- **モデル**: DS220+以上（Intel Celeron J4025 2.0GHz以上推奨）
- **RAM**: 2GB以上（4GB以上推奨）
- **ストレージ**: 20GB以上の空き容量
- **DSM**: 7.0以上
- **Container Manager**: インストール済み

### 外部データベース要件
PhotoNestは外部のMariaDB/MySQLデータベースを利用します：

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
CREATE USER 'photonest_user'@'%' IDENTIFIED BY 'your-strong-password';

# 3. 権限付与
GRANT ALL PRIVILEGES ON photonest.* TO 'photonest_user'@'%';
FLUSH PRIVILEGES;
```

**外部MySQL/MariaDBサーバーを使用する場合:**
```bash
# 外部サーバーで以下を実行（管理者権限）
mysql -u root -p

CREATE DATABASE photonest CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'photonest_user'@'%' IDENTIFIED BY 'your-strong-password';
GRANT ALL PRIVILEGES ON photonest.* TO 'photonest_user'@'%';
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
│   └── playback/
├── db/
└── redis/
```

### 1.3 リリースファイルの準備
1. PhotoNestのリリースパッケージをSynologyにアップロード
2. `/docker/photonest/`フォルダに展開
3. 必要ファイルを配置

```bash
# SynologyのSSH接続（有効化要）、またはFile Station経由で実行
cd /volume1/docker/photonest/
# リリースパッケージを展開
tar -xzf photonest-*.tar.gz
mv release-*/* ./
```

## 2. 環境設定ファイルの準備

### 2.1 .envファイルの作成
`/docker/photonest/config/.env`ファイルを作成：

```env
```env
# ===========================================
# PhotoNest Synology Production Environment
# ===========================================

# セキュリティキー（必ず変更してください）
SECRET_KEY=your-very-strong-secret-key-here-change-this-immediately
AES_KEY=your-32-byte-aes-encryption-key-change-this-now

# 外部データベース設定（Synology MariaDB/MySQL または別サーバー）
# 例: DATABASE_URL=mysql+pymysql://photonest_user:password@192.168.1.100:3306/photonest
DATABASE_URL=mysql+pymysql://photonest_user:your-password@your-db-host:3306/photonest

# Redis設定（認証付き）
REDIS_PASSWORD=strong-redis-password-here
REDIS_URL=redis://:strong-redis-password-here@photonest-redis:6379/0

# Celery設定（Redis認証対応）
CELERY_BROKER_URL=redis://:strong-redis-password-here@photonest-redis:6379/0
CELERY_RESULT_BACKEND=redis://:strong-redis-password-here@photonest-redis:6379/0

# Flask設定
FLASK_ENV=production
FLASK_DEBUG=False

# ログ設定
LOG_LEVEL=INFO

# メディアストレージパス
MEDIA_PATH=/app/data/media
THUMB_PATH=/app/data/thumbs
PLAYBACK_PATH=/app/data/playback

# Google OAuth設定（オプション）
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret

# セキュリティ設定
SESSION_COOKIE_SECURE=True
SESSION_COOKIE_HTTPONLY=True
REMEMBER_COOKIE_SECURE=True
REMEMBER_COOKIE_HTTPONLY=True

# Synology固有設定
TZ=Asia/Tokyo
PUID=1026
PGID=100
```
```

### 2.2 docker-compose.synology.ymlの作成
Synology専用のdocker-composeファイルを作成（外部データベース・Redis認証対応）：

```yaml
version: '3.8'

services:
  photonest-web:
    image: photonest:latest
    container_name: photonest-web
    restart: unless-stopped
    ports:
      - "5000:5000"
    environment:
      - TZ=Asia/Tokyo
      - PUID=1026
      - PGID=100
    env_file:
      - /volume1/docker/photonest/config/.env
    volumes:
      - /volume1/docker/photonest/data/media:/app/data/media
      - /volume1/docker/photonest/data/thumbs:/app/data/thumbs
      - /volume1/docker/photonest/data/playback:/app/data/playback
    depends_on:
      - photonest-redis
    networks:
      - photonest-network
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:5000/api/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s

  photonest-worker:
    image: photonest:latest
    container_name: photonest-worker
    restart: unless-stopped
    command: celery -A cli.src.celery.tasks worker --loglevel=info --concurrency=2
    environment:
      - TZ=Asia/Tokyo
      - PUID=1026
      - PGID=100
    env_file:
      - /volume1/docker/photonest/config/.env
    volumes:
      - /volume1/docker/photonest/data/media:/app/data/media
      - /volume1/docker/photonest/data/thumbs:/app/data/thumbs
      - /volume1/docker/photonest/data/playback:/app/data/playback
    depends_on:
      - photonest-redis
    networks:
      - photonest-network

  photonest-beat:
    image: photonest:latest
    container_name: photonest-beat
    restart: unless-stopped
    command: celery -A cli.src.celery.tasks beat --loglevel=info
    environment:
      - TZ=Asia/Tokyo
      - PUID=1026
      - PGID=100
    env_file:
      - /volume1/docker/photonest/config/.env
    depends_on:
      - photonest-redis
    networks:
      - photonest-network

  photonest-redis:
    image: redis:7-alpine
    container_name: photonest-redis
    restart: unless-stopped
    ports:
      - "6379:6379"
    command: redis-server --requirepass ${REDIS_PASSWORD} --appendonly yes
    environment:
      - TZ=Asia/Tokyo
    volumes:
      - /volume1/docker/photonest/data/redis:/data
    networks:
      - photonest-network
    healthcheck:
      test: ["CMD", "redis-cli", "--no-auth-warning", "-a", "${REDIS_PASSWORD}", "ping"]
      interval: 30s
      timeout: 5s
      retries: 3

  photonest-db:
    image: mariadb:10.11
    container_name: photonest-db
    restart: unless-stopped
    environment:
      - TZ=Asia/Tokyo
      - MYSQL_ROOT_PASSWORD=${DB_ROOT_PASSWORD}
      - MYSQL_DATABASE=photonest
      - MYSQL_USER=photonest_user
      - MYSQL_PASSWORD=${DB_PASSWORD}
    volumes:
      - /volume1/docker/photonest/db:/var/lib/mysql
      - /volume1/docker/photonest/init.sql:/docker-entrypoint-initdb.d/init.sql:ro
    ports:
      - "3306:3306"
    networks:
      - photonest-network
    healthcheck:
      test: ["CMD", "healthcheck.sh", "--connect", "--innodb_initialized"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 30s

  photonest-redis:
    image: redis:7-alpine
    container_name: photonest-redis
    restart: unless-stopped
    command: redis-server --appendonly yes
    environment:
      - TZ=Asia/Tokyo
    volumes:
      - /volume1/docker/photonest/redis:/data
networks:
  photonest-network:
    driver: bridge
```

## 3. Container Managerでのデプロイ

### 3.1 イメージのビルド方法

#### 方法1: Synology上で直接ビルド（推奨）
1. Container Managerを開く
2. 「イメージ」タブを選択
3. 「追加」→「Dockerfileからビルド」を選択
4. 設定：
   - **イメージ名**: `photonest:latest`
   - **Dockerfileパス**: `/docker/photonest/Dockerfile`
   - **コンテキストパス**: `/docker/photonest/`
5. 「ビルド」を実行

#### 方法2: 外部でビルドしてインポート
```bash
# 開発マシンでイメージをビルド
docker build -t photonest:latest .

# イメージをtarファイルとして保存
docker save photonest:latest > photonest-latest.tar

# SynologyにアップロードしてContainer Managerでインポート
```

### 3.2 プロジェクトの作成
1. Container Managerで「プロジェクト」タブを選択
2. 「作成」をクリック
3. 設定：
   - **プロジェクト名**: `photonest`
   - **パス**: `/docker/photonest/`
   - **ソース**: 「既存のdocker-compose.ymlをアップロード」を選択
   - **ファイル**: `docker-compose.synology.yml`を選択

### 3.3 サービスの起動
1. プロジェクト一覧で「photonest」を選択
2. 「アクション」→「ビルドして起動」を選択
3. 起動順序を確認：
   - photonest-db（データベース）
   - photonest-redis（Redis）
   - photonest-web（Webアプリ）
   - photonest-worker（Celeryワーカー）
   - photonest-beat（Celeryスケジューラ）

## 4. ネットワーク設定とアクセス公開

### 4.1 ポート設定の確認
Container Managerで各コンテナのポートを確認：
- **photonest-web**: 5000:5000
- **photonest-db**: 3306:3306（内部アクセスのみ）
- **photonest-redis**: 6379:6379（内部アクセスのみ）

### 4.2 DSMでのアクセス設定

#### 4.2.1 リバースプロキシの設定（推奨）
1. DSMの「コントロールパネル」→「アプリケーションポータル」を開く
2. 「リバースプロキシ」タブを選択
3. 「作成」をクリック
4. 設定：
   - **説明**: PhotoNest
   - **ソースプロトコル**: HTTPS
   - **ソースホスト名**: your-nas-domain.synology.me
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
3. ドメイン名を取得（例：your-nas.synology.me）

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
1. ブラウザで `https://your-nas-domain.synology.me` にアクセス
2. PhotoNestのログイン画面が表示されることを確認
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
docker logs photonest-db
docker logs photonest-redis
```

### 6.3 定期メンテナンス

#### 6.3.1 バックアップ設定
```bash
# データベースバックアップスクリプト
#!/bin/bash
BACKUP_DIR="/volume1/docker/photonest/backups"
DATE=$(date +%Y%m%d_%H%M%S)

# データベースバックアップ
docker exec photonest-db mysqldump -u root -p${DB_ROOT_PASSWORD} photonest > \
    ${BACKUP_DIR}/db_backup_${DATE}.sql

# メディアファイルバックアップ（必要に応じて）
tar -czf ${BACKUP_DIR}/media_backup_${DATE}.tar.gz \
    /volume1/docker/photonest/data/

# 古いバックアップの削除（30日より古い）
find ${BACKUP_DIR} -name "*.sql" -mtime +30 -delete
find ${BACKUP_DIR} -name "*.tar.gz" -mtime +30 -delete
```

#### 6.3.2 アップデート手順
1. 新しいPhotoNestリリースをダウンロード
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
3. PhotoNestイメージの更新
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
1. photonest-dbコンテナの状態確認
2. データベース認証情報の確認
3. ネットワーク接続の確認

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
docker-compose -f docker-compose.synology.yml up -d
echo "PhotoNest started successfully!"
echo "Access URL: https://your-nas-domain.synology.me"
```

#### stop-photonest.sh
```bash
#!/bin/bash
cd /volume1/docker/photonest/
docker-compose -f docker-compose.synology.yml down
echo "PhotoNest stopped successfully!"
```

#### backup-photonest.sh
```bash
#!/bin/bash
BACKUP_DIR="/volume1/docker/photonest/backups"
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p ${BACKUP_DIR}

# データベースバックアップ
docker exec photonest-db mysqldump -u root -p${DB_ROOT_PASSWORD} \
    --single-transaction --routines --triggers photonest > \
    ${BACKUP_DIR}/photonest_db_${DATE}.sql

# 設定ファイルバックアップ
cp /volume1/docker/photonest/config/.env ${BACKUP_DIR}/env_${DATE}.backup

echo "Backup completed: ${BACKUP_DIR}"
echo "Database: photonest_db_${DATE}.sql"
echo "Config: env_${DATE}.backup"
```

### 9.2 監視スクリプト

#### check-status.sh
```bash
#!/bin/bash
echo "=== PhotoNest Status Check ==="
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
    server your-nas-ip:5000;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /path/to/certificate.crt;
    ssl_certificate_key /path/to/private.key;

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

このガイドに従って、SynologyでPhotoNestを安全かつ効率的にデプロイしてください。
