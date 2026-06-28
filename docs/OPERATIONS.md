# nolumia 運用ガイド

開発環境セットアップ・デプロイ・DB操作・機能設定・トラブルシューティングをまとめる。

---

## 1. 開発環境セットアップ

### 前提条件

- Python 3.10 以上
- Redis（Celery の broker / backend 用）
- MariaDB 10.11
- FFmpeg（動画変換用）
- Node.js 18 以上（フロントエンド開発時）

### 初期セットアップ

```bash
# 仮想環境作成・有効化
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# パッケージインストール
pip install --upgrade pip
pip install -r requirements.txt

# 環境設定
cp .env.example .env
# .env を編集してDB接続情報・各種キーを設定

# データベースマイグレーション
flask db upgrade

# マスタデータ投入（ロール・権限・初期設定）
flask seed-master
```

### 開発サーバー起動

Flask が全リクエストを受け付け、API以外はViteにプロキシする構成。

```bash
# ターミナル1: Vite（フロントエンド）
cd frontend
npm run dev

# ターミナル2: Flask（バックエンド）
python main.py

# ブラウザで http://localhost:5000 にアクセス
```

Viteを起動せず Flask のみ起動した場合は、`/` アクセス時に起動方法が案内される。

本番モード（ビルド済みファイルを配信）:
```bash
cd frontend && npm run build
FLASK_ENV=production python main.py
```

### Celeryワーカー（必須）

非同期処理（サムネイル生成・インポート・動画変換）に必要。開発時も起動すること。

```bash
# ワーカー起動
celery -A cli.src.celery.tasks worker --loglevel=info

# Beat（定期タスク）起動
celery -A cli.src.celery.tasks beat --loglevel=info

# Docker の場合は自動起動（docker-compose.yml 参照）
```

主な定期タスク:
- `picker_import.watchdog` — 取り込みセッション監視
- `session_recovery.cleanup_stale_sessions` — 停止中セッションのクリーンアップ
- `backup_cleanup.cleanup` — 古いバックアップの削除（30日以上）

---

## 2. データベース操作

### マイグレーション（Alembic）

```bash
# 現在の状態確認
flask db current
flask db history

# マイグレーション適用
flask db upgrade

# 一つ戻す
flask db downgrade

# Docker の場合
docker compose exec web flask db upgrade
docker compose exec web flask db current
```

トラブルシューティング:
```bash
# マイグレーション履歴の不整合を強制リセット（慎重に）
flask db stamp <revision-id>

# DB接続確認
docker compose ps db
```

### マスタデータ投入

```bash
# 推奨方法
flask seed-master

# 既存データがあっても強制投入
flask seed-master --force

# YAML から投入
python scripts/seed_from_yaml.py
```

投入されるマスタデータ:
- ロール: `admin`(1) / `manager`(2) / `member`(3) / `guest`(4)
- 権限: `admin:photo-settings`, `user:manage`, `album:create`, `media:view` 他

### DB再初期化（Synology / Docker）

`db/init/01_initialize.sql` を更新した場合の手順:

```bash
# 1. DBイメージをリビルド
make build-db

# 2. Synology側で停止・DB削除・イメージ更新
docker compose -p photonest -f /volume1/docker/photonest/docker-compose.yml down
rm -rf /volume1/docker/photonest/db_data/*
docker load -i /volume1/docker/photonest-db-latest.tar

# 3. 再起動
docker compose -p photonest -f /volume1/docker/photonest/docker-compose.yml up -d

# 4. 初期化確認
docker logs mariadb | grep Entrypoint
```

### originals からのメディア再構築

DB を初期化した後、`MEDIA_ORIGINALS_DIRECTORY`（NAS 上の原本）から Media の
メタデータを再登録する。取り込み inbox は取り込み後に空になるため、DB だけ作り直す
場合はこの CLI で復元する（冪等。サムネイル等の派生生成は行わない）。

```bash
flask rebuild-originals             # originals を走査し未登録ファイルを Media 化
flask rebuild-originals --dry-run   # 変更せず件数のみ集計
flask rebuild-originals --refresh   # 既存 Media のメタデータも再適用
flask rebuild-originals --verbose   # 1件ごとに表示
```

冪等性は `local_rel_path` をキーに担保するため、再実行しても重複登録されない。
原本は削除・変更されない。

---

## 3. デプロイ

### 環境切替（本番 / STG）

`docker-compose.yml` の環境差分（プロジェクト名・ポート・データルート・ネットワーク・
ドメイン）はすべて `.env` で切り替える。値未設定時のデフォルトは従来の本番値なので、
既存の本番 `.env` は変更不要。

