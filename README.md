# nolumia

Flask + DDD アーキテクチャによる家族写真管理・同期プラットフォーム。Google Photos 同期、ローカルファイルインポート、動画変換、サムネイル生成などの処理を Celery によるバックグラウンドジョブで実行します。

## ドキュメント

- [アーキテクチャガイド](docs/ARCHITECTURE.md) - DDD 設計・レイヤー構成・技術スタック
- [運用ガイド](docs/OPERATIONS.md) - 開発環境セットアップ・DB 操作・機能設定・トラブルシューティング
- [scripts/](scripts/README.md) - 運用スクリプト一覧

## 必要環境

### 開発環境

| 依存 | バージョン |
|---|---|
| Python | 3.11 以上 |
| MariaDB | 10.11 以上 |
| Redis | 7.x |
| Node.js | 20.x LTS（フロントエンド開発時） |
| FFmpeg | 任意（動画変換機能を使う場合） |

### 本番環境（Docker）

| 依存 | バージョン |
|---|---|
| Docker | 20.10 以上 |
| Docker Compose | v2 以上 |
| RAM | 2GB 以上 |
| ディスク | 10GB 以上 |

## 開発環境セットアップ

```bash
# 仮想環境作成・有効化
python -m venv .venv
source .venv/bin/activate

# 依存関係インストール
pip install --upgrade pip
pip install -r requirements.txt

# 環境設定（.env を編集してDB接続情報等を設定）
cp .env.example .env

# データベースセットアップ（スキーマ + 認可マスタデータ）
alembic -c migrations/alembic.ini upgrade head

# システム設定（app.config / app.cors）も含めて投入する場合
python scripts/seed_master_data.py

# Flask 開発サーバー起動
python main.py

# Celery ワーカー（別ターミナル）
celery -A cli.src.celery.tasks worker --loglevel=info

# Celery beat スケジューラー（別ターミナル）
celery -A cli.src.celery.tasks beat --loglevel=info
```

フロントエンドを開発する場合:

```bash
cd frontend
npm install
npm run dev   # http://localhost:3000 で起動、Flask へのリクエストはプロキシ
```

## ビルド

Docker イメージのビルドは `scripts/.build.sh` で行います。成果物は `.tar` ファイルとして出力されます。

```bash
# アプリ + DB を両方ビルド（推奨）
./scripts/.build.sh

# アプリイメージのみ → photonest-latest.tar
./scripts/.build.sh app

# DB イメージのみ → photonest-db-latest.tar
./scripts/.build.sh db
```

`scripts/.build.sh app` は以下を順に実行します:

1. 前提チェック（Docker / buildx / make / git）
2. `docker buildx build` でイメージをローカルに作成（フロントエンドのビルドを含む）
3. イメージ内の `shared/kernel/version.json` を表示して内容確認
4. `docker save` で `photonest-latest.tar` を書き出し

`make` を直接使う場合:

```bash
make build           # アプリのみ
make build-db        # DB のみ
make all             # 両方

make load            # TAR からイメージをロード
make run             # ロード済みイメージを単体起動（動作確認用）
make show-tar-version  # TAR の中身のバージョン情報を確認
make clean           # 生成物と Docker ビルドキャッシュを削除
```

## デプロイ

### Synology NAS（本番 / STG）

`make build` / `make build-db` で生成した `.tar` を Synology に転送してから実行します。

```bash
# TAR を Synology に転送（例）
scp photonest-latest.tar photonest-db-latest.tar user@synology:/volume1/docker/

# 本番デプロイ（SSH 接続後）
./scripts/deploy.sh

# STG デプロイ
./scripts/deploy-stg.sh

# 完全初期化（初回またはリセット時）
./scripts/deploy.sh reset
./scripts/deploy-stg.sh reset
```

deploy スクリプトの処理内容:

