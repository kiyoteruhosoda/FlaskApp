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

FastAPI（ASGI）が `/api/*` を処理し、Flask が UI ルートを処理する Strangler Fig 構成。

```bash
# ターミナル1: Vite（フロントエンド）
cd frontend
npm run dev

# ターミナル2: ASGI サーバー（FastAPI + Flask Strangler Fig）
uvicorn asgi:app --host 0.0.0.0 --port 5000 --reload

# ブラウザで http://localhost:5000 にアクセス
```

開発用に Flask 単体で起動する場合（API は Flask 側のみ）:
```bash
python main.py
```

> **注意**: 本番（Docker）は `gunicorn asgi:app -k uvicorn.workers.UvicornWorker`
> で ASGI 起動する。`wsgi:app`（Flask 単体）は開発デバッグ用途のみ。

Viteを起動せず Flask のみ起動した場合は、`/` アクセス時に起動方法が案内される。

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
```

ログ確認は `docker-compose.yml`/`.env` があるディレクトリに `cd` してから、
**サービス名**（コンテナ名ではない）を指定する:

```bash
# 本番
cd /volume1/docker/photonest
docker compose logs web --tail 100
docker compose logs worker --tail 50

# STG
cd /volume1/docker/photonest-stg
docker compose logs web --tail 100
```

> 別ディレクトリから実行する場合は `docker compose -p photonest -f /volume1/docker/photonest/docker-compose.yml --env-file /volume1/docker/photonest/.env logs web` のように `-p`/`-f`/`--env-file` を明示する。

サービス構成（`docker compose logs <サービス名>` の引数）:
- `web` — FastAPI + Flask（Gunicorn + UvicornWorker、ASGI、ポート 5000）
- `worker` — Celery ワーカー
- `beat` — Celery Beat（定期タスク）
- `redis` — Redis（Broker / Backend）
- `db` — MariaDB

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
ENCRYPTION_KEY=<32-byte-base64-key>       # Google連携（トークン暗号化）に必須
MEDIA_DOWNLOAD_SIGNING_KEY=<signing-key>
```

`ENCRYPTION_KEY` の生成例（`base64:` 接頭辞付き・32バイト）:

```bash
python3 -c "import base64, os; print('base64:' + base64.urlsafe_b64encode(os.urandom(32)).decode())"
```

.env の代わりに管理画面の System Settings（Security & Signing >
Token encryption key）でも設定できる。未設定のまま Google アカウント連携を
開始しようとするとエラーメッセージで案内される。

Google アカウント連携の詳細設定は管理画面の System Settings（Identity
Providers セクション）から変更できる。

- `GOOGLE_OAUTH_REDIRECT_ORIGIN` — OAuth コールバック URL のスキーム・ホスト
  （例: `https://photos.example.com`）。リバースプロキシ配下で自動判定が
  効かない場合のみ設定する。**パス `/auth/google/callback` は固定で自動付与**
  され、パスを含む値は保存時に拒否される。空欄（既定）ならリクエストから
  `https://<request-host>/auth/google/callback` を自動生成する。
  Google Cloud Console の「承認済みのリダイレクト URI」には
  `<設定値>/auth/google/callback` を登録する。
- `GOOGLE_PHOTO_PICKER_SCOPES` — Photo Picker 連携で要求する OAuth スコープ。
  未設定時は既定スコープが使われる。

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
cd /volume1/docker/photonest && docker compose ps
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

### 画像・メディアの配信方式を選びたいとき（表示が遅いとき）

画像（サムネイル・オリジナル・動画）の配信は次の流れで行う。まず全体像を押さえ、
どこを速くしたいかで設定を選ぶ。

**配信パイプライン**:

1. フロントが署名付き URL を要求する
   （`POST /api/media/<id>/thumb-url` 等 → `/api/dl/<token>` を受け取る）。
2. ブラウザが `/api/dl/<token>` を GET する。トークンは署名・有効期限を検証される。
3. 実バイトの返し方が **3 通り**あり、以下の設定で切り替わる。

| 方式 | 誰がバイトを返すか | 速度 | 必要なもの |
|---|---|---|---|
| ① Flask 直返し | Gunicorn（Python）がファイルを読んで流す | 遅い | 設定不要（`MEDIA_ACCEL_REDIRECT_ENABLED=false`） |
| ② Nginx 直接（X-Accel-Redirect） | Nginx がディスクから直接返す | 速い | **docker-compose 既定** |
| ③ CDN | エッジがキャッシュから返す | 最速（2回目以降） | 設定 + オリジン（②の nginx）+ データ配信 |

**docker-compose では方式②が既定で有効**。`nginx` コンテナが公開ポート
（`WEB_HOST_PORT`）を受け持ち、`web`（gunicorn）は内部専用。メディアは nginx が
`X-Accel-Redirect` でディスクから直接配信する（`MEDIA_ACCEL_REDIRECT_ENABLED=true`）。
「以前は Nginx から直接取得していた」挙動はこれで既定に戻っている。