| 変数 | 役割 | 本番デフォルト |
|---|---|---|
| `COMPOSE_PROJECT_NAME` | コンテナ/NW 接頭辞（環境分離の要） | `photonest` |
| `HOST_DATA_ROOT` | 永続データのホスト側ルート | `/volume1/docker/photonest` |
| `WEB_BIND_ADDR` / `WEB_HOST_PORT` | Web 公開（既定 127.0.0.1:8050） | `127.0.0.1` / `8050` |
| `DB_HOST_PORT` / `DB_CONTAINER_NAME` | DB 公開ポート / コンテナ名 | `3307` / `mariadb` |
| `DOCKER_NETWORK_NAME` / `DOCKER_NETWORK_SUBNET` | 外部ネットワーク | `photonest-dev` / `172.22.0.0/16` |
| `WEB_IMAGE` / `DB_IMAGE` | 使用イメージタグ | `photonest:latest` / `photonest-db:latest` |
| `API_BASE_URL` / `CORS_ALLOWED_ORIGINS` | 自己参照 URL / 許可オリジン（ドメイン） | 環境ごとに設定 |

STG を本番と同一ホストで共存させる例:

```bash
# STG 用ディレクトリで .env を用意
cp .env.staging.example .env       # ポート・データルート・NW・ドメインを STG 値に

# STG 用の外部ネットワークを作成（初回のみ）
docker network create photonest-stg

# 設定の解決結果を確認（ポート/コンテナ名/ボリュームが STG 値か）
docker compose config | grep -E "container_name|published|source:"

# 起動（COMPOSE_PROJECT_NAME=photonest-stg により本番と分離）
docker compose up -d
```

> ネットワークは `external: true`。環境ごとに別ネットワーク名にすることで、
> サービス名（`db` 等）の名前解決が環境間で衝突しない。

### Docker（推奨）

```bash
# イメージビルド
docker build -t photonest:latest .

# 起動
docker compose up -d

# ログ確認
docker compose logs web --tail 100
docker compose logs worker --tail 50

# マイグレーション後の再起動
docker compose restart web
```

コンテナ構成:
- `photonest-web` — Flask アプリ（ポート 5000）
- `photonest-worker` — Celery ワーカー
- `photonest-beat` — Celery Beat（定期タスク）
- `photonest-redis` — Redis（Broker / Backend）

### Synology NAS デプロイ

#### 必要環境
- DSM 7.0 以上
- Container Manager インストール済み
- MariaDB 10（パッケージセンター）または外部 MySQL/MariaDB

#### 手順

**1. データベース準備（Synology MariaDB の場合）**

```sql
CREATE DATABASE photonest CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER '<photonest_user>'@'%' IDENTIFIED BY '<your-password>';
GRANT ALL PRIVILEGES ON photonest.* TO '<photonest_user>'@'%';
FLUSH PRIVILEGES;
```

**2. ディレクトリ作成（File Station）**

```
/volume1/docker/photonest/
├── config/
├── data/
│   ├── media/
│   ├── thumbs/
│   ├── playback/
│   └── redis/
└── backups/
```

**3. イメージをSynologyへ転送**

```bash
# 開発マシンで
docker save photonest:latest > photonest-latest.tar
scp photonest-latest.tar <admin>@<nas-ip>:/volume1/docker/
```

Container Manager → イメージ → 追加 → ファイルからインポート

**4. .env 設定**（最低限変更が必要な項目）

```env
SECRET_KEY=<strong-secret-key>
JWT_SECRET_KEY=<strong-jwt-secret>
DATABASE_URI=mysql+pymysql://<user>:<pass>@<db-host>:3306/photonest
REDIS_PASSWORD=<strong-redis-password>
REDIS_URL=redis://:<strong-redis-password>@photonest-redis:6379/0
CELERY_BROKER_URL=redis://:<strong-redis-password>@photonest-redis:6379/0
CELERY_RESULT_BACKEND=redis://:<strong-redis-password>@photonest-redis:6379/0
GOOGLE_CLIENT_ID=<google-client-id>       # OAuth使用時のみ
GOOGLE_CLIENT_SECRET=<google-client-secret>
MEDIA_DOWNLOAD_SIGNING_KEY=<signing-key>
```

**5. 初期化**

```bash
docker exec -it photonest-web bash
flask db upgrade
flask seed-master
```

**6. リバースプロキシ（DSM）**

コントロールパネル → アプリケーションポータル → リバースプロキシ:
- ソース: HTTPS / `<your-nas-domain.synology.me>` / 443
- デスティネーション: HTTP / localhost / 5000

SSL証明書はコントロールパネル → セキュリティ → 証明書 から Let's Encrypt で取得。

#### Synology 運用スクリプト

```bash
# 起動
cd /volume1/docker/photonest/
docker-compose up -d

# バックアップ
DATE=$(date +%Y%m%d_%H%M%S)
mysqldump -h <db-host> -u <user> -p photonest \
    --single-transaction > /volume1/docker/photonest/backups/photonest_db_${DATE}.sql

# 状態確認
docker ps --filter "name=photonest" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
curl -s http://localhost:5000/api/health
```

---

## 4. 機能設定ガイド

### OAuth HTTPS 設定

リバースプロキシ（nginx / Synology）経由でHTTPS終端する場合の設定。

**.env**:
```env
PREFERRED_URL_SCHEME=https
```

**nginx 設定**（必須ヘッダー）:
```nginx
proxy_set_header X-Forwarded-Proto $scheme;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header Host $host;
```

**Google Cloud Console**: 認証済みリダイレクト URI に `https://<your-domain>/auth/google/callback` を追加。