1. `photonest-latest.tar` をロード（`docker load`）
2. 既存コンテナを停止（`docker compose down`）
3. `reset` モードの場合は `photonest-db-latest.tar` も再ロードし DB・メディアデータを削除
4. コンテナを起動（`docker compose up -d`）
5. `/health/live` へのポーリングでヘルスチェック

期待するディレクトリ構成（Synology 上）:

```
/volume1/docker/
├── photonest/           ← docker-compose.yml + .env（本番）
├── photonest-stg/       ← docker-compose.yml + .env（STG）
├── photonest-latest.tar
├── photonest-db-latest.tar
└── scripts/
    ├── deploy.sh
    └── deploy-stg.sh
```

コンテナ構成（`docker-compose.yml`）:

| サービス | 役割 |
|---|---|
| `web` | Gunicorn による Flask API（ポート 8050） |
| `worker` | Celery ワーカー（バックグラウンドジョブ処理） |
| `beat` | Celery beat（定期タスクスケジューラー） |
| `db` | MariaDB |
| `redis` | Celery ブローカー / バックエンド |

### 初回起動後の初期化

```bash
# マイグレーション適用（スキーマ + 認可マスタデータ）
docker compose exec web alembic -c migrations/alembic.ini upgrade head

# システム設定（app.config / app.cors）も含めて投入する場合
docker compose exec web python scripts/seed_master_data.py

# 初期ログイン情報（必ずパスワードを変更してください）
# Email:    admin@example.com
# Password: admin123
```

## アーキテクチャ

```
nolumia/
├── bounded_contexts/   # 境界づけられたコンテキスト
│   ├── photonest/      #   写真・メディア管理の中核ドメイン
│   ├── picker_import/  #   Google Photos ピッカー連携・インポート
│   ├── storage/        #   ストレージ抽象（ローカル/Azure Blob/CDN）
│   ├── email/          #   メール送信
│   ├── email_sender/   #   メール送信の実装（SMTP）
│   ├── certs/          #   アクセストークン署名証明書管理
│   ├── totp/           #   TOTP（二要素認証）
│   └── wiki/           #   Wiki/ドキュメント
│
├── shared/             # 複数コンテキストで共有する要素
│   ├── domain/         #   共有ドメイン（user, auth）
│   ├── application/    #   共有アプリケーションサービス
│   ├── infrastructure/ #   共有インフラ（リポジトリ実装）
│   ├── presentation/   #   共有プレゼンテーション部品
│   └── kernel/         #   共有カーネル（crypto, database, logging, settings）
│
├── presentation/web/   # Flask アプリ本体（create_app・Blueprint・API・認証）
├── cli/                # Celery タスク定義・CLI
├── frontend/           # React SPA（Vite + TypeScript + Redux）
├── migrations/         # Alembic マイグレーション
├── db/                 # DB コンテナ用 Dockerfile と初期化 SQL
├── scripts/            # 運用・デプロイ・デバッグスクリプト
├── docs/               # 設計・運用ドキュメント
└── tests/              # ユニット・統合テスト
```

詳細は [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) を参照。

## テスト実行

```bash
# 全テスト
pytest

# カバレッジ付き
pytest --cov=presentation --cov=bounded_contexts --cov=shared --cov=cli

# 特定ディレクトリ
pytest tests/unit/core/ -v
```

## セキュリティ設定

Google Photos の OAuth トークンは AES-256-GCM で暗号化保存します。`.env` に暗号化鍵を設定してください。

```bash
# 暗号化鍵生成
python -c "import os, base64; print('ENCRYPTION_KEY=base64:' + base64.b64encode(os.urandom(32)).decode())"
```

主な環境変数（`.env.example` を参照）:

```env
SECRET_KEY=<strong-secret-key>
DATABASE_URI=mysql+pymysql://<user>:<pass>@<host>/<db>
GOOGLE_CLIENT_ID=<your-google-client-id>
GOOGLE_CLIENT_SECRET=<your-google-client-secret>
ENCRYPTION_KEY=base64:<generated-key>
```

## ライセンス

[MIT License](LICENSE)
