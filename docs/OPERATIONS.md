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

Synology / Docker 環境では通常 `scripts/deploy.sh migrate`（本番）/
`scripts/deploy-stg.sh migrate`（STG）から自動適用する（3. デプロイ参照）。
ここでは手動実行する場合のコマンドを示す。

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

DDLを変更したとき:

```bash
# 1. db/init/01_initialize.sql を現在の migration head から再生成
./scripts/regenerate_db_baseline.sh

# 2. DBイメージをリビルド
make build-db

# 3. デプロイ（DB・メディアデータを削除して作り直す）
./scripts/deploy.sh reset       # 本番
./scripts/deploy-stg.sh reset   # STG
```

初期化確認:
```bash
docker logs mariadb | grep Entrypoint      # 本番
docker logs mariadb-stg | grep Entrypoint  # STG
```

何が投入されるか・仕組みは `scripts/README.md` を参照。

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

流れ: **ビルド → デプロイ**。本番/STGどちらも同じ2ステップ。

### ビルド

```bash
./scripts/.build.sh        # アプリ + DB イメージを TAR 生成（アプリのみ/DBのみも可）
```

`make build` / `make build-db` を呼び出すラッパー。コマンドの詳細は `scripts/README.md` 参照。

### Docker（推奨）

```bash
./scripts/deploy.sh app       # アプリのみ更新
./scripts/deploy.sh migrate   # DDL更新
./scripts/deploy.sh reset     # 完全初期化

# STG は deploy-stg.sh を使う（同じ引数）

# ログ確認
docker compose logs web --tail 100
docker compose logs worker --tail 50
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

#### 初回セットアップ

ディレクトリ配置・TAR転送先は `scripts/README.md`（`deploy.sh` / `deploy-stg.sh`）参照。

**1. .env 設定**（`photonest/.env`。最低限変更が必要な項目）

```env
SECRET_KEY=<strong-secret-key>
JWT_SECRET_KEY=<strong-jwt-secret>
MARIADB_ROOT_PASSWORD=<strong-password>
MARIADB_USER=<user>
MARIADB_PASSWORD=<strong-password>
REDIS_PASSWORD=<strong-redis-password>
GOOGLE_CLIENT_ID=<google-client-id>       # OAuth使用時のみ
GOOGLE_CLIENT_SECRET=<google-client-secret>
MEDIA_DOWNLOAD_SIGNING_KEY=<signing-key>
```

> DB・メディアのディレクトリは compose の `init-paths` サービスが起動時に自動作成する。File Station での手動作成は不要。

**2. ビルド・転送・デプロイ**

```bash
# 開発マシンで
./scripts/.build.sh
scp photonest-latest.tar photonest-db-latest.tar <user>@<nas-ip>:/volume1/docker/

# Synology 上で（初回はスキーマ + マスタデータ投入済みの状態まで起動する）
./scripts/deploy.sh reset
```

**3. リバースプロキシ（DSM）**

コントロールパネル → アプリケーションポータル → リバースプロキシ:
- ソース: HTTPS / `<your-nas-domain.synology.me>` / 443
- デスティネーション: HTTP / localhost / 5000

SSL証明書はコントロールパネル → セキュリティ → 証明書 から Let's Encrypt で取得。

#### 日常運用

```bash
# 更新（アプリのみ / DDL更新 / 完全初期化は「3. デプロイ」参照）
./scripts/deploy.sh app

# バックアップ
DATE=$(date +%Y%m%d_%H%M%S)
docker exec mariadb mysqldump -u root -p"$MARIADB_ROOT_PASSWORD" --single-transaction appdb \
    > /volume1/docker/photonest/backups/photonest_db_${DATE}.sql

# 状態確認
docker compose -p photonest ps
curl -s http://localhost:5000/api/health
```

### STG を本番と同一ホストで共存させたいとき

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

```bash
# STG 用ディレクトリで .env を用意
cp .env.staging.example .env       # ポート・データルート・NW・ドメインを STG 値に

# STG 用の外部ネットワークを作成（初回のみ）
docker network create photonest-stg

# 設定の解決結果を確認（ポート/コンテナ名/ボリュームが STG 値か）
docker compose config | grep -E "container_name|published|source:"
```

> ネットワークは `external: true`。環境ごとに別ネットワーク名にすることで、
> サービス名（`db` 等）の名前解決が環境間で衝突しない。

---

## 4. 機能設定ガイド

APIエンドポイントの仕様は Swagger UI（`/api/docs`）または一覧ページ（`/api/overview`）を参照。
以下は各機能を有効化・設定したいときに触る `.env` / DB設定のみ。

### OAuth を HTTPS 経由（リバースプロキシ配下）で使いたいとき

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

### パスワードリセット（メール経由）を有効化したいとき

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

動作確認: `pytest tests/webapp/auth/test_password_reset.py -v`

### TOTP（二要素認証）を管理したいとき

管理画面から利用する（`totp:view`/`totp:write` 権限が必要）。追加の `.env` 設定は不要。

### CDN 配信（Azure CDN / CloudFlare CDN）を有効化したいとき

**.env**:
```env
CDN_ENABLED=true
CDN_PROVIDER=azure                     # azure / cloudflare / generic
CDN_AZURE_ACCOUNT_NAME=<account>
CDN_AZURE_ACCESS_KEY=<access-key>
CDN_AZURE_PROFILE=<profile-name>
CDN_AZURE_ENDPOINT=<endpoint-name>
CDN_CACHE_TTL=3600
```

設定内容の確認: `python scripts/demo_cdn_configuration.py --cdn`

### システム設定（DB管理）を変更したいとき

管理画面、または `python scripts/bootstrap_system_settings.py` で `system_settings`
テーブルを更新する。主なキー: `access_token_signing`（JWT署名モード）、`app.config`、
`app.cors`。

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

## 6. トラブルシューティング（Docker / デプロイ）

| 症状 | 対処 |
|---|---|
| Container Manager に赤い traceback が出る | `docker inspect --format '{{json .State.Health}}' <container名> \| python3 -m json.tool` で healthcheck の実行結果を確認する（`docker compose -p <project> ps` でも Health 列が見える） |
| `docker load` が反応なく見える | `...still loading` のハートビートが出続けていれば進行中。別ターミナルで `watch -n 2 'docker system df'` |
| `docker events` にパスワードが平文で出る | `docker-compose.yml` の healthcheck が `${VAR}` を直接展開していないか確認する（`$$VAR` にする） |
| `photonest-latest.tar` が異常に大きい | `docker images photonest:latest` / `docker history photonest:latest --no-trunc` でレイヤーを確認する |
| `docker build` の "transferring context" が大きい | `du -sh photonest-latest.tar photonest-db-latest.tar` で古い tar がビルドディレクトリに残っていないか確認する |

各症状の原因・仕組みは `scripts/README.md` を参照。

---

## 7. バックアップ

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