デバッグ:
```bash
curl -H "X-Forwarded-Proto: https" https://<domain>/debug/oauth-url
```

### パスワードリセット機能

メール経由でパスワードを再設定する機能。

**.env**（SMTP設定）:
```env
MAIL_PROVIDER=smtp          # テスト環境は console
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USERNAME=your-email@example.com
MAIL_PASSWORD=your-app-password    # Gmailはアプリパスワードを使用
MAIL_DEFAULT_SENDER=your-email@example.com
```

主な仕様:
- トークン: 256ビットランダム、ハッシュ化保存、**30分有効**、ワンタイム
- エンドポイント: `GET/POST /auth/password/forgot`、`GET/POST /auth/password/reset`
- テスト: `pytest tests/webapp/auth/test_password_reset.py -v`

### TOTP 管理

管理者向け TOTP（二要素認証）の管理機能。

**権限要件**:
- `totp:view` — 一覧閲覧・エクスポート
- `totp:write` — 登録・編集・削除・インポート

**主な操作**:
- QR コード画像アップロードで `otpauth://` URI を自動解析
- JSON エクスポート / インポート（`force` フラグで重複上書き）
- 一覧は1秒ごとに OTP コードをフロントエンドで再計算

**API エンドポイント**:

| メソッド | パス | 説明 |
|---|---|---|
| `GET` | `/api/totp` | 一覧取得 |
| `POST` | `/api/totp` | 新規登録 |
| `PUT` | `/api/totp/<id>` | 更新 |
| `DELETE` | `/api/totp/<id>` | 削除 |
| `GET` | `/api/totp/export` | JSON エクスポート |
| `POST` | `/api/totp/import` | JSON インポート |

### CDN 統合

画像・動画配信に CDN を使用する場合の設定。Azure CDN と CloudFlare CDN をサポート。

```python
from bounded_contexts.storage.domain import StorageCredentials, StorageConfiguration

cdn_config = StorageConfiguration(
    backend_type=StorageBackendType.AZURE_CDN,
    credentials=StorageCredentials(
        backend_type=StorageBackendType.AZURE_CDN,
        account_name="your-cdn-account",
        access_key="your-access-key",
        cdn_profile="your-profile-name",
        cdn_endpoint="your-endpoint-name",
    ),
    origin_backend_type=StorageBackendType.AZURE_BLOB,
    # ... origin_credentials
    cache_ttl=7200,
    enable_compression=True,
)
```

### システム設定（DB管理）

`system_settings` テーブルで管理するアプリ設定。管理画面または初期投入スクリプトで更新する。

| `setting_key` | 用途 |
|---|---|
| `access_token_signing` | JWTトークン署名モード（`builtin` / `server_signing`） |
| `app.config` | Flask 共通設定・外部サービス接続 |
| `app.cors` | CORS 許可オリジン配列 |

`access_token_signing` の JSON 例:
```json
{
  "mode": "server_signing",
  "groupCode": "prod-signers"
}
```

`mode="builtin"` の場合は `kid`・`groupCode` を設定しない。
`mode="server_signing"` かつ `groupCode` が欠けると `AccessTokenSigningValidationError`。

---

## 5. ログ監視

### Celeryタスクのログ

タスク実行履歴は `CeleryTaskRecord` と `JobSync` テーブルに保存される。

```bash
# タスク状況を確認
python -m cli.src.celery.inspect_tasks

# コンテナログ
docker compose logs worker --tail 100 | grep ERROR
```

### ローカルインポートログ

`log` テーブルにイベントが記録される。

```sql
-- 最新のインポートセッション
SELECT * FROM log
WHERE event = 'picker.session.complete'
ORDER BY created_at DESC LIMIT 5;

-- 特定セッションの全ログ
SELECT * FROM log
WHERE event LIKE 'picker.%'
AND message LIKE '%"session_id": 123%'
ORDER BY created_at;

-- ファイル保存ログ
SELECT created_at,
       JSON_EXTRACT(message, '$.file_path') AS file_path,
       JSON_EXTRACT(message, '$.file_size') AS file_size
FROM log WHERE event = 'picker.file.saved'
ORDER BY created_at DESC;
```

CLIスクリプトでも確認可能:
```bash
python scripts/check_logs.py --session-id 123
python scripts/check_logs.py --last 20 --event picker.session.error
```

### ヘルスチェック

```bash
curl http://localhost:5000/api/health
```

---

## 6. バックアップ

バックアップクリーンアップは Celery Beat が毎日自動実行（デフォルト30日保持）。

**.env 設定**:
```env
SYSTEM_BACKUP_DIRECTORY=/app/data/backups   # Synology: /volume1/docker/photonest/backups
BACKUP_RETENTION_DAYS=30
```

手動実行:
```python
from core.tasks.backup_cleanup import cleanup_old_backups, get_backup_status

result = cleanup_old_backups(retention_days=30)
status = get_backup_status()
```

対象ファイル: `.sql`, `.tar.gz`, `.backup`

> `MEDIA_BACKUP_DIRECTORY`（旧名称）も互換目的でサポートされるが、新規設定では `SYSTEM_BACKUP_DIRECTORY` を使用すること。