> **注意**: 方式②有効時に `web` へ直接アクセスすると、内部配信ヘッダーが解釈されず
> 壊れる。必ず nginx（公開ポート）経由で使う。純粋なローカル開発（`flask run` 等で
> nginx を挟まない）では `.env` で `MEDIA_ACCEL_REDIRECT_ENABLED=false` にして方式①に
> フォールバックする（コード既定は false）。

> メディア URL（サムネイル・オリジナル・動画）は
> `MEDIA_THUMBNAIL_URL_TTL_SECONDS` 等（既定 600 秒）のウィンドウ単位で決定的に
> 発行され、同一メディアは同一 URL を返す。ブラウザ／CDN のキャッシュを効かせるため、
> この TTL より短い間隔で同じ画像を何度開いても URL は変わらない。

#### 方式② Nginx から直接配信（X-Accel-Redirect）— docker-compose 標準構成

`docker-compose.yml` の `nginx` サービスがフロントに立ち、以下を行う（設定は
`docker/nginx/default.conf`）:

- 通常リクエストを `web:5000` へプロキシ。
- `web` が返す `X-Accel-Redirect: /media/{thumbs,playback,originals}/<rel>` を受けて
  `internal` ロケーションからファイルを直接配信。外部から `/media/*` へ直アクセスは
  404（署名を通った内部リダイレクト時のみ配信 = 署名バイパス防止）。

alias 先・accel ロケーションは settings 既定（`system_settings_defaults.py`）と一致:

```
MEDIA_ACCEL_THUMBNAILS_LOCATION=/media/thumbs → /app/data/media/thumbs
MEDIA_ACCEL_PLAYBACK_LOCATION=/media/playback → /app/data/media/playback
MEDIA_ACCEL_ORIGINALS_LOCATION=/media/originals → /app/data/media/originals
```

`nginx` コンテナはデータを読み取り専用（`:ro`）でマウントするため、通常は追加設定
不要。別ホストで nginx を立てる／パスを変える場合は accel ロケーションと alias を
揃える。`Content-Type`/`Cache-Control` は `web` のレスポンスヘッダーがそのまま使われる。

**データ（必須）**: サムネイル等の派生ファイルは取り込み後に生成される。未生成の
メディアは方式に関わらず表示できない（「2. データベース操作 → originals からの
メディア再構築」で再生成）。つまり**設定だけでなくデータ整備も必要**。

#### ストレージバックエンド（ローカル / Blob）

ファイルの実体をどこに置くか。`STORAGE_BACKEND` で切り替える。

```env
STORAGE_BACKEND=local     # 既定。ローカル/NAS のファイルシステム
# STORAGE_BACKEND=blob    # オブジェクトストレージ（Blob）
```

**Blob を使う場合のデータ整備（必須）**: 既存の originals / thumbs / playback を
Blob へアップロードしておく必要がある（設定を変えるだけでは既存ファイルは移らない）。
Blob 上にファイルが無ければ方式①でも②でも 404 になる。方式②（Nginx 直接）は
ローカルファイルシステム前提のため、Blob と併用する場合は方式①か③（CDN）を使う。

#### まとめ（何が必要か）

- **とにかく速くしたい／以前の挙動に戻したい** → 方式②（docker-compose 既定）。追加設定不要。
- **地理的に分散・大量アクセス** → 方式③ CDN（下記）。オリジンは方式②の nginx。
- **どの方式でも** サムネイル等の派生ファイルが生成済みであること（データ整備）が前提。

### CDN 配信（CloudFlare CDN / Azure CDN）を有効化したいとき

上記「配信方式」の方式③。**オリジンは方式②の nginx コンテナ**（`WEB_HOST_PORT` を
公開するドメイン）に向ける。CDN は設定に加え、初回アクセスでのプル（またはプリフェッチ）
によるデータ配信が必要。管理画面（設定 → CDN）でも `CDN_PROVIDER` を選択リストで
切り替えられる（none / azure / cloudflare / generic）。

**対応プロバイダー**: 実装があるのは `cloudflare` / `azure` / `generic`。CloudFlare は
キャッシュパージ（API v4）・ゾーン設定更新・キャッシュ状態取得（`CF-Cache-Status`）・
アナリティクス（GraphQL）・プリフェッチを実際の API 呼び出しで行う。

**.env（CloudFlare の例）**:
```env
CDN_ENABLED=true
CDN_PROVIDER=cloudflare
CDN_CLOUDFLARE_API_TOKEN=<api-token>
CDN_CLOUDFLARE_ZONE_ID=<zone-id>
CDN_CLOUDFLARE_ORIGIN_HOSTNAME=photonest.example.com   # nginx を公開するドメイン
CDN_CACHE_TTL=3600
```

**.env（Azure の例）**:
```env
CDN_ENABLED=true
CDN_PROVIDER=azure
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

# コンテナログ（docker-compose.yml/.envのあるディレクトリで実行。3.デプロイ参照）
cd /volume1/docker/photonest
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
| `deploy.sh`/`deploy-stg.sh` が `permission denied ... docker.sock` で失敗する | `sudo` を付けて実行するか、実行ユーザーを `docker` グループに追加して再ログインする |
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
