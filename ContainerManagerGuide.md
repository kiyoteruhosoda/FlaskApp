# PhotoNest Container Manager設定ガイド

## Container Managerでのプロジェクト作成手順

### 1. プロジェクト基本設定
- **プロジェクト名**: `photonest`
- **説明**: `PhotoNest - Family Photo Management Platform`
- **パス**: `/volume1/docker/photonest`

### 2. docker-compose.yml設定
以下の内容でdocker-compose.ymlを作成：

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
    env_file:
      - ./config/.env
    volumes:
      - ./data/media:/app/data/media
      - ./data/thumbs:/app/data/thumbs
      - ./data/playback:/app/data/playback
    depends_on:
      - photonest-db
      - photonest-redis
    networks:
      - photonest-network

  photonest-worker:
    image: photonest:latest
    container_name: photonest-worker
    restart: unless-stopped
    command: celery -A cli.src.celery.tasks worker --loglevel=info --concurrency=2
    environment:
      - TZ=Asia/Tokyo
    env_file:
      - ./config/.env
    volumes:
      - ./data/media:/app/data/media
      - ./data/thumbs:/app/data/thumbs
      - ./data/playback:/app/data/playback
    depends_on:
      - photonest-db
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
    env_file:
      - ./config/.env
    depends_on:
      - photonest-db
      - photonest-redis
    networks:
      - photonest-network

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
      - ./db:/var/lib/mysql
      - ./init.sql:/docker-entrypoint-initdb.d/init.sql:ro
    networks:
      - photonest-network

  photonest-redis:
    image: redis:7-alpine
    container_name: photonest-redis
    restart: unless-stopped
    command: redis-server --appendonly yes
    environment:
      - TZ=Asia/Tokyo
    volumes:
      - ./redis:/data
    networks:
      - photonest-network

networks:
  photonest-network:
    driver: bridge
```

### 3. 環境変数設定
`config/.env`ファイルを編集：

**必須変更項目:**
```env
SECRET_KEY=your-very-strong-secret-key-here
AES_KEY=your-32-byte-aes-encryption-key-here
DB_ROOT_PASSWORD=strong-root-password
DB_PASSWORD=strong-user-password
```

### 4. Container Manager操作手順

1. **プロジェクト作成**
   - Container Manager > プロジェクト > 作成
   - 上記設定を入力

2. **イメージビルド**
   - プロジェクト詳細 > ビルド
   - または事前にイメージタブでビルド

3. **サービス起動**
   - プロジェクト詳細 > 開始
   - 起動順序: DB → Redis → Web → Worker → Beat

4. **ログ確認**
   - 各コンテナのログタブで動作確認

### 5. アクセス設定

1. **リバースプロキシ設定**
   - DSM > コントロールパネル > アプリケーションポータル
   - リバースプロキシ > 作成
   - ソース: HTTPS, your-nas.synology.me, 443
   - デスティネーション: HTTP, localhost, 5000

2. **外部アクセス設定**
   - コントロールパネル > 外部アクセス > DDNS
   - ルーター設定でポートフォワーディング

## トラブルシューティング

### よくある問題

1. **コンテナが起動しない**
   - ログを確認
   - 権限設定を確認: `chmod -R 755 data/`
   - ポートの競合確認

2. **データベース接続エラー**
   - 環境変数の確認
   - DB_PASSWORDの設定確認
   - MariaDBコンテナの状態確認

3. **外部アクセスできない**
   - リバースプロキシ設定確認
   - ファイアウォール設定確認
   - DDNS設定確認

### 管理コマンド

```bash
# SSH接続後に実行
cd /volume1/docker/photonest

# サービス状態確認
docker-compose ps

# ログ確認
docker-compose logs photonest-web

# データベースマイグレーション
docker-compose exec photonest-web flask db upgrade

# バックアップ
docker-compose exec photonest-db mysqldump -u root -p photonest > backup.sql
```
